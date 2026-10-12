"""Push-to-talk (protocol v0.9): presses, not silences, end the user's turns.

Gateway tests in the barge-in pattern (test_barge_in.py): fake recogniser,
scripted model, fake synthesiser, and SCRIPTED VAD (a frame is speech when
its first byte is not zero), so no Whisper, no network and no Piper. One test
uses the real Silero model, to show each press starts from fresh VAD state.

Each frame carries a tag in byte 1, so a test can check exactly which frames
reached the recogniser.
"""

import asyncio
import logging
import time

import pytest
from fastapi.testclient import TestClient

import vaani.turns as turns_mod
from tests.fake_tts import FakeSynthesizer
from tests.test_asr_gateway import START
from tests.test_barge_in import FRAME_BYTES, Recognizer, ScriptedVad, frame, history
from tests.test_turn_llm import ScriptedLLM, reacks
from tests.test_turn_tts import is_, trace, until
from tests.test_vad import speech_frames
from vaani.app import create_app
from vaani.config import EndpointSettings, GatewaySettings, Settings
from vaani.ptt import PttBuffer
from vaani.session import Session
from vaani.telemetry import Telemetry
from vaani.turns import TurnPipeline
from vaani.vad import VadStream, load_model

PTT_START = {"type": "ptt.start"}
PTT_END = {"type": "ptt.end"}


class CountingVad(ScriptedVad):
    """ScriptedVad that also counts how often it is reset, across sessions."""

    resets = 0

    def reset(self) -> None:
        CountingVad.resets += 1


@pytest.fixture(autouse=True)
def scripted_vad(monkeypatch) -> None:
    CountingVad.resets = 0
    monkeypatch.setattr(turns_mod, "VadStream", CountingVad)


def make_client(llm=None, synth=None, rec=None, **endpoint) -> TestClient:
    """Fakes everywhere; `endpoint` overrides [endpoint] settings."""
    base = Settings()
    settings = Settings(
        gateway=GatewaySettings(echo_enabled=False),
        asr=base.asr.model_copy(update={"enabled": True}),
        endpoint=base.endpoint.model_copy(update=endpoint),
    )
    app = create_app(
        settings,
        recognizer=rec or Recognizer("kya haal hai"),
        llm=llm or ScriptedLLM(("Theek hai.",)),
        synthesizer=synth or FakeSynthesizer(),
    )
    return TestClient(app)


def start_ptt(ws) -> dict:
    ws.send_json({**START, "mode": "ptt"})
    started = ws.receive_json()
    assert started["type"] == "session.started"
    return started


def speak(ws, speech_frames: int = 20, tag: int = 0) -> None:
    """Speech frames only, as the client sends them while a press is open."""
    for i in range(speech_frames):
        ws.send_bytes(frame(True, tag + i))


def press(ws, speech_frames: int = 20, tag: int = 0) -> None:
    """A whole press: speak pressed, speech, stop pressed. No silence."""
    ws.send_json(PTT_START)
    speak(ws, speech_frames, tag)
    ws.send_json(PTT_END)


def frames_of(pcm: bytes) -> list[bytes]:
    return [pcm[i : i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)]


# --- A press is a turn ----------------------------------------------------------


def test_a_press_is_one_turn_ended_by_ptt_end_with_no_silence_wait() -> None:
    rec = Recognizer("kya haal hai")
    with make_client(rec=rec).websocket_connect("/ws/session") as ws:
        assert start_ptt(ws)["mode"] == "ptt"
        press(ws)  # not one frame of silence: ptt.end alone ends the turn
        turn = until(ws, is_("idle"))

    assert trace(turn)[:3] == ["listening", "thinking", "transcript.final"]
    assert trace(turn)[-3:] == ["agent.done", "audio.end", "idle"]
    final = next(m for m in turn if is_("transcript.final")(m))
    assert final["duration_ms"] == 20 * 20  # the press: 20 frames of 20 ms
    # Exactly the pressed frames: no pre-roll, nothing trimmed.
    assert frames_of(rec.audio[0]) == [frame(True, i) for i in range(20)]


def test_silence_while_pressed_does_not_end_the_turn() -> None:
    rec = Recognizer("kya haal hai")
    with make_client(rec=rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        ws.send_json(PTT_START)
        assert trace(until(ws, is_("listening"))) == ["listening"]
        speak(ws, 10)
        for _ in range(60):  # 1.2 s: hands-free mode would end the turn at 0.7 s
            ws.send_bytes(frame(False))
        assert reacks(ws)  # nothing was sent: still listening
        ws.send_json(PTT_END)
        turn = until(ws, is_("idle"))

    assert trace(turn)[0] == "thinking"
    assert len(frames_of(rec.audio[0])) == 70


def test_each_press_resets_vad_and_hands_free_never_does() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)  # hands-free
        assert ws.receive_json()["mode"] == "vad"
        speak(ws, 20)
        for _ in range(50):
            ws.send_bytes(frame(False))
        until(ws, is_("idle"))
    assert CountingVad.resets == 0

    with make_client(rec=Recognizer("ek", "do")).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        for n in range(2):
            press(ws, tag=40 * n)
            until(ws, is_("idle"))
    assert CountingVad.resets == 2


