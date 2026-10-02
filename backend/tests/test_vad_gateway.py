"""Tests for VAD inside the /ws/session gateway.

Covers: only correctly sized frames reach VAD, speech events are logged with
the session id, the per-interval log line carries VAD p50/p95, and the
[vad].enabled flag really switches VAD off.
"""

import logging
import time

from fastapi.testclient import TestClient

import vaani.turns as turns_mod
from tests.test_vad import SILENCE, speech_frames
from vaani.app import create_app
from vaani.config import GatewaySettings, Settings
from vaani.gateway import expected_frame_bytes

START = {
    "type": "session.start",
    "persona": "default",
    "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 20},
}


def make_client(vad_enabled: bool = True, interval_s: float = 1.0) -> TestClient:
    """App with echo off (nothing to drain) and VAD on or off."""
    base = Settings()
    settings = Settings(
        gateway=GatewaySettings(frame_log_interval_s=interval_s, echo_enabled=False),
        vad=base.vad.model_copy(update={"enabled": vad_enabled}),
    )
    return TestClient(create_app(settings))


def test_wrong_size_frames_never_reach_vad(monkeypatch) -> None:
    pushed: list[int] = []

    class SpyVad:
        def __init__(self, *args) -> None:
            pass

        def push(self, frame: bytes) -> None:
            pushed.append(len(frame))

    monkeypatch.setattr(turns_mod, "VadStream", SpyVad)
    good = expected_frame_bytes(Settings().audio)
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()  # session.started
        ws.send_bytes(b"\x00" * 100)  # too short
        assert ws.receive_json()["code"] == "BAD_FRAME_SIZE"
        ws.send_bytes(b"\x00" * (good + 2))  # too long
        assert ws.receive_json()["code"] == "BAD_FRAME_SIZE"
        ws.send_bytes(b"\x00" * good)
        ws.send_json({"type": "session.end"})

    assert pushed == [good]


def test_speech_events_are_logged_with_session_id(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="vaani.turns"):
        with make_client().websocket_connect("/ws/session") as ws:
            ws.send_json(START)
            session_id = ws.receive_json()["session_id"]
            for frame in speech_frames() + [SILENCE] * 50:
                ws.send_bytes(frame)
            ws.send_json({"type": "session.end"})

    messages = [r.getMessage() for r in caplog.records]
    events = [m for m in messages if "speech_started" in m or "speech_ended" in m]
    assert events, "expected speech_started / speech_ended log lines"
    assert all(session_id in m for m in events)
    assert "speech_started" in events[0] and "speech_ended" in events[-1]


def test_interval_log_reports_vad_p50_p95(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="vaani.gateway"):
        with make_client(interval_s=0.02).websocket_connect("/ws/session") as ws:
            ws.send_json(START)
            ws.receive_json()
            for _ in range(40):  # more than MIN_SAMPLES
                ws.send_bytes(SILENCE)
            time.sleep(0.15)

    lines = [r.getMessage() for r in caplog.records if "frames in last" in r.msg]
    assert any("(vad p50=" in m and "ms p95=" in m for m in lines)


def test_vad_disabled_runs_no_vad(caplog, monkeypatch) -> None:
    def fail(*args):
        raise AssertionError("VadStream must not be built when VAD is off")

    monkeypatch.setattr(turns_mod, "VadStream", fail)
    with caplog.at_level(logging.INFO, logger="vaani.gateway"):
        with make_client(False, 0.02).websocket_connect("/ws/session") as ws:
            ws.send_json(START)
            ws.receive_json()
            ws.send_bytes(SILENCE)
            time.sleep(0.1)

    lines = [r.getMessage() for r in caplog.records if "frames in last" in r.msg]
    assert lines and all("(vad off)" in m for m in lines)
