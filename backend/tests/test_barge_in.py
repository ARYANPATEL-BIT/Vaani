"""Day 13: barge-in. The user talks over the agent, and the agent stops.

Gateway tests in the fake-gateway pattern: the fake recogniser, a scripted
model and a fake synthesiser, so no Whisper, no network, no Piper. VAD is
SCRIPTED too (ScriptedVad below): a frame is speech when its first byte is
not zero, and the real Hysteresis turns that into speech_started /
speech_ended. That makes "how much speech" exact to the frame, which a
barge-in threshold test needs.

The defaults apply: VAD fires speech_started on the 4th speech frame, and a
barge-in needs 200 ms = 10 speech frames counted from the onset.
"""

import logging
import time
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

import vaani.turns as turns_mod
from tests.fake_asr import FakeRecognizer
from tests.fake_tts import FakeSynthesizer
from tests.test_turn_llm import ScriptedLLM, reacks, start
from tests.test_turn_tts import is_, trace, until
from vaani.app import create_app
from vaani.asr.base import Transcript
from vaani.barge_in import BargeIn, heard_text
from vaani.config import BargeInSettings, GatewaySettings, Settings, VadSettings
from vaani.speaker import Spoken
from vaani.vad import SPEECH_ENDED, SPEECH_STARTED, Hysteresis, SpeechEvent

FRAME_BYTES = 640
PREROLL_FRAMES = 15  # [endpoint].preroll_ms = 300


def frame(speech: bool, tag: int = 0) -> bytes:
    """One mic frame. Byte 0 says speech or not; byte 1 is a tag, so a test
    can find exactly which frames reached the recogniser."""
    return bytes([1 if speech else 0, tag % 256]) + bytes(FRAME_BYTES - 2)


class ScriptedVad:
    """Stands in for VadStream: probability 1 for a speech frame, else 0."""

    def __init__(self, model, vad: VadSettings, audio) -> None:
        self._hysteresis = Hysteresis(vad.start_frames, vad.end_frames)
        self._index = -1
        self.probability = 0.0

    def push(self, data: bytes) -> SpeechEvent | None:
        self._index += 1
        self.probability = 1.0 if data[0] else 0.0
        return self._hysteresis.update(data[0] != 0, self._index, perf_counter())


@pytest.fixture(autouse=True)
def scripted_vad(monkeypatch) -> None:
    monkeypatch.setattr(turns_mod, "VadStream", ScriptedVad)


class Recognizer(FakeRecognizer):
    """Says `texts` in order, one per decode, and keeps every decode's audio."""

    def __init__(self, *texts: str, gated: bool = False) -> None:
        super().__init__(gated=gated)
        self.texts = list(texts)
        self.audio: list[bytes] = []

    def _work(self, pcm: bytes) -> Transcript:
        self.audio.append(pcm)
        result = super()._work(pcm)
        return Transcript(self.texts.pop(0), result.language)


def make_client(llm, synth, rec, min_utterance_ms: int = 300) -> TestClient:
    base = Settings()
    settings = Settings(
        gateway=GatewaySettings(echo_enabled=False),
        asr=base.asr.model_copy(update={"enabled": True}),
        endpoint=base.endpoint.model_copy(
            update={"min_utterance_ms": min_utterance_ms}
        ),
    )
    return TestClient(create_app(settings, recognizer=rec, llm=llm, synthesizer=synth))


def say(ws, speech_frames: int = 20, tag: int = 0) -> None:
    """A whole user turn: speech, then enough silence to end it."""
    for i in range(speech_frames):
        ws.send_bytes(frame(True, tag + i))
    for _ in range(50):
        ws.send_bytes(frame(False))


def barge(ws, speech_frames: int = 10, tag: int = 200) -> None:
    """Exactly enough speech to be an interruption (10 frames = 200 ms)."""
    for i in range(speech_frames):
        ws.send_bytes(frame(True, tag + i))


def history(llm, call: int) -> list[tuple[str, str]]:
    """(role, content) of every message the model got on `call`, minus the
    system prompt."""
    return [(m.role, m.content) for m in llm.calls[call][1:]]


