"""scripts/fake_client.py --barge-in-after, end to end over a real socket.

The client is the harness for the real barge-in path, so it is tested the way
it is used: a real uvicorn server (in a thread, on a free port, never 8000)
and a real WebSocket client, with the real Silero VAD on the speech fixture.
Only the slow or paid parts are fakes: recogniser, model and synthesiser.
"""

import asyncio
import importlib.util
import threading
import time
import wave
from pathlib import Path

import uvicorn

from tests.fake_asr import FakeRecognizer
from tests.fake_tts import FakeSynthesizer
from tests.test_turn_llm import ScriptedLLM
from vaani.app import create_app
from vaani.config import GatewaySettings, Settings

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fake_client.py"
FIXTURE = Path(__file__).parent / "fixtures" / "speech_16k_mono.wav"


def load_client():
    """Import the script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("fake_client", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def short_clip(path: Path, seconds: float) -> None:
    """The fixture's first `seconds` of voiced audio, to keep the test short."""
    with wave.open(str(FIXTURE), "rb") as src:
        params, pcm = src.getparams(), src.readframes(src.getnframes())
    first = next(i for i in range(0, len(pcm), 2) if pcm[i : i + 2] != b"\x00\x00")
    with wave.open(str(path), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(pcm[first : first + int(seconds * 16000) * 2])


def serve(app) -> tuple[uvicorn.Server, threading.Thread, int]:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, port


def test_barge_in_after_cuts_the_reply_and_opens_a_new_turn(tmp_path) -> None:
    clip = tmp_path / "clip.wav"
    short_clip(clip, 1.5)
    base = Settings()
    settings = Settings(
        gateway=GatewaySettings(echo_enabled=False),
        asr=base.asr.model_copy(update={"enabled": True}),
    )
    # 2.6 s of reply audio: still playing when the client talks over it.
    llm = ScriptedLLM(("Theek hai, ", "main kal subah aath baje yaad dila doongi. "))
    synth = FakeSynthesizer(audio_ms_per_char=50)
    app = create_app(settings, recognizer=FakeRecognizer(), llm=llm, synthesizer=synth)
    server, thread, port = serve(app)
    try:
        client = load_client()
        log = asyncio.run(
            client.main(
                f"ws://127.0.0.1:{port}/ws/session", 0, 300.0, None, clip, False
            )
        )
    finally:
        server.should_exit = True
        thread.join(10)

    msgs = [m for _, m in log]
    states = [(m["state"], m["turn_id"]) for m in msgs if m["type"] == "turn.state"]
    first_turn = states[0][1]
    flush = next(m for m in msgs if m["type"] == "audio.flush")
    assert flush["turn_id"] == first_turn  # the agent's reply was cut
    after = msgs[msgs.index(flush) :]
    cut = [m["state"] for m in after if m["type"] == "turn.state"][:2]
    assert cut == ["cancelling", "listening"]
    new_turn = next(m["turn_id"] for m in after if m.get("state") == "listening")
    assert new_turn != first_turn
