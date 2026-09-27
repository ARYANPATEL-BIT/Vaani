"""Endpointing inside the /ws/session gateway, with the real Silero VAD.

The scripted pattern is the same one `fake_client.py --turn-test` sends:
silence, the speech clip, a short pause, the clip again, a long silence. It
must produce exactly ONE turn_ended: the short pause is ignored.
"""

import logging

from fastapi.testclient import TestClient

from tests.test_vad import SILENCE, speech_frames
from vaani.app import create_app
from vaani.config import EndpointSettings, GatewaySettings, Settings

START = {
    "type": "session.start",
    "persona": "default",
    "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 20},
}


def make_client(endpoint_enabled: bool = True) -> TestClient:
    settings = Settings(
        gateway=GatewaySettings(echo_enabled=False),
        endpoint=EndpointSettings(enabled=endpoint_enabled),
    )
    return TestClient(create_app(settings))


def turn_test_pattern() -> list[bytes]:
    """0.5 s silence, clip, 0.4 s pause, clip, 2 s silence (20 ms frames).

    The clip's all-zero lead-in (40 ms) and tail (780 ms) are stripped: left
    in, the "short" pause would really be 1.2 s and correctly end the turn.
    """
    frames = speech_frames()
    voiced = [i for i, f in enumerate(frames) if any(f)]
    clip = frames[voiced[0] : voiced[-1] + 1]
    return [SILENCE] * 25 + clip + [SILENCE] * 20 + clip + [SILENCE] * 100


def send_and_collect(client: TestClient, frames: list[bytes], caplog) -> list[str]:
    with caplog.at_level(logging.INFO, logger="vaani.gateway"):
        with client.websocket_connect("/ws/session") as ws:
            ws.send_json(START)
            session_id = ws.receive_json()["session_id"]
            for frame in frames:
                ws.send_bytes(frame)
            ws.send_json({"type": "session.end"})
    turns = [r.getMessage() for r in caplog.records if "turn_ended" in r.msg]
    assert all(session_id in m for m in turns)
    return turns


def test_short_pause_then_long_silence_gives_exactly_one_turn(caplog) -> None:
    turns = send_and_collect(make_client(), turn_test_pattern(), caplog)
    assert len(turns) == 1, turns
    assert "frames buffered" in turns[0] and "waited" in turns[0]


def test_endpointing_disabled_emits_no_turn(caplog) -> None:
    turns = send_and_collect(make_client(False), turn_test_pattern(), caplog)
    assert turns == []
