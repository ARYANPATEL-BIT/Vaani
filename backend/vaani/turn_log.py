"""One database row per session and per turn (the SQL itself is in db.py).

A TurnLog belongs to one session; TurnPipeline (turns.py) builds it, which
records the session's row. From then on it writes one row per turn, at the
moment the turn is over. That moment is always a move of the turn state
machine (turn_state.py): to `idle` (the turn ended: replied, failed or
empty) or to `cancelling` (a barge-in cut it). So `state_changed`, called by
`TurnStateMachine.move_to` on every move, is the one place rows are made.
A turn still live when the socket closes is written by `session_closed`.

A turn is over only after its first audio, so no row is ever built between
the end of the user's speech and the first audio frame of the reply.

Where a row's values come from, all read at that moment:
  * the reply side (what the model was asked, what it said, what the user
    heard, provider, error): the ReplyRecord reply.py fills in as it goes;
  * the timings: the turn's telemetry spans (telemetry.py);
  * the scripts: vaani/language.py's rule, Devanagari or not.

Building a row is dictionary reads plus one queue put, on the event loop.
The write itself happens later, on the database thread (db.DbWriter).
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from vaani.db import DbWriter
from vaani.language import reply_language
from vaani.protocol import ErrorCode, TurnState
from vaani.session import Session
from vaani.telemetry import (
    ASR_FAILED,
    ASR_FINAL,
    ASR_START,
    LLM_FIRST_TOKEN,
    LLM_REQUEST,
    SPEECH_END,
    TTS_FIRST_AUDIO,
    TTS_START,
    Telemetry,
)

log = logging.getLogger("vaani.turn_log")

# (column, from span, to span): each stage is the gap between two spans.
STAGES = (
    ("end_to_asr_ms", SPEECH_END, ASR_FINAL),
    ("asr_ms", ASR_START, ASR_FINAL),
    ("llm_first_token_ms", LLM_REQUEST, LLM_FIRST_TOKEN),
    ("tts_first_chunk_ms", TTS_START, TTS_FIRST_AUDIO),
    ("end_to_first_audio_ms", SPEECH_END, TTS_FIRST_AUDIO),
)


@dataclass
class ReplyRecord:
    """What one reply did. reply.py makes one per reply and fills it in."""

    turn_id: str
    transcript: str  # what the model was asked to answer
    parts: list[str] = field(default_factory=list)  # every delta received
    provider: str | None = None  # from the first delta
    model: str | None = None
    error: ErrorCode | None = None  # the error this reply sent, if any
    heard: str | None = None  # what went into history; None: nothing did


def utc_now() -> str:
    """Wall-clock time for started_at / ended_at, UTC, to the millisecond.

    A date, not a duration: durations use perf_counter, which has no date.
    """
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class TurnLog:
    """Writes one session's rows. Built by TurnPipeline at session.start."""

    def __init__(self, db: DbWriter, session: Session, telemetry: Telemetry, responder):
        self._db = db
        self._session = session
        self._telemetry = telemetry
        # The session's Responder (reply.py): its `record` and `speaker` are
        # the latest reply's. Not type-annotated: reply.py imports this file.
        self._responder = responder
        self._index = 0  # rows written so far: the next row's turn_index - 1
        db.insert_session(
            {
                "id": session.session_id,
                "started_at": utc_now(),
                "persona": session.persona,
                "mode": session.mode,
            }
        )

    def state_changed(self, old: TurnState, new: TurnState) -> None:
        """TurnStateMachine.move_to calls this on EVERY move, on the event
        loop, after the new state is set and before turn.state is sent.

        It must never raise: an exception here would break the turn the
        user is in. So any failure is logged (its type only, never the
        row's text) and the row is lost.
        """
        try:
            if new is TurnState.CANCELLING:
                self._write("cut")
            elif new is TurnState.IDLE:
                self._write(None)
        except Exception as exc:
            log.warning(
                "session %s: turn row not recorded: %s",
                self._session.session_id,
                type(exc).__name__,
            )

    def session_closed(self, reason: str, state: TurnState) -> None:
        """The socket closed. `state` is where the turn state machine stopped:
        anything but idle means a turn was still live, recorded as closed."""
        try:
            if state is not TurnState.IDLE:
                self._write("closed")
            self._db.end_session(
                {
                    "id": self._session.session_id,
                    "ended_at": utc_now(),
                    "end_reason": reason,
                }
            )
        except Exception as exc:
            log.warning(
                "session %s: close not recorded: %s",
                self._session.session_id,
                type(exc).__name__,
            )

    def _write(self, outcome: str | None) -> None:
        """Queue the current turn's row. `outcome` None: worked out here."""
        turn_id = self._session.current_turn_id
        reply = self._responder.record
        if reply is not None and reply.turn_id != turn_id:
            reply = None  # no reply was started for this turn
        speaker = self._responder.speaker if reply is not None else None
        spans = self._telemetry.pop_turn(turn_id)
        error = reply.error if reply is not None else None
        if error is None and ASR_FAILED in spans:
            error = ErrorCode.ASR_FAILED
        if outcome is None:
            if reply is not None and reply.heard is not None:
                outcome = "replied"
            elif error is not None:
                outcome = "failed"
            else:
                outcome = "empty"  # too short, an empty press, nothing heard
        self._index += 1
        row = {
            "id": turn_id,
            "session_id": self._session.session_id,
            "turn_index": self._index,
            "outcome": outcome,
            "user_text": reply.transcript if reply else None,
            "user_script": reply_language(reply.transcript) if reply else None,
            # The first chunk's SCRIPT, as schema.sql says, not the voice: in
            # a forced session (v0.10) the voice can be the other language.
            "reply_script": speaker.first_script if speaker else None,
            "reply_generated": "".join(reply.parts) if reply and reply.parts else None,
            "reply_heard": reply.heard if reply else None,
            "llm_provider": reply.provider if reply else None,
            "llm_model": reply.model if reply else None,
            # .value: the plain string, as the browser got it.
            "error_code": error.value if error is not None else None,
        }
        for column, start, end in STAGES:
            both = start in spans and end in spans
            row[column] = (spans[end] - spans[start]) * 1000 if both else None
        self._db.insert_turn(row)
