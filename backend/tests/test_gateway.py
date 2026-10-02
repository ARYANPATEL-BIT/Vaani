"""Tests for the /ws/session WebSocket gateway.

Uses FastAPI's TestClient, whose `websocket_connect` opens a real in-process
WebSocket. Each test drives the protocol from the client side and asserts on
what the server sends back and whether the connection stays open.
"""

import logging
import time
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

import vaani.turns as turns_mod
from vaani.app import create_app
from vaani.config import GatewaySettings, Settings
from vaani.gateway import expected_frame_bytes
from vaani.vad import SPEECH_STARTED, SpeechEvent

# The audio block every valid session.start must carry to match the server.
GOOD_AUDIO = {"sample_rate": 16000, "channels": 1, "frame_ms": 20}
START = {"type": "session.start", "persona": "default", "audio": GOOD_AUDIO}


class SpeechOnFirstFrame:
    """Stand-in VadStream: speech_started on the very first frame, then never
    another event. Echo is turn-scoped (a turn is one utterance), so a turn
    must open before anything is echoed; this opens one at once, keeping these
    tests about echo and flush rather than about the Silero model."""

    def __init__(self, *args) -> None:
        self._frames = 0

    def push(self, frame: bytes) -> SpeechEvent | None:
        self._frames += 1
        if self._frames == 1:
            return SpeechEvent(SPEECH_STARTED, 0, perf_counter())
        return None


@pytest.fixture(autouse=True)
def speech_on_first_frame(monkeypatch) -> None:
    monkeypatch.setattr(turns_mod, "VadStream", SpeechOnFirstFrame)


def make_client(interval_s: float = 1.0, echo_enabled: bool = True) -> TestClient:
    """Build a TestClient over an app whose gateway settings we control."""
    settings = Settings(
        gateway=GatewaySettings(
            frame_log_interval_s=interval_s, echo_enabled=echo_enabled
        )
    )
    return TestClient(create_app(settings))


def good_frame() -> bytes:
    """One correctly sized silent frame (640 zero bytes for the defaults)."""
    return b"\x00" * expected_frame_bytes(Settings().audio)


def distinct_frame() -> bytes:
    """A correctly sized frame with recognisable, non-zero content, so an echo
    test proves the exact bytes came back rather than any zero-filled frame."""
    size = expected_frame_bytes(Settings().audio)
    return bytes(i % 256 for i in range(size))


def test_session_start_returns_started_with_id() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        reply = ws.receive_json()

    assert reply["type"] == "session.started"
    assert isinstance(reply["session_id"], str) and reply["session_id"]


def test_frame_before_start_returns_session_not_started() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_bytes(good_frame())
        reply = ws.receive_json()

    assert reply["type"] == "error"
    assert reply["code"] == "SESSION_NOT_STARTED"


def test_text_before_start_returns_session_not_started() -> None:
    """Any control message other than session.start, sent first, is rejected."""
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json({"type": "session.end"})
        reply = ws.receive_json()

    assert reply["code"] == "SESSION_NOT_STARTED"


def test_wrong_size_frame_returns_bad_frame_size_and_stays_open() -> None:
    # Echo off so the good frame below draws no audio.start/echo to drain — this
    # test is about frame-size validation and the socket staying usable.
    with make_client(echo_enabled=False).websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()  # session.started

        ws.send_bytes(b"\x00" * 100)  # wrong length
        reply = ws.receive_json()
        assert reply["code"] == "BAD_FRAME_SIZE"

        # Connection is still usable: a good frame afterwards draws no error.
        ws.send_bytes(good_frame())
        ws.send_json(START)  # idempotent re-ack proves the socket is alive
        assert ws.receive_json()["type"] == "session.started"


def test_invalid_json_returns_bad_message() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_text("this is not json{")
        reply = ws.receive_json()

    assert reply["code"] == "BAD_MESSAGE"


def test_unknown_type_returns_unknown_message_type() -> None:
    """Unknown types are only reachable after a session exists (before that,
    session-gating returns SESSION_NOT_STARTED)."""
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()  # session.started

        ws.send_json({"type": "does.not.exist"})
        reply = ws.receive_json()

    assert reply["code"] == "UNKNOWN_MESSAGE_TYPE"


