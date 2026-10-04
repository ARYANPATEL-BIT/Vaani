"""One session's turns: VAD -> endpointing -> turns -> ASR -> reply.

The gateway validates a frame and hands it to `TurnPipeline.on_frame`. From
there, in order:
  1. VAD (vad.py) says whether speech started or ended on this frame;
  2. the Endpointer (endpoint.py) decides whether the user's turn is over;
  3. turns open and close here. A TURN IS ONE USER UTTERANCE: its turn_id is
     created when speech starts, so partial transcripts, the final
     transcript, any echo audio and the agent's reply all carry the same id;
  4. ASR (asr/runner.py) is asked for partials while the user speaks and for
     the final when the turn ends — asked only: recognition never runs here;
  5. the final transcript goes to reply.py, which streams the model's answer;
  6. echo (echo.py; day 3, development only) sends the turn's frames back.

Everything in on_frame is quick: VAD is ~1 ms, the rest microseconds. The
slow steps, recognition and the model, run as background tasks, so the frame
loop never waits for them.

The TURN STATE MACHINE (day 11) is what the agent is doing, as one value:
idle, listening, thinking, speaking or cancelling. `_LEGAL` lists every
allowed move; `move_to` is the only way to change state, raises on anything
else, and sends turn.state to the browser.

The system is HALF-DUPLEX today: while the agent is thinking, speaking or
cancelling, user speech is detected but dropped (`_drop_overlap`), not
endpointed. Week-3 barge-in replaces that one method.
"""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from vaani.asr import Recognizer
from vaani.asr.runner import AsrRunner
from vaani.config import Settings
from vaani.echo import Echo
from vaani.endpoint import Endpointer, TurnEnded, ms_to_frames
from vaani.protocol import TurnState, turn_state
from vaani.providers.base import LLMProvider
from vaani.reply import Responder
from vaani.session import Session
from vaani.telemetry import TURN_ENDED, Telemetry
from vaani.vad import SPEECH_ENDED, SPEECH_STARTED, SpeechEvent, VadStream

log = logging.getLogger("vaani.turns")

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]

# Every legal move, and nothing else. An unlisted move is a bug in the
# caller, so it raises instead of quietly happening.
_LEGAL: dict[TurnState, set[TurnState]] = {
    TurnState.IDLE: {TurnState.LISTENING},  # speech started: a turn opens
    # Turn over -> thinking. Too short, flushed, or no model -> idle.
    TurnState.LISTENING: {TurnState.THINKING, TurnState.IDLE},
    # First reply text -> speaking; failed or nothing to say -> idle.
    TurnState.THINKING: {TurnState.SPEAKING, TurnState.IDLE, TurnState.CANCELLING},
    # Reply done or failed -> idle; dev.flush -> cancelling.
    TurnState.SPEAKING: {TurnState.IDLE, TurnState.CANCELLING},
    # dev.flush (no speech caused it) -> idle. Week-3 barge-in (the user's
    # speech caused it and already opened the new turn) -> listening.
    TurnState.CANCELLING: {TurnState.IDLE, TurnState.LISTENING},
}


class IllegalTransition(Exception):
    """A move `_LEGAL` does not allow was attempted."""


def check_transition(current: TurnState, new: TurnState) -> None:
    """Raise IllegalTransition unless current -> new is in `_LEGAL`."""
    if new not in _LEGAL[current]:
        raise IllegalTransition(f"{current} -> {new}")


