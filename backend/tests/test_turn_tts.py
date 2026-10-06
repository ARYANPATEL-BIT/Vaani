"""Day 12: the reply is chunked, synthesised and sent as audio.

Gateway tests: real VAD and endpointer on the speech fixture, the fake
recogniser, a scripted model (tests/test_turn_llm.py) and a fake synthesiser
(tests/fake_tts.py), so no model download and no network.
"""

import json
from time import perf_counter

from fastapi.testclient import TestClient

from tests.fake_asr import FakeRecognizer
from tests.fake_tts import SAMPLE_RATE, FakeSynthesizer
from tests.test_asr_gateway import frame_rate_during_inference
from tests.test_turn_llm import ScriptedLLM, reacks, speak, start
from vaani.app import create_app
from vaani.config import GatewaySettings, Settings

FRAME_BYTES = SAMPLE_RATE * 20 // 1000 * 2  # 20 ms at the voice's rate: 882


def make_client(llm, synth, rec=None) -> TestClient:
    base = Settings()
    settings = Settings(
        gateway=GatewaySettings(echo_enabled=False),
        asr=base.asr.model_copy(update={"enabled": True}),
    )
    return TestClient(
        create_app(
            settings, recognizer=rec or FakeRecognizer(), llm=llm, synthesizer=synth
        )
    )


def recv(ws) -> dict | bytes:
    """The next server message: a dict for JSON, bytes for an audio frame."""
    msg = ws.receive()
    return msg["bytes"] if msg.get("bytes") is not None else json.loads(msg["text"])


def until(ws, done) -> list:
    """Every message up to and including the first one `done` accepts."""
    msgs = [recv(ws)]
    while not done(msgs[-1]):
        msgs.append(recv(ws))
    return msgs


def is_(kind: str):
    """Matches a JSON message of type `kind`, or a turn.state of state `kind`."""

    def match(m) -> bool:
        if isinstance(m, bytes):
            return kind == "frame"
        return m["type"] == kind or m.get("state") == kind

    return match


def trace(msgs: list) -> list[str]:
    """States as their name, JSON as its type, and each run of frames as one
    'frames' (how many frames a chunk makes depends on its length)."""
    out: list[str] = []
    for m in msgs:
        if isinstance(m, bytes):
            if out[-1:] != ["frames"]:
                out.append("frames")
        else:
            out.append(m["state"] if m["type"] == "turn.state" else m["type"])
    return out


def test_reply_is_spoken_audio_start_frames_audio_end() -> None:
    llm = ScriptedLLM(("Theek hai, main ", "kal yaad dila doongi. ", "Aur kuch?"))
    synth = FakeSynthesizer()
    with make_client(llm, synth).websocket_connect("/ws/session") as ws:
        start(ws)
        speak(ws)
        msgs = until(ws, is_("idle"))
        assert reacks(ws)  # nothing more after idle

    assert trace(msgs) == [
        "listening",
        "thinking",
        "transcript.final",
        "agent.text",
        # The first chunk ("Theek hai,") is spoken while the model is still
        # streaming, and speaking begins with its audio, not with the text.
        "speaking",
        "audio.start",
        "frames",
        "agent.text",
        "frames",
        "agent.text",
        "frames",  # "Aur kuch?" - the remainder, flushed at the end
        "agent.done",
        "audio.end",
        "idle",
    ]
    assert synth.texts == ["Theek hai,", "main kal yaad dila doongi.", "Aur kuch?"]
    audio_start = next(m for m in msgs if is_("audio.start")(m))
    assert audio_start["sample_rate"] == SAMPLE_RATE
    assert audio_start["turn_id"] == msgs[0]["turn_id"]
    frames = [m for m in msgs if isinstance(m, bytes)]
    assert max(len(f) for f in frames) == FRAME_BYTES