def test_mismatched_audio_returns_unsupported_format() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        bad = {"type": "session.start", "audio": {**GOOD_AUDIO, "sample_rate": 8000}}
        ws.send_json(bad)
        reply = ws.receive_json()

    assert reply["code"] == "UNSUPPORTED_FORMAT"


def test_second_start_reacks_same_session_id() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        first = ws.receive_json()

        ws.send_json(START)
        second = ws.receive_json()

    assert first["type"] == second["type"] == "session.started"
    assert first["session_id"] == second["session_id"]  # no new session created


def test_session_end_closes_with_1000() -> None:
    from starlette.websockets import WebSocketDisconnect

    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()

        ws.send_json({"type": "session.end"})
        # After a normal close the next receive raises with the close code.
        try:
            ws.receive_json()
            raised = None
        except WebSocketDisconnect as exc:
            raised = exc

    assert raised is not None
    assert raised.code == 1000


def test_echo_returns_same_bytes_after_audio_start() -> None:
    """A valid frame comes back unchanged, preceded by audio.start."""
    frame = distinct_frame()
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()  # session.started

        ws.send_bytes(frame)
        start = ws.receive_json()  # audio.start precedes the first frame
        echoed = ws.receive_bytes()

    assert start["type"] == "audio.start"
    assert isinstance(start["turn_id"], str) and start["turn_id"]
    assert echoed == frame  # exact same bytes returned


def test_audio_start_sent_once_for_the_session() -> None:
    """Only the turn's first echoed frame is preceded by audio.start; later
    frames of the same turn are bare binary."""
    frame = distinct_frame()
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()

        ws.send_bytes(frame)
        start = ws.receive_json()
        ws.receive_bytes()  # first echo

        ws.send_bytes(frame)
        second = ws.receive_bytes()  # second echo, no audio.start before it

    assert start["type"] == "audio.start"
    assert second == frame


def test_audio_end_sent_on_session_end_with_same_turn_id() -> None:
    from starlette.websockets import WebSocketDisconnect

    frame = distinct_frame()
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()

        ws.send_bytes(frame)
        start = ws.receive_json()  # audio.start
        ws.receive_bytes()  # echoed frame

        ws.send_json({"type": "session.end"})
        end = ws.receive_json()  # audio.end before the socket closes
        try:
            ws.receive_json()
            raised = None
        except WebSocketDisconnect as exc:
            raised = exc

    assert end["type"] == "audio.end"
    assert end["turn_id"] == start["turn_id"]  # the turn still open at session end
    assert raised is not None and raised.code == 1000


def test_no_audio_end_when_no_frames_were_echoed() -> None:
    """A session that ends without ever sending a frame owes no audio.end."""
    from starlette.websockets import WebSocketDisconnect

    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()

        ws.send_json({"type": "session.end"})
        # No audio.start was ever sent, so the very next event is the close.
        try:
            ws.receive_json()
            raised = None
        except WebSocketDisconnect as exc:
            raised = exc

    assert raised is not None and raised.code == 1000


def test_echo_disabled_returns_no_audio() -> None:
    """With echo off, a valid frame draws no reply; the socket stays usable."""
    with make_client(echo_enabled=False).websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()

        ws.send_bytes(distinct_frame())
        # Prove nothing was echoed: the next server message is the idempotent
        # session.started re-ack, not an audio.start.
        ws.send_json(START)
        reply = ws.receive_json()

    assert reply["type"] == "session.started"


def test_valid_frames_are_counted(caplog) -> None:
    """With a tiny log interval, the per-interval logger reports the frames we
    sent. We check the logs (no multi-second wait), summing the counts."""
    client = make_client(interval_s=0.02)
    frame = good_frame()

    with caplog.at_level(logging.INFO, logger="vaani.gateway"):
        with client.websocket_connect("/ws/session") as ws:
            ws.send_json(START)
            ws.receive_json()
            for _ in range(5):
                ws.send_bytes(frame)
            # Let the 0.02s logger tick a few times so every frame is reported.
            time.sleep(0.15)

    reported = [
        int(rec.args[1]) for rec in caplog.records if "frames in last" in rec.msg
    ]
    assert sum(reported) == 5