# --- Empty presses go back to idle --------------------------------------------


@pytest.mark.parametrize("silent_frames", [30, 0])
def test_an_empty_press_goes_back_to_idle_untranscribed(silent_frames) -> None:
    rec = Recognizer()
    with make_client(rec=rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        ws.send_json(PTT_START)
        for _ in range(silent_frames):
            ws.send_bytes(frame(False))
        ws.send_json(PTT_END)
        msgs = until(ws, is_("idle"))
        assert reacks(ws)

    assert trace(msgs) == ["listening", "idle"]
    assert rec.audio == []  # never sent to the recogniser


def test_an_empty_press_after_a_cut_answers_the_cut_question() -> None:
    # The press cuts a reply nobody heard yet (synthesis held), then carries
    # no speech: the cut question is answered, and the state ends idle.
    llm = ScriptedLLM(("Theek hai.",))
    synth = FakeSynthesizer(gate_from=0)
    rec = Recognizer("kal kitne baje meeting hai")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        press(ws)
        until(ws, is_("agent.text"))
        assert synth.gated.wait(5)
        ws.send_json(PTT_START)
        cut = until(ws, is_("listening"))
        ws.send_json(PTT_END)
        again = until(ws, is_("thinking"))
        synth.gate.set()
        rest = until(ws, is_("idle"))

    assert trace(cut) == ["audio.flush", "cancelling", "listening"]
    assert trace(again) == ["thinking"]
    assert "idle" in trace(rest)
    assert history(llm, 1) == [("user", "kal kitne baje meeting hai")]


# --- Barge-in by pressing --------------------------------------------------------


def test_pressing_while_speaking_barges_in_and_keeps_what_was_heard() -> None:
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(audio_ms_per_char=50)  # 1.2 s of audio
    rec = Recognizer("kya haal hai", "ruko")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        press(ws)
        first = until(ws, is_("frame"))
        time.sleep(0.3)  # the user hears part of the first chunk
        ws.send_json(PTT_START)
        cut = until(ws, is_("listening"))
        speak(ws, 10, tag=200)
        ws.send_json(PTT_END)
        until(ws, is_("idle"))

    flushed = trace(cut).index("audio.flush")
    assert trace(cut)[flushed:] == ["audio.flush", "cancelling", "listening"]
    old_turn = next(m["turn_id"] for m in first if is_("thinking")(m))
    assert next(m for m in cut if is_("audio.flush")(m))["turn_id"] == old_turn
    assert cut[-1]["turn_id"] != old_turn
    said = history(llm, 1)[1]
    assert said[0] == "assistant" and said[1] != "Theek hai, sab theek hai."
    assert history(llm, 1)[2] == ("user", "ruko")


def test_pressing_while_thinking_carries_the_unheard_question() -> None:
    llm = ScriptedLLM(("Theek hai, ", "main kal yaad dila doongi."))
    synth = FakeSynthesizer(gate_from=0)
    rec = Recognizer("pehla sawaal", "aur doosra")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        press(ws)
        until(ws, is_("agent.text"))
        assert synth.gated.wait(5)
        ws.send_json(PTT_START)
        cut = until(ws, is_("listening"))
        synth.gate.set()  # the held synthesis finishes; it must be discarded
        speak(ws, 10, tag=200)
        ws.send_json(PTT_END)
        until(ws, is_("idle"))

    assert trace(cut) == ["audio.flush", "cancelling", "listening"]
    assert llm.closed.is_set()
    assert history(llm, 1) == [("user", "pehla sawaal aur doosra")]


def test_speech_without_a_press_does_not_barge_in() -> None:
    # The client should not send these frames; if it does, they are dropped.
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(audio_ms_per_char=50)
    rec = Recognizer("kya haal hai")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        press(ws)
        until(ws, is_("frame"))
        speak(ws, 30, tag=100)  # far past the 200 ms a hands-free barge-in needs
        rest = until(ws, is_("idle"))

    assert "audio.flush" not in trace(rest) and "cancelling" not in trace(rest)
    assert len(rec.audio) == 1


# --- Edge cases -------------------------------------------------------------------


def test_frames_outside_a_press_are_dropped() -> None:
    rec = Recognizer("kya haal hai")
    with make_client(rec=rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        speak(ws, 20, tag=100)  # before any press
        press(ws, tag=0)
        until(ws, is_("idle"))
        speak(ws, 20, tag=150)  # after the press
        assert reacks(ws)  # no turn opened

    assert frames_of(rec.audio[0]) == [frame(True, i) for i in range(20)]
    assert len(rec.audio) == 1


def test_ptt_end_without_a_press_is_ignored() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        ws.send_json(PTT_END)
        assert reacks(ws)  # nothing at all was sent for it


def test_a_second_ptt_start_is_ignored_and_the_press_goes_on() -> None:
    rec = Recognizer("kya haal hai")
    with make_client(rec=rec).websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        ws.send_json(PTT_START)
        speak(ws, 10, tag=0)
        ws.send_json(PTT_START)  # a key held down repeats its keydown
        speak(ws, 10, tag=10)
        ws.send_json(PTT_END)
        turn = until(ws, is_("idle"))

    assert trace(turn).count("listening") == 1
    assert frames_of(rec.audio[0]) == [frame(True, i) for i in range(20)]


def test_disconnect_mid_press_transcribes_nothing(caplog) -> None:
    rec = Recognizer()
    with caplog.at_level(logging.INFO, logger="vaani.ptt"):
        with make_client(rec=rec).websocket_connect("/ws/session") as ws:
            start_ptt(ws)
            ws.send_json(PTT_START)
            until(ws, is_("listening"))
            speak(ws, 10)
        # Leaving the block closed the socket mid-press.

    assert rec.audio == []
    assert any("discarding open press" in r.getMessage() for r in caplog.records)


def test_ptt_messages_in_a_hands_free_session_are_bad_messages() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)  # no mode: hands-free
        assert ws.receive_json()["mode"] == "vad"
        for message in (PTT_START, PTT_END):
            ws.send_json(message)
            reply = ws.receive_json()
            assert reply["type"] == "error" and reply["code"] == "BAD_MESSAGE"
        assert reacks(ws)  # the session carries on


def test_a_second_session_start_does_not_change_the_mode() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        first = start_ptt(ws)
        ws.send_json({**START, "mode": "vad"})
        second = ws.receive_json()
        ws.send_json(PTT_START)  # still a ptt session
        assert trace(until(ws, is_("listening"))) == ["listening"]

    assert second == first  # same session_id, mode still "ptt"


def test_an_unknown_mode_is_a_bad_message() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json({**START, "mode": "hold"})
        reply = ws.receive_json()
    assert reply["type"] == "error" and reply["code"] == "BAD_MESSAGE"


def test_a_press_held_past_the_cap_ends_there() -> None:
    rec = Recognizer("kya haal hai")
    client = make_client(rec=rec, max_utterance_ms=200)  # 10 frames
    with client.websocket_connect("/ws/session") as ws:
        start_ptt(ws)
        press(ws, 15)  # 5 frames too many; then a ptt.end with no press open
        turn = until(ws, is_("idle"))
        assert reacks(ws)

    assert trace(turn)[:2] == ["listening", "thinking"]
    assert frames_of(rec.audio[0]) == [frame(True, i) for i in range(10)]
    assert len(rec.audio) == 1


# --- Fresh VAD state per press (real Silero) ----------------------------------


def test_two_presses_with_a_long_gap_each_start_from_fresh_vad_state(
    monkeypatch,
) -> None:
    # The second press comes "much later" with no frames in between (the
    # ptt client sends none). Its speech probabilities must be exactly the
    # first press's, frame for frame: Silero's memory of press 1 is gone.
    # 41 frames is not a whole number of 512-sample chunks, so a left-over
    # partial chunk would also show up here if it were carried over.
    monkeypatch.setattr(turns_mod, "VadStream", VadStream)
    settings = Settings()
    model = load_model(settings.vad.model_path, settings.vad.model_sha256)
    session = Session(session_id="ptt", persona="default", mode="ptt")
    speech = speech_frames()[:41]

    async def discard(_message) -> None:
        pass

    async def two_presses() -> list[list[float]]:
        pipeline = TurnPipeline(
            settings,
            session,
            Telemetry("ptt"),
            discard,
            discard,
            model,
            None,
            None,
            None,
        )
        presses = []
        for _ in range(2):
            await pipeline.on_ptt_start()
            probabilities = []
            for f in speech:
                await pipeline.on_frame(f)
                probabilities.append(pipeline._vad.probability)
            presses.append(probabilities)
            await pipeline.on_ptt_end()
        await pipeline.close()
        return presses

    first, second = asyncio.run(two_presses())
    assert max(first) >= settings.vad.threshold  # the clip really has speech
    assert second == first


# --- PttBuffer on its own ---------------------------------------------------------


def test_buffer_counts_only_voiced_frames_against_min_utterance() -> None:
    cfg = EndpointSettings(min_utterance_ms=60)  # 3 frames
    buffer = PttBuffer(cfg, frame_ms=20, vad_threshold=0.5, session_id="t")
    buffer.press()
    for p in (0.9, 0.9, 0.4, 0.1):
        buffer.push(b"x", p)
    assert buffer.release() is None  # 2 voiced frames: too few
    buffer.press()
    for p in (0.9, 0.9, 0.5):
        buffer.push(b"x", p)
    turn = buffer.release()
    assert turn is not None and turn.voiced_frames == 3 and turn.audio == b"xxx"
    assert not buffer.holding
