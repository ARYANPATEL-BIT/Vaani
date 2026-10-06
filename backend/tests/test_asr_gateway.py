"""Speech recognition inside the /ws/session gateway, with a fake recogniser.

The real Silero VAD and endpointer run on the recorded speech fixture; only
the recogniser is a stand-in (tests/fake_asr.py), so these run in the default
suite. tests/test_asr_whisper.py repeats the frame-rate test with the real
model.
"""

import logging
import time
from time import perf_counter

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import vaani.session as session_mod
from tests.fake_asr import FakeRecognizer
from tests.test_vad import SILENCE, speech_frames
from vaani.app import create_app
from vaani.asr import Recognizer
from vaani.config import GatewaySettings, Settings

START = {
    "type": "session.start",
    "persona": "default",
    "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 20},
}
FRAME_S = 0.020


def make_client(recognizer: Recognizer, partial_interval_ms: int = 0) -> TestClient:
    base = Settings()
    settings = Settings(
        gateway=GatewaySettings(echo_enabled=False),
        asr=base.asr.model_copy(
            update={"enabled": True, "partial_interval_ms": partial_interval_ms}
        ),
    )
    return TestClient(create_app(settings, recognizer=recognizer))


def utterance() -> list[bytes]:
    """The speech clip followed by enough silence for endpointing to end it."""
    return speech_frames() + [SILENCE] * 60


def drain(ws) -> list[dict]:
    """End the session and collect every JSON message until the close."""
    ws.send_json({"type": "session.end"})
    got = []
    try:
        while True:
            got.append(ws.receive_json())
    except WebSocketDisconnect:
        return got


def test_final_transcript_after_turn_end() -> None:
    rec = FakeRecognizer()
    with make_client(rec).websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()  # session.started
        for frame in utterance():
            ws.send_bytes(frame)
        listening, idle, final = [ws.receive_json() for _ in range(3)]
        rest = drain(ws)

    # No language model in this app: the turn goes straight back to idle,
    # and the transcript still arrives.
    assert (listening["state"], idle["state"]) == ("listening", "idle")
    assert final["type"] == "transcript.final"
    assert final["text"] == "namaste duniya" and final["language"] == "hi"
    assert final["turn_id"] and final["duration_ms"] > 0
    assert rest == []


def test_partials_share_the_finals_turn_id() -> None:
    rec = FakeRecognizer(decode_s=0.01)
    client = make_client(rec, partial_interval_ms=400)
    with client.websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()
        for frame in utterance():
            ws.send_bytes(frame)
            time.sleep(0.002)  # let partials run between frames
        msgs = [ws.receive_json()]
        while msgs[-1]["type"] != "transcript.final":
            msgs.append(ws.receive_json())

    partials = [m for m in msgs if m["type"] == "transcript.partial"]
    assert partials, msgs
    transcripts = [m for m in msgs if m["type"].startswith("transcript")]
    assert {m["turn_id"] for m in transcripts} == {msgs[-1]["turn_id"]}


def test_disconnect_mid_inference_emits_nothing(caplog) -> None:
    rec = FakeRecognizer(gated=True)
    try:
        with caplog.at_level(logging.INFO, logger="vaani.asr"):
            with make_client(rec).websocket_connect("/ws/session") as ws:
                ws.send_json(START)
                ws.receive_json()
                for frame in utterance():
                    ws.send_bytes(frame)
                while not rec.started.is_set():  # the final is decoding
                    time.sleep(0.005)
            # Leaving the block disconnected the socket mid-inference.
            rec.gate.set()
            time.sleep(0.2)
    finally:
        rec.gate.set()

    assert len(rec.windows) == 1  # the decode did run to its end...
    sent = [r.getMessage() for r in caplog.records if "transcript." in r.msg]
    assert sent == []  # ...but nothing was sent for it


# --- The event loop keeps ingesting while recognition runs -------------------


def send_paced(ws, frames: list[bytes]) -> None:
    """Send frames at the real-time rate, one every 20 ms, like a microphone.

    Paced against an absolute schedule, so sleep jitter does not accumulate.
    """
    t0 = perf_counter()
    for i, frame in enumerate(frames):
        while perf_counter() < t0 + i * FRAME_S:
            time.sleep(0.001)
        ws.send_bytes(frame)


def frame_rate_during_inference(
    monkeypatch, client: TestClient, decode_window, silence_s: float
) -> tuple[float, float, float]:
    """(frames per second while a decode ran, longest gap ms, decode seconds).

    Frames are timestamped where the SERVER counts them (Session.record_frame,
    on the event loop). If inference blocked the loop, frames would pile up
    in the socket and be counted late, in a burst: the rate during the decode
    would drop and the longest gap would grow to the decode's length.
    """
    stamps: list[float] = []
    original = session_mod.Session.record_frame

    def record(self) -> None:
        stamps.append(perf_counter())
        original(self)

    monkeypatch.setattr(session_mod.Session, "record_frame", record)
    frames = speech_frames() + [SILENCE] * round(silence_s / FRAME_S)
    with client.websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()
        send_paced(ws, frames)
        while ws.receive_json()["type"] != "transcript.final":
            pass
    start, end = decode_window()
    assert end < stamps[-1], "decode must finish while frames still arrive"
    inside = [t for t in stamps if start <= t <= end]
    gaps = [b - a for a, b in zip(inside, inside[1:], strict=False)]
    # No two frames inside the window at all = the loop was frozen throughout.
    longest = max(gaps) if gaps else end - start
    return len(inside) / (end - start), longest * 1000, end - start


def test_frames_keep_flowing_at_50_per_second_during_inference(monkeypatch) -> None:
    rec = FakeRecognizer(decode_s=1.0)
    rate, max_gap_ms, decode_s = frame_rate_during_inference(
        monkeypatch, make_client(rec), lambda: rec.windows[0], silence_s=3.0
    )
    assert decode_s >= 1.0
    assert rate >= 45, f"{rate:.1f} frames/s during inference"
    assert max_gap_ms < 100, f"longest gap {max_gap_ms:.0f} ms"
