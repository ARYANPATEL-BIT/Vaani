"""Tests for the /ws/session WebSocket gateway.

Uses FastAPI's TestClient, whose `websocket_connect` opens a real in-process
WebSocket. Each test drives the protocol from the client side and asserts on
what the server sends back and whether the connection stays open.
"""

import logging
import time

from fastapi.testclient import TestClient

from vaani.app import create_app
from vaani.config import GatewaySettings, Settings
from vaani.gateway import expected_frame_bytes

# The audio block every valid session.start must carry to match the server.
GOOD_AUDIO = {"sample_rate": 16000, "channels": 1, "frame_ms": 20}
START = {"type": "session.start", "persona": "default", "audio": GOOD_AUDIO}


def make_client(interval_s: float = 1.0) -> TestClient:
    """Build a TestClient over an app whose gateway log interval we control."""
    settings = Settings(gateway=GatewaySettings(frame_log_interval_s=interval_s))
    return TestClient(create_app(settings))


def good_frame() -> bytes:
    """One correctly sized silent frame (640 zero bytes for the defaults)."""
    return b"\x00" * expected_frame_bytes(Settings().audio)


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
    with make_client().websocket_connect("/ws/session") as ws:
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