def test_speaking_lasts_until_the_audio_has_played() -> None:
    # 50 ms of audio per character: "Theek hai," + "sab theek hai." is 1.2 s.
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(audio_ms_per_char=50)
    with make_client(llm, synth).websocket_connect("/ws/session") as ws:
        start(ws)
        speak(ws)
        until(ws, is_("audio.end"))
        ended = perf_counter()
        until(ws, is_("idle"))
        waited = perf_counter() - ended

    # Every frame was sent long before; idle waits for the estimated play-out:
    # 1.2 s at the voice's 22050 Hz. The window is tight on purpose: a play-out
    # computed at a hardcoded 16000 Hz would wait 1.2 * 22050 / 16000 = 1.65 s
    # and fail here.
    assert abs(waited - 1.2) < 0.25, f"idle came {waited:.2f} s after audio.end"


def test_cancel_mid_reply_discards_the_buffer_and_sends_no_more_frames() -> None:
    # Chunk 1 is spoken; chunk 2 is held mid-synthesis; "Aur " sits in the
    # chunker's buffer; the model has paused. Then dev.flush.
    llm = ScriptedLLM(("Theek hai, ", "main kal yaad dila doongi. Aur "), hang_after=2)
    synth = FakeSynthesizer(gate_from=1)
    with make_client(llm, synth).websocket_connect("/ws/session") as ws:
        start(ws)
        speak(ws)
        until(ws, is_("frame"))  # chunk 1 is audible
        assert synth.gated.wait(5)  # chunk 2 is being synthesised
        ws.send_json({"type": "dev.flush"})
        before_release = until(ws, is_("cancelling"))
        synth.gate.set()  # chunk 2's synthesis finishes; its audio is dropped
        after = until(ws, is_("idle"))
        assert reacks(ws)  # not one frame after the flush

    flushed_at = trace(before_release).index("audio.flush")
    assert trace(before_release)[flushed_at:] == ["audio.flush", "cancelling"]
    assert trace(after) == ["idle"]
    # The buffered "Aur" was never synthesised, and no audio.end: the flush
    # ends a cancelled turn.
    assert synth.texts == ["Theek hai,", "main kal yaad dila doongi."]
    assert llm.closed.is_set()


def test_synthesis_failure_ends_audio_then_reports_tts_failed() -> None:
    llm = ScriptedLLM()  # "Namaste! " + "Main " + "theek hoon."
    synth = FakeSynthesizer(fail_on=1)  # the second chunk fails
    with make_client(llm, synth).websocket_connect("/ws/session") as ws:
        start(ws)
        speak(ws)
        msgs = until(ws, is_("idle"))
        assert reacks(ws)

    assert trace(msgs)[3:] == [
        "agent.text",  # "Namaste! "
        "speaking",
        "audio.start",
        "frames",  # chunk 1, "Namaste!"
        "agent.text",
        "agent.text",
        "audio.end",  # chunk 2 failed: end the audio that did play...
        "error",  # ...then say why...
        "idle",  # ...then stop
    ]
    assert msgs[-2]["code"] == "TTS_FAILED"
    assert "agent.done" not in trace(msgs)  # an unspoken reply is not complete


def test_frames_keep_flowing_at_50_per_second_during_synthesis(monkeypatch) -> None:
    synth = FakeSynthesizer(synth_s=1.0)  # every chunk holds a thread for 1 s
    rate, max_gap_ms, synth_s = frame_rate_during_inference(
        monkeypatch,
        make_client(ScriptedLLM(), synth),
        lambda: synth.windows[0],
        silence_s=3.0,
    )
    assert synth_s >= 1.0
    assert rate >= 45, f"{rate:.1f} frames/s during synthesis"
    assert max_gap_ms < 100, f"longest gap {max_gap_ms:.0f} ms"


def test_echo_audio_start_declares_the_mic_rate() -> None:
    settings = Settings(gateway=GatewaySettings(echo_enabled=True))
    with TestClient(create_app(settings)).websocket_connect("/ws/session") as ws:
        start(ws)
        speak(ws)
        audio_start = until(ws, is_("audio.start"))[-1]

    assert audio_start["sample_rate"] == 16000
