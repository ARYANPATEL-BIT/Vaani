"""WebSocket message protocol for Vaani — the single home for message shapes.

Every message that crosses the client/server WebSocket connection is defined
here and NOWHERE else. Centralising the wire format means there is exactly one
place to look when asking "what can the client send?" or "what can the server
send back?", and one place to change when the protocol evolves.

This is SHARED PROTOCOL v0.2. The same shapes are mirrored on the frontend.

Two kinds of traffic flow over the socket, in BOTH directions:
  * Audio frames are raw BINARY messages (16 kHz mono 16-bit PCM). They carry
    no JSON and are NOT modelled here — they are just bytes validated by length.
    Server-to-browser audio has the same format as client-to-server audio.
  * Control messages are JSON TEXT messages, each with a "type" field. Those
    are the models below.

v0.2 adds server-to-browser audio: the server may now send audio frames back,
bracketed by audio.start / audio.end control messages that carry a turn_id.
A turn_id is a server-generated string, unique within a session. Every audio
frame the browser receives belongs to the most recent audio.start.

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
    matching audio.end (or the socket closes)."""

    type: Literal["audio.start"] = "audio.start"
    turn_id: str


class AudioEnd(BaseModel):
    """Marks the end of a turn's audio. Sent after that turn's last frame."""

    type: Literal["audio.end"] = "audio.end"
    turn_id: str


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


def audio_start(turn_id: str) -> dict:
    """Build the audio.start payload for `websocket.send_json`."""
    return AudioStart(turn_id=turn_id).model_dump(mode="json")


def audio_end(turn_id: str) -> dict:
    """Build the audio.end payload for `websocket.send_json`."""
    return AudioEnd(turn_id=turn_id).model_dump(mode="json")