# --- Mid-conversation barge-ins ------------------------------------------------


def test_barge_in_during_first_chunk_synthesis() -> None:
    # The model has answered; the first chunk is held mid-synthesis, so the
    # state is still `thinking` and nothing has been heard.
    llm = ScriptedLLM(("Theek hai, ", "main kal yaad dila doongi."))
    synth = FakeSynthesizer(gate_from=0)
    rec = Recognizer("pehla sawaal", "aur doosra")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start(ws)
        say(ws)
        first = until(ws, is_("agent.text"))
        assert synth.gated.wait(5)
        barge(ws)
        cut = until(ws, is_("listening"))
        synth.gate.set()  # the held synthesis finishes; it must be discarded
        say(ws, speech_frames=10, tag=210)  # the rest of the new turn
        rest = until(ws, is_("idle"))
        assert reacks(ws)

    old_turn = first[0]["turn_id"]
    # Stop playback first: audio.flush is the first thing the browser gets.
    assert trace(cut) == ["audio.flush", "cancelling", "listening"]
    assert cut[0]["turn_id"] == old_turn
    assert cut[-1]["turn_id"] != old_turn  # a new turn, from the new speech
    assert llm.closed.is_set()
    # The discarded synthesis never became audio for the old turn.
    starts = [m for m in rest if is_("audio.start")(m)]
    assert [m["turn_id"] for m in starts] == [cut[-1]["turn_id"]]
    # Nothing was heard, so nothing of the cut reply is in history, and the
    # unanswered question is carried into the next reply.
    assert history(llm, 1) == [("user", "pehla sawaal aur doosra")]


def test_barge_in_mid_reply_stops_frames_and_keeps_what_was_heard(caplog) -> None:
    # Chunk 1 ("Theek hai,", 0.5 s of audio) is playing; chunk 2 is held
    # mid-synthesis; the model has paused.
    llm = ScriptedLLM(("Theek hai, ", "main kal yaad dila doongi. Aur "), hang_after=2)
    synth = FakeSynthesizer(audio_ms_per_char=50, gate_from=1)
    rec = Recognizer("kal yaad dilana", "ruko")
    with caplog.at_level(logging.INFO):
        with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
            start(ws)
            say(ws)
            until(ws, is_("frame"))
            assert synth.gated.wait(5)
            time.sleep(0.3)  # the user hears part of chunk 1
            barge(ws)
            cut = until(ws, is_("listening"))
            synth.gate.set()
            say(ws, speech_frames=10, tag=210)
            # The scripted model pauses on every call, so the second reply
            # is checked by what it was asked, not by its ending.
            until(ws, is_("agent.text"))

    flushed = trace(cut).index("audio.flush")
    assert trace(cut)[flushed:] == ["audio.flush", "cancelling", "listening"]
    assert synth.texts[:2] == ["Theek hai,", "main kal yaad dila doongi."]
    assert "Aur" not in synth.texts[2]  # the buffered word was never said
    assert llm.closed.is_set()
    # History: the question, and only the part of chunk 1 that had played.
    (user, said), new_turn = history(llm, 1)[:2], history(llm, 1)[2]
    assert user == ("user", "kal yaad dilana")
    assert said[0] == "assistant" and said[1] in ("Theek", "Theek hai,")
    assert new_turn == ("user", "ruko")
    logged = [r.getMessage() for r in caplog.records]
    assert any("SERVER-SIDE only, not PERF-3" in m for m in logged)


def test_barge_in_after_agent_done_while_audio_still_plays() -> None:
    # Every frame is sent and agent.done and audio.end are out, but the
    # browser is still playing: the state is still `speaking`.
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(audio_ms_per_char=50)  # 1.2 s of audio
    rec = Recognizer("kya haal hai", "bas")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start(ws)
        say(ws)
        done = until(ws, is_("audio.end"))
        time.sleep(0.3)
        barge(ws)
        cut = until(ws, is_("listening"))
        say(ws, speech_frames=10, tag=210)
        until(ws, is_("idle"))

    assert "agent.done" in trace(done) and "idle" not in trace(done)
    # audio.flush may follow audio.end: the audio was sent, not yet played.
    assert trace(cut) == ["audio.flush", "cancelling", "listening"]
    said = history(llm, 1)[1]
    assert said[0] == "assistant" and said[1] != "Theek hai, sab theek hai."


