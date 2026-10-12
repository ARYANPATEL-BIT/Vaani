"""Per-connection session state for the WebSocket gateway.

A Session is the server's memory of one live conversation: who it is, when it
started, how many valid audio frames it has seen, which turn is current, and
which turns have been flushed. Exactly one Session exists per WebSocket
connection, owned by the coroutine handling that socket. Nothing here is shared
between connections, so no locking is needed.

Flush lives here because "may this turn still send audio?" is session state:
every place that sends a frame for a turn must ask the session first. Since
day 13 the only thing that flushes is a barge-in (turns.py).
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic

from vaani.protocol import FlushAck, audio_flush
from vaani.providers.base import Message
from vaani.telemetry import FLUSH_ACKED, FLUSH_SENT, Telemetry

log = logging.getLogger("vaani.session")

# The shape of `websocket.send_json`: takes a dict, must be awaited. Taking the
# function rather than the websocket keeps Session testable without a socket.
SendJson = Callable[[dict], Awaitable[None]]


@dataclass
class Session:
    """State for a single live session.

    `frame_count` is the running total for the whole session (handy for a
    closing log line). `frames_this_interval` is the short-lived counter the
    per-interval logger reads and then resets — it answers "how many frames in
    the last second?" rather than "how many ever?".
    """

    session_id: str
    persona: str
    # "vad" (hands-free) or "ptt" (push-to-talk), from session.start (v0.9).
    # Fixed for the session: turns.py builds its pipeline from it once.
    mode: str = "vad"
    # monotonic() is a clock that only moves forward and is immune to system
    # time changes — correct for measuring elapsed time, not wall-clock dates.
    created_at: float = field(default_factory=monotonic)
    frame_count: int = 0
    frames_this_interval: int = 0
    # The most recent turn. A turn is one user utterance: it opens when speech
    # starts and closes when endpointing ends it. The id is kept after the
    # turn closes, so a late flush.ack can still be matched to it.
    current_turn_id: str | None = None
    # True while current_turn_id is open (between speech start and turn end).
    turn_open: bool = False
    # Frames that arrived for a flushed turn and were therefore not sent.
    late_frames_dropped: int = 0
    # The conversation so far, oldest first: user and assistant messages,
    # re-sent to the model every turn. An assistant message is what the user
    # HEARD: the whole reply once played, or the part before a barge-in.
    history: list[Message] = field(default_factory=list)
    # Every turn ever flushed in this session. A turn in here must never have
    # another audio frame sent for it.
    _flushed_turns: set[str] = field(default_factory=set)
    # turn_id -> perf_counter time its audio.flush was sent, for flushes whose
    # flush.ack has not arrived yet. Removed when the ack arrives.
    _awaiting_ack: dict[str, float] = field(default_factory=dict)

    def record_frame(self) -> None:
        """Count one valid audio frame."""
        self.frame_count += 1
        self.frames_this_interval += 1

    def take_interval_count(self) -> int:
        """Return frames seen since the last call, and reset the interval
        counter to zero for the next window."""
        count = self.frames_this_interval
        self.frames_this_interval = 0
        return count

    def open_turn(self) -> str:
        """Start a new turn, make it current, and return its id."""
        self.current_turn_id = uuid.uuid4().hex
        self.turn_open = True
        return self.current_turn_id

    def close_turn(self) -> None:
        """The current turn has ended (or was discarded as too short)."""
        self.turn_open = False

    def remember(self, user: str, assistant: str, keep_turns: int) -> None:
        """Append one exchange, then keep only the newest `keep_turns`."""
        self.history.append(Message(role="user", content=user))
        self.history.append(Message(role="assistant", content=assistant))
        # Two messages per exchange. max(0, ...) so keep_turns = 0 keeps
        # nothing (a bare `history[:-0]` would mean "keep everything").
        del self.history[: max(0, len(self.history) - 2 * keep_turns)]

    def is_flushed(self, turn_id: str) -> bool:
        """True if `turn_id` was flushed. Callers MUST check this immediately
        before sending a frame, with no `await` in between (see gateway)."""
        return turn_id in self._flushed_turns

    async def flush(self, send_json: SendJson, telemetry: Telemetry) -> str | None:
        """Flush the current turn: stop its frames and tell the browser.

        Returns the flushed turn_id, or None if there was nothing to flush (no
        turn yet, or this turn was already flushed — flushing is idempotent).

        It flushes whether or not the user's turn is still open: the agent's
        reply carries the same turn_id after the user's turn has closed.
        Whether there is anything to flush is the state machine's call
        (turns.py), not this method's.
        """
        turn_id = self.current_turn_id
        if turn_id is None:
            log.info("session %s: flush ignored, no turn yet", self.session_id)
            return None
        if turn_id in self._flushed_turns:
            log.info("session %s: turn %s already flushed", self.session_id, turn_id)
            return None

        # Mark FIRST, send SECOND. `await send_json(...)` hands control back to
        # the event loop until the send completes; any other coroutine that runs
        # during that pause and is about to send a frame for this turn must
        # already see the mark. If we marked after the await, a frame could
        # slip out between "flush decided" and "flush recorded".
        self._flushed_turns.add(turn_id)
        # Stamp flush_sent BEFORE the await too, for the same reason: an ack
        # handled during the pause must find this turn in _awaiting_ack. The
        # round trip then also includes the send itself, so it reads slightly
        # high — the safe direction for a latency number.
        span = telemetry.record(FLUSH_SENT, turn_id)
        self._awaiting_ack[turn_id] = span.at
        await send_json(audio_flush(turn_id))
        log.info("session %s: flush sent for turn %s", self.session_id, turn_id)
        return turn_id

    def handle_flush_ack(self, ack: FlushAck, telemetry: Telemetry) -> float | None:
        """Record a flush.ack and return the round trip in ms.

        An ack for a turn that was never flushed, or was already acknowledged,
        is logged and ignored (returns None). It is not an error: a slow or
        duplicated ack is normal network behaviour, not a bad client.

        The turn need NOT be the current one (day 13): a barge-in flushes the
        agent's turn and opens the user's next turn at once, so the ack for
        the flushed turn always arrives after a newer turn is current.
        """
        turn_id = ack.turn_id
        if turn_id not in self._awaiting_ack:
            log.warning(
                "session %s: ignoring flush.ack for turn %s (not awaiting an ack)",
                self.session_id,
                turn_id,
            )
            return None

        sent_at = self._awaiting_ack.pop(turn_id)
        span = telemetry.record(FLUSH_ACKED, turn_id)
        round_trip_ms = (span.at - sent_at) * 1000.0
        # client_ts is logged for correlation with browser logs only; it is on
        # the browser's clock, so it is never subtracted from a server time.
        log.info(
            "session %s: flush acked for turn %s, round trip %.3f ms (client_ts=%.1f)",
            self.session_id,
            turn_id,
            round_trip_ms,
            ack.client_ts,
        )
        return round_trip_ms
