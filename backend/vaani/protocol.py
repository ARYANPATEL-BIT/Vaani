"""WebSocket message protocol for Vaani — the single home for message shapes.

Every message that crosses the client/server WebSocket connection is defined
here and NOWHERE else. Centralising the wire format means there is exactly one
place to look when asking "what can the client send?" or "what can the server
send back?", and one place to change when the protocol evolves.

This is SHARED PROTOCOL v0.7. The same shapes are mirrored on the frontend.
Version numbers come from docs/contracts.md, the source of truth; the
history below repeats its version table, and only the PR that changes
contracts.md bumps the version.

Two kinds of traffic flow over the socket, in BOTH directions:
  * Audio frames are raw BINARY messages (mono 16-bit little-endian PCM).
    They carry no JSON and are NOT modelled here. Browser-to-server audio is
    16 kHz, validated by length. Server-to-browser audio is at the rate its
    audio.start declares (v0.6).
  * Control messages are JSON TEXT messages, each with a "type" field. Those
    are the models below.

v0.1 is the initial protocol: session.start, session.started, session.end,
error, and 640-byte 16 kHz mic frames.

v0.2 adds server-to-browser audio: the server may now send audio frames back,
bracketed by audio.start / audio.end control messages that carry a turn_id.
A turn_id is a server-generated string, unique within a session. Every audio
frame the browser receives belongs to the most recent audio.start.

v0.2 also adds FLUSH: the server sends audio.flush to silence a turn at once,
and the browser replies flush.ack as soon as its audio has stopped. A flushed
turn gets no audio.end — the flush IS its ending. Frames the browser receives
for a flushed turn_id must be discarded, not played. dev.flush (dev only)
asked the server to flush; v0.7 removed it.

v0.3 adds TRANSCRIPTS: transcript.partial (zero or more while the user is
still speaking; each REPLACES the previous partial for that turn_id) and
transcript.final (once per turn, after endpointing; replaces the partial). A
final may arrive with no partial before it, and may differ from the last
partial. A turn is one user utterance: its turn_id is created when speech
starts, so partials, the final, and any echo audio share it. ASR_FAILED is
proposed.

v0.4 adds the AGENT'S SIDE: turn.state (sent on every state change of the
turn state machine in turns.py), agent.text (one streamed fragment of the
reply; APPEND these, unlike transcript.partial which replaces) and agent.done
(the full reply). A failed turn gets an error and then turn.state idle, never
agent.done; a cancelled turn gets no agent.done either. Adds LLM_FAILED and
INPUT_REJECTED.

v0.5 adds TELEMETRY for the frontend's Latency HUD (contracts.md 2.6). The
backend does not send it yet, so there is NO model for it in this file.

v0.6 makes the agent AUDIBLE: its reply is synthesised and sent as audio
frames between audio.start and audio.end, the same route the echo used.
audio.start now carries `sample_rate`: the rate of every frame until the
matching audio.end (22050 for the Piper voice, 16000 for echo). turn.state
`speaking` now means the agent's AUDIO has started, not its text, so
agent.text deltas arrive while the state is still `thinking`. A reply whose
synthesis fails gets audio.end (if audio had started), TTS_FAILED, then idle.

v0.7 is BARGE-IN, and adds no message. Speech while the agent is thinking or
speaking stops it: audio.flush for the agent's turn FIRST, then turn.state
cancelling, then turn.state listening with a NEW turn_id. Because of that,
audio.flush can now come during thinking (no audio.start before it), after
agent.done, or after audio.end (the audio was sent but is still playing), and
the flush.ack for it arrives when a newer turn is already current: the server
accepts it. dev.flush is removed: an unknown type now.

Pydantic models are used because they validate incoming JSON for us: if the
client sends the wrong shape, constructing the model raises instead of letting
a malformed message through.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class ErrorCode(StrEnum):
    """The fixed set of error codes the server may report.

    These are stable strings, not free text, so the client can branch on them
    reliably. StrEnum (Python 3.11+) means each member IS its wire string, so it
    serialises straight to JSON as e.g. "BAD_FRAME_SIZE".
    """

    SESSION_NOT_STARTED = "SESSION_NOT_STARTED"  # data before session.start
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"  # audio settings mismatch
    BAD_FRAME_SIZE = "BAD_FRAME_SIZE"  # binary frame not the expected length
    BAD_MESSAGE = "BAD_MESSAGE"  # not valid JSON, or no "type"
    UNKNOWN_MESSAGE_TYPE = "UNKNOWN_MESSAGE_TYPE"  # a "type" we do not handle
    ASR_FAILED = "ASR_FAILED"  # a turn's final transcript could not be produced
    LLM_FAILED = "LLM_FAILED"  # the agent could not answer
    INPUT_REJECTED = "INPUT_REJECTED"  # the turn was blocked before the model
    TTS_FAILED = "TTS_FAILED"  # the reply could not be spoken


class TurnState(StrEnum):
    """What the agent is doing, as sent in turn.state.

    Lives here, beside ErrorCode, because these five strings are wire values
    the frontend must match. WHICH moves between them are legal is decided
    in turns.py, not here.
    """

    IDLE = "idle"  # nothing in progress; turn_id is null
    LISTENING = "listening"  # the user is speaking
    THINKING = "thinking"  # turn over; transcribing and waiting for the model
    SPEAKING = "speaking"  # the reply's audio is being sent and played
    CANCELLING = "cancelling"  # reply being stopped by a barge-in


# --- Client -> server -------------------------------------------------------


class AudioParams(BaseModel):
    """Audio format the client claims it will send, inside session.start."""

    sample_rate: int
    channels: int
    frame_ms: int


class SessionStart(BaseModel):
    """Opens a session. The client must send this and receive session.started
    before sending any audio frames."""

    type: Literal["session.start"]
    persona: str = "default"
    audio: AudioParams


class SessionEnd(BaseModel):
    """Closes a session cleanly. The server ends the session and closes the
    socket with a normal (1000) close code."""

    type: Literal["session.end"]


class FlushAck(BaseModel):
    """The browser's reply to audio.flush, sent once its audio has stopped.

    `client_ts` is the browser's own monotonic time in milliseconds
    (performance.now()). The server logs it but never subtracts it from a
    server timestamp: the two clocks start at different moments, so their
    difference is meaningless. The round trip is timed on the server clock.
    """

    type: Literal["flush.ack"]
    turn_id: str
    client_ts: float


# --- Server -> client -------------------------------------------------------


class SessionStarted(BaseModel):
    """Acknowledges a session and hands the client its session id."""

    type: Literal["session.started"] = "session.started"
    session_id: str


class ErrorMessage(BaseModel):
    """A non-fatal problem report. The connection stays open after one."""

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


class AudioStart(BaseModel):
    """Marks the start of a turn's audio. Sent before that turn's first audio
    frame. Every frame the browser then receives belongs to this turn until the
    matching audio.end (or the socket closes), and is `sample_rate` samples
    per second."""

    type: Literal["audio.start"] = "audio.start"
    turn_id: str
    sample_rate: int


class AudioEnd(BaseModel):
    """Marks the end of a turn's audio. Sent after that turn's last frame."""

    type: Literal["audio.end"] = "audio.end"
    turn_id: str


class AudioFlush(BaseModel):
    """Tells the browser to silence a turn immediately: stop all scheduled
    audio, drop every queued frame for that turn, fade out within 10 ms, and
    reply with flush.ack. Replaces audio.end for that turn, or follows it if
    the turn's audio was all sent but is still playing (v0.7)."""

    type: Literal["audio.flush"] = "audio.flush"
    turn_id: str