def test_a_short_noise_does_not_stop_the_reply() -> None:
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(audio_ms_per_char=50)
    rec = Recognizer("kya haal hai")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start(ws)
        say(ws)
        until(ws, is_("frame"))
        for i in range(6):  # 120 ms: VAD calls it speech, barge-in does not
            ws.send_bytes(frame(True, 100 + i))
        for _ in range(15):
            ws.send_bytes(frame(False))
        rest = until(ws, is_("idle"))
        assert reacks(ws)  # and the noise opened no turn afterwards

    assert "audio.flush" not in trace(rest) and "cancelling" not in trace(rest)
    assert trace(rest)[-3:] == ["agent.done", "audio.end", "idle"]


# --- The new turn keeps the user's opening audio --------------------------------


def test_the_new_turn_starts_at_the_first_sound_of_the_interruption() -> None:
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(audio_ms_per_char=50)
    rec = Recognizer("kya haal hai", "ruko")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start(ws)
        say(ws)
        until(ws, is_("frame"))
        for i in range(20):  # tagged silence while the agent speaks
            ws.send_bytes(frame(False, 100 + i))
        barge(ws, tag=200)
        until(ws, is_("listening"))
        say(ws, speech_frames=10, tag=210)
        until(ws, is_("idle"))

    audio = rec.audio[1]  # what the recogniser got for the new turn
    frames = [audio[i : i + FRAME_BYTES] for i in range(0, len(audio), FRAME_BYTES)]
    # VAD fired on the 4th speech frame (tag 203). The pre-roll is the 15
    # frames before it: 12 of silence (108-119), then 200-202, the speech VAD
    # was still confirming. Without the replay the turn would start at 210.
    assert frames[0] == frame(False, 108)
    assert frames[12:16] == [frame(True, t) for t in (200, 201, 202, 203)]


def test_speech_judged_as_the_reply_ends_becomes_a_normal_turn() -> None:
    # Speech that starts in the last moments of play-out and is still being
    # judged when `speaking` ends is the user's next turn, not lost.
    llm = ScriptedLLM(("Theek hai.",))
    synth = FakeSynthesizer(audio_ms_per_char=30)  # 0.3 s of audio
    rec = Recognizer("kya haal hai", "achha")
    with make_client(llm, synth, rec).websocket_connect("/ws/session") as ws:
        start(ws)
        say(ws)
        until(ws, is_("frame"))
        for i in range(5):  # speech_started, but short of a barge-in
            ws.send_bytes(frame(True, 200 + i))
        idle = until(ws, is_("idle"))
        say(ws, speech_frames=15, tag=205)
        turn = until(ws, is_("transcript.final"))

    assert "audio.flush" not in trace(idle)
    assert trace(turn)[:2] == ["listening", "thinking"]
    frames = rec.audio[1]
    assert frame(True, 200) in [
        frames[i : i + FRAME_BYTES] for i in range(0, len(frames), FRAME_BYTES)
    ]


# --- A cut question followed by a "hmm" still gets its answer -----------------


def test_hmm_after_a_cut_question_answers_the_question() -> None:
    # min_utterance_ms raised so the 200 ms "hmm" is discarded as too short.
    # (With the defaults it cannot be: VAD's 200 ms end hangover makes any
    # barge-in at least 340 ms long by the endpointer's measure.)
    llm = ScriptedLLM(("Theek hai, ", "sab theek hai."))
    synth = FakeSynthesizer(gate_from=0)
    rec = Recognizer("kal kitne baje meeting hai")
    client = make_client(llm, synth, rec, min_utterance_ms=500)
    with client.websocket_connect("/ws/session") as ws:
        start(ws)
        say(ws, speech_frames=30)
        until(ws, is_("agent.text"))
        assert synth.gated.wait(5)  # thinking, nothing heard yet
        barge(ws)
        cut = until(ws, is_("listening"))
        for _ in range(60):  # the "hmm" stops: too short to be a turn
            ws.send_bytes(frame(False))
        again = until(ws, is_("thinking"))
        synth.gate.set()
        until(ws, is_("idle"))

    assert trace(cut) == ["audio.flush", "cancelling", "listening"]
    assert trace(again) == ["thinking"]  # listening -> thinking, no transcript
    assert len(llm.calls) == 2
    assert history(llm, 1) == [("user", "kal kitne baje meeting hai")]
    assert again[-1]["turn_id"] == cut[-1]["turn_id"]  # answered as the new turn