class TurnPipeline:
    """One session's frame-by-frame processing. Built on session.start."""

    def __init__(
        self,
        settings: Settings,
        session: Session,
        telemetry: Telemetry,
        send_json: SendJson,
        send_bytes: SendBytes,
        vad_model,
        recognizer: Recognizer | None,
        chain: LLMProvider | None,
    ) -> None:
        self._session = session
        self._telemetry = telemetry
        self._send_json = send_json
        self._frame_ms = settings.audio.frame_ms
        self._echo = Echo(
            settings.gateway.echo_enabled, session, telemetry, send_json, send_bytes
        )
        # Each stage needs the one before it: no VAD, no endpointing; no
        # endpointing (no utterances), nothing to transcribe; no transcript
        # (or no model), nothing to answer.
        self._vad = (
            VadStream(vad_model, settings.vad, settings.audio)
            if settings.vad.enabled
            else None
        )
        self._endpointer = (
            Endpointer(settings.endpoint, self._frame_ms, session.session_id)
            if self._vad is not None and settings.endpoint.enabled
            else None
        )
        self._asr = (
            AsrRunner(recognizer, settings.asr, send_json, telemetry, self._on_final)
            if self._endpointer is not None and recognizer is not None
            else None
        )
        self._responder = (
            Responder(chain, settings, session, telemetry, send_json, self.move_to)
            if self._asr is not None and chain is not None
            else None
        )
        self.state = TurnState.IDLE
        # perf_counter of the last turn_ended, for the first-token log line.
        self._ended_at = 0.0
        # speech_started of user speech being dropped (agent busy), until
        # its speech_ended.
        self._overlap: SpeechEvent | None = None
        # Partial re-decode interval in frames; 0 = partials off.
        interval = settings.asr.partial_interval_ms
        self._partial_frames = ms_to_frames(interval, self._frame_ms) if interval else 0
        # frames_since_start at which the last partial was requested.
        self._last_partial_at = 0

    async def on_frame(self, data: bytes) -> None:
        """Process one valid frame. Must be called for every frame, in order."""
        speech_event = None
        if self._vad is not None:
            # Plain synchronous CPU work on the event loop: while it runs,
            # every session on this loop waits, so its cost is timed per frame.
            vad_started = perf_counter()
            speech_event = self._vad.push(data)
            self._telemetry.record_vad_decision(vad_started)
            if speech_event is not None:
                log.info(
                    "session %s: %s at frame %d (%.2fs into audio)",
                    self._session.session_id,
                    speech_event.kind,
                    speech_event.frame_index,
                    (speech_event.frame_index + 1) * self._frame_ms / 1000,
                )
        if self._endpointer is not None:
            # THE ROUTING SEAM: who gets the user's speech right now.
            if (
                self.state in (TurnState.IDLE, TurnState.LISTENING)
                and self._overlap is None
            ):
                await self._endpoint(data, speech_event)
            else:
                self._drop_overlap(speech_event)
        await self._echo.frame(data)

    async def on_dev_flush(self) -> None:
        """dev.flush: stop the agent's reply if there is one; otherwise flush
        the user's open turn (day 4) and abandon its recognition."""
        if self.state in (TurnState.THINKING, TurnState.SPEAKING):
            await self._cancel_reply()
            return
        flushed = await self._session.flush(self._send_json, self._telemetry)
        if flushed is not None and self._asr is not None:
            self._asr.abandon_turn(flushed)

    async def on_session_end(self) -> None:
        """Clean session.end: close the open echo turn before the socket."""
        await self._echo.end()

    async def close(self) -> None:
        """Session over, cleanly or not. Sends nothing: the socket may be gone."""
        if self._responder is not None:
            self._responder.cancel()
            try:
                await self._responder.wait()  # its HTTP stream is closed after
            except Exception:
                # Typically a send on the socket that has just closed.
                log.exception("session %s: reply ended badly", self._session.session_id)
        if self._asr is not None:
            await self._asr.close()
        if self._endpointer is not None:
            self._endpointer.close()

    async def move_to(self, new: TurnState) -> None:
        """The ONLY way the state changes: check, record, tell the browser.

        Recorded BEFORE the send, like a flush mark: anything that runs during
        the send's await must already see the new state.
        """
        check_transition(self.state, new)
        old, self.state = self.state, new
        turn_id = None if new is TurnState.IDLE else self._session.current_turn_id
        log.info("session %s: %s -> %s", self._session.session_id, old, new)
        await self._send_json(turn_state(turn_id, new))

    # --- Routing -------------------------------------------------------------

    async def _endpoint(self, data: bytes, speech_event: SpeechEvent | None) -> None:
        """Agent not busy: the user's speech opens and ends turns."""
        ep = self._endpointer
        assert ep is not None  # on_frame routes here only when it exists
        was_open = ep.utterance_open
        turn = ep.push(data, speech_event)
        if turn is not None:
            await self._end_turn(turn)
        elif was_open and not ep.utterance_open:
            await self._discard_turn()  # shorter than min_utterance_ms
        # Opens on speech_started, and again straight after a forced end
        # (max_utterance_ms) - unless that end just made the agent busy.
        if (
            ep.utterance_open
            and not self._session.turn_open
            and self.state is TurnState.IDLE
        ):
            await self._open_turn()
        self._maybe_request_partial()

    def _drop_overlap(self, speech_event: SpeechEvent | None) -> None:
        """Agent busy, no barge-in yet: drop the user's speech, and log it.

        Week 3 replaces this body with barge-in. The logs count how often
        users talk over the agent. Once a drop starts, the whole utterance is
        dropped, even if the agent goes idle first: half an utterance must
        not become a turn.
        """
        if speech_event is None:
            return
        sid = self._session.session_id
        if speech_event.kind == SPEECH_STARTED:
            self._overlap = speech_event
            log.info(
                "session %s: speech dropped while %s (half-duplex)", sid, self.state
            )
        elif speech_event.kind == SPEECH_ENDED and self._overlap is not None:
            ms = (speech_event.frame_index - self._overlap.frame_index) * self._frame_ms
            log.info("session %s: dropped speech lasted %d ms", sid, ms)
            self._overlap = None

    # --- Turn lifecycle ----------------------------------------------------

    async def _open_turn(self) -> None:
        turn_id = self._session.open_turn()
        self._last_partial_at = 0
        log.info("session %s: turn %s opened", self._session.session_id, turn_id)
        await self.move_to(TurnState.LISTENING)
        await self._echo.start(turn_id)

    async def _end_turn(self, turn: TurnEnded) -> None:
        turn_id = self._session.current_turn_id
        assert turn_id is not None  # a turn ends only after one opened
        self._telemetry.record(TURN_ENDED, turn_id)
        self._ended_at = turn.at
        waited = (
            "forced"
            if turn.speech_ended_at is None
            else f"waited {(turn.at - turn.speech_ended_at) * 1000:.0f} ms"
        )
        log.info(
            "session %s: turn_ended turn %s frames %d-%d, %d ms, "
            "%d frames buffered (%s)",
            self._session.session_id,
            turn_id,
            turn.start_frame,
            turn.end_frame,
            turn.duration_ms,
            turn.frame_count,
            waited,
        )
        await self._echo.end()
        self._session.close_turn()
        # A flushed (interrupted) turn gets no transcript: on_dev_flush already
        # abandoned its recognition, and nothing may restart it.
        if self._asr is None or self._session.is_flushed(turn_id):
            await self.move_to(TurnState.IDLE)
            return
        # Thinking only if a model will answer. Without one the transcript is
        # still sent, but the agent itself is idle.
        await self.move_to(
            TurnState.THINKING if self._responder is not None else TurnState.IDLE
        )
        self._asr.request_final(turn_id, turn.audio, turn.duration_ms, turn.at)

    async def _discard_turn(self) -> None:
        turn_id = self._session.current_turn_id
        assert turn_id is not None
        log.info(
            "session %s: turn %s discarded (too short)",
            self._session.session_id,
            turn_id,
        )
        await self._echo.end()
        self._session.close_turn()
        if self._asr is not None:
            self._asr.abandon_turn(turn_id)
        await self.move_to(TurnState.IDLE)

    # --- Reply lifecycle ---------------------------------------------------

    async def _on_final(self, turn_id: str, text: str | None) -> None:
        """AsrRunner's hand-over. `text` is None if transcription failed (the
        runner already sent ASR_FAILED). Must return quickly."""
        if self._responder is None:
            return  # no model: the turn already went idle
        if text is None or not text.strip():
            await self.move_to(TurnState.IDLE)  # failed, or heard nothing to answer
            return
        self._responder.start(turn_id, text, self._ended_at)

    async def _cancel_reply(self) -> None:
        """Thinking or speaking -> cancelling -> idle."""
        started = perf_counter()
        turn_id = self._session.current_turn_id
        assert self._responder is not None  # thinking/speaking need one
        # Token FIRST, before any await: the reply checks it before every
        # send, so from here on nothing more is sent for this turn.
        self._responder.cancel()
        # Still transcribing? Then no transcript, and so no reply, will come.
        if self._asr is not None and turn_id is not None:
            self._asr.abandon_turn(turn_id)
        await self.move_to(TurnState.CANCELLING)
        await self._responder.wait()  # returns once the HTTP stream is closed
        ms = (perf_counter() - started) * 1000
        log.info("session %s: reply cancelled in %.1f ms", self._session.session_id, ms)
        # Idle, not listening: dev.flush has no speech behind it, and a turn
        # id is created by speech starting, and by nothing else.
        await self.move_to(TurnState.IDLE)

    def _maybe_request_partial(self) -> None:
        """Ask for a partial every `partial_interval_ms` of an utterance.

        Only while the user is actively speaking (a re-decode in the silence
        window would hear nothing new) and only once the utterance is longer
        than min_utterance_ms. The utterance then cannot be discarded as too
        short later, so the browser never shows a partial whose turn vanishes.
        """
        ep = self._endpointer
        if self._asr is None or not self._partial_frames or ep is None:
            return
        frames = ep.frames_since_start
        turn_id = self._session.current_turn_id
        if not ep.speaking or frames < ep.min_frames or turn_id is None:
            return
        if self._session.is_flushed(turn_id):
            return
        if frames - self._last_partial_at >= self._partial_frames:
            self._last_partial_at = frames
            self._asr.request_partial(turn_id, ep.snapshot())