class TranscriptPartial(BaseModel):
    """Best guess so far at what the user is saying, sent while they speak.
    Replaces (does not append to) the previous partial for the same turn."""

    type: Literal["transcript.partial"] = "transcript.partial"
    turn_id: str
    text: str


class TranscriptFinal(BaseModel):
    """The turn's transcript, sent once after the turn ends.

    `duration_ms` is the length of the user's speech in the turn (endpointing's
    speech_started..speech_ended span). `language` is the language the
    recogniser reports, or None if it does not say. Today it is always the
    forced language from config, not a detection.
    """

    type: Literal["transcript.final"] = "transcript.final"
    turn_id: str
    text: str
    duration_ms: int
    language: str | None


class TurnStateMessage(BaseModel):
    """The agent's state changed. turn_id is None (JSON null) only in idle."""

    type: Literal["turn.state"] = "turn.state"
    turn_id: str | None
    state: TurnState


class AgentText(BaseModel):
    """One streamed fragment of the agent's reply. The browser APPENDS it."""

    type: Literal["agent.text"] = "agent.text"
    turn_id: str
    delta: str


class AgentDone(BaseModel):
    """The reply is complete. `text` is the whole reply, for the scrollback."""

    type: Literal["agent.done"] = "agent.done"
    turn_id: str
    text: str


# --- Helpers for the server to build outgoing JSON --------------------------


def session_started(session_id: str) -> dict:
    """Build the session.started payload for `websocket.send_json`."""
    return SessionStarted(session_id=session_id).model_dump(mode="json")


def error(code: ErrorCode, message: str) -> dict:
    """Build an error payload for `websocket.send_json`.

    `mode="json"` turns the ErrorCode enum into its plain string value so the
    wire message is exactly {"type": "error", "code": "...", "message": "..."}.
    """
    return ErrorMessage(code=code, message=message).model_dump(mode="json")


def audio_start(turn_id: str, sample_rate: int) -> dict:
    """Build the audio.start payload for `websocket.send_json`."""
    return AudioStart(turn_id=turn_id, sample_rate=sample_rate).model_dump(mode="json")


def audio_end(turn_id: str) -> dict:
    """Build the audio.end payload for `websocket.send_json`."""
    return AudioEnd(turn_id=turn_id).model_dump(mode="json")


def audio_flush(turn_id: str) -> dict:
    """Build the audio.flush payload for `websocket.send_json`."""
    return AudioFlush(turn_id=turn_id).model_dump(mode="json")


def transcript_partial(turn_id: str, text: str) -> dict:
    """Build the transcript.partial payload for `websocket.send_json`."""
    return TranscriptPartial(turn_id=turn_id, text=text).model_dump(mode="json")


def transcript_final(
    turn_id: str, text: str, duration_ms: int, language: str | None
) -> dict:
    """Build the transcript.final payload for `websocket.send_json`."""
    return TranscriptFinal(
        turn_id=turn_id, text=text, duration_ms=duration_ms, language=language
    ).model_dump(mode="json")


def turn_state(turn_id: str | None, state: TurnState) -> dict:
    """Build the turn.state payload for `websocket.send_json`."""
    return TurnStateMessage(turn_id=turn_id, state=state).model_dump(mode="json")


def agent_text(turn_id: str, delta: str) -> dict:
    """Build the agent.text payload for `websocket.send_json`."""
    return AgentText(turn_id=turn_id, delta=delta).model_dump(mode="json")


def agent_done(turn_id: str, text: str) -> dict:
    """Build the agent.done payload for `websocket.send_json`."""
    return AgentDone(turn_id=turn_id, text=text).model_dump(mode="json")