def test_hmm_while_the_question_is_still_transcribing_answers_it() -> None:
    # The hardest order: the barge-in comes before the question's transcript,
    # the "hmm" is discarded, and only then does the transcript arrive.
    llm = ScriptedLLM(("Theek hai.",))
    synth = FakeSynthesizer()
    rec = Recognizer("kal kitne baje meeting hai", gated=True)
    client = make_client(llm, synth, rec, min_utterance_ms=500)
    try:
        with client.websocket_connect("/ws/session") as ws:
            start(ws)
            say(ws, speech_frames=30)
            until(ws, is_("thinking"))
            assert rec.started.wait(5)  # the question is being transcribed
            barge(ws)
            cut = until(ws, is_("listening"))
            for _ in range(60):
                ws.send_bytes(frame(False))
            until(ws, is_("thinking"))
            rec.gate.set()  # now the question's transcript arrives
            rest = until(ws, is_("idle"))
    finally:
        rec.gate.set()

    assert trace(cut) == ["audio.flush", "cancelling", "listening"]
    final = next(m for m in rest if is_("transcript.final")(m))
    assert final["text"] == "kal kitne baje meeting hai"
    assert history(llm, 0) == [("user", "kal kitne baje meeting hai")]
    replies = {m["turn_id"] for m in rest if is_("agent.text")(m)}
    assert replies == {cut[-1]["turn_id"]}


# --- The two pure parts --------------------------------------------------------


def judge(*kinds_and_probs) -> list[bool]:
    """Feed BargeIn (default config) one frame per (event kind, probability)."""
    barge_in = BargeIn(BargeInSettings(), Settings().vad, frame_ms=20)
    out = []
    for i, (kind, prob) in enumerate(kinds_and_probs):
        event = SpeechEvent(kind, i, 0.0) if kind else None
        out.append(barge_in.push(b"", event, prob))
    return out


def test_judge_fires_on_the_tenth_speech_frame_counted_from_onset() -> None:
    # speech_started counts as 4 (VAD's confirmation frames), then 6 more.
    fired = judge((SPEECH_STARTED, 1.0), *[(None, 1.0)] * 6)
    assert fired == [False] * 6 + [True]


def test_judge_counts_only_frames_over_the_threshold() -> None:
    fired = judge((SPEECH_STARTED, 1.0), *[(None, 0.4)] * 20)
    assert not any(fired)  # VAD still "in speech", but none of it counts


def test_judge_resets_on_speech_ended() -> None:
    fired = judge(
        (SPEECH_STARTED, 1.0),
        *[(None, 1.0)] * 5,
        (SPEECH_ENDED, 0.0),  # 9 counted: short by one
        (SPEECH_STARTED, 1.0),
        *[(None, 1.0)] * 5,
    )
    assert not any(fired)


def test_heard_text_keeps_whole_chunks_and_whole_words() -> None:
    spoken = [Spoken("Theek hai,", 0.0, 1.0), Spoken("main kal aaungi.", 1.0, 2.0)]
    assert heard_text(spoken, 0.0) == ""
    assert heard_text(spoken, 0.55) == "Theek"  # "Theek " then "h" of "hai"
    assert heard_text(spoken, 1.0) == "Theek hai,"
    assert heard_text(spoken, 1.6) == "Theek hai, main kal"
    assert heard_text(spoken, 5.0) == "Theek hai, main kal aaungi."
