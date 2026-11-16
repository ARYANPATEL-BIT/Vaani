"""Tests for the sign-in check on the /ws/session handshake (protocol v0.11).

Before accepting the WebSocket, the gateway checks the Origin header and the
vaani_session cookie (vaani/auth.py, handshake_refusal). A refused handshake
is closed BEFORE accept: the client never gets a socket, which TestClient
reports by raising WebSocketDisconnect from websocket_connect itself.
"""

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from vaani.app import create_app
from vaani.auth import COOKIE_NAME, sign_cookie
from vaani.config import AuthSettings, Settings

SECRET = "s" * 32
ORIGIN = "http://localhost:5173"
EMAIL = "aryan@example.com"
START = {
    "type": "session.start",
    "persona": "default",
    "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 20},
}


def make_client(enabled: bool = True) -> TestClient:
    auth = AuthSettings(
        enabled=enabled,
        google_client_id="test-client-id",
        session_secret=SECRET,
        allowed_emails=[EMAIL],
        allowed_origins=[ORIGIN],
    )
    return TestClient(create_app(Settings(auth=auth)))


def cookie(expires_in: float = 3600, secret: str = SECRET) -> str:
    value = sign_cookie("sub-1", EMAIL, "Aryan", time.time() + expires_in, secret)
    return f"{COOKIE_NAME}={value}"


def assert_session_starts(ws) -> None:
    ws.send_json(START)
    assert ws.receive_json()["type"] == "session.started"


def test_valid_cookie_and_origin_are_accepted():
    headers = {"origin": ORIGIN, "cookie": cookie()}
    with make_client().websocket_connect("/ws/session", headers=headers) as ws:
        assert_session_starts(ws)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"origin": ORIGIN}, id="no-cookie"),
        pytest.param(
            {"origin": "https://evil.example", "cookie": cookie()}, id="bad-origin"
        ),
        pytest.param({"cookie": cookie()}, id="no-origin"),
        pytest.param({"origin": ORIGIN, "cookie": cookie(-1)}, id="expired-cookie"),
        pytest.param(
            {"origin": ORIGIN, "cookie": cookie(secret="x" * 32)}, id="wrong-secret"
        ),
    ],
)
def test_handshake_is_refused(headers):
    with pytest.raises(WebSocketDisconnect):
        with make_client().websocket_connect("/ws/session", headers=headers):
            pass  # never reached: no socket was accepted


def test_refusal_is_logged_with_the_reason(caplog):
    with pytest.raises(WebSocketDisconnect):
        with make_client().websocket_connect("/ws/session", headers={"origin": ORIGIN}):
            pass
    assert "refused" in caplog.text and "cookie" in caplog.text


def test_auth_disabled_accepts_without_cookie_or_origin():
    with make_client(enabled=False).websocket_connect("/ws/session") as ws:
        assert_session_starts(ws)
