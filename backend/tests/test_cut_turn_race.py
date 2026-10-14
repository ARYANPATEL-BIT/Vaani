"""fix/cut-turn-race: a final transcript arriving while a barge-in is still
sending audio.flush (or turn.state cancelling) for the turn it is cutting.

During those sends the cut turn is flushed but still current: the next turn
has not opened yet. A final for it must be carried into the next reply, never
answered as the cut turn.

The race tests build TurnPipeline directly, as test_ptt.py's fresh-VAD test
does, so the test owns send_json. Its HOOK delivers the waiting final from
inside one chosen send: it opens the fake recogniser's gate, then waits, still
inside the send, until the real AsrRunner has handed the final to turns.py.
Fakes everywhere (scripted VAD, recogniser, model, synthesiser): no network.

The last tests check ASR_FAILED (an error and a timeout) still ends in
turn.state idle in both modes, through the gateway.
"""

import asyncio
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

import vaani.turns as turns_mod
from tests.fake_tts import FakeSynthesizer
from tests.test_barge_in import Recognizer, ScriptedVad, frame, history, say
from tests.test_ptt import press, start_ptt
from tests.test_turn_llm import ScriptedLLM, start
from tests.test_turn_tts import is_, trace, until
from vaani.app import create_app
from vaani.asr.base import AsrError, Transcript
from vaani.config import GatewaySettings, Settings
from vaani.session import Session
from vaani.telemetry import Telemetry
from vaani.turns import TurnPipeline


class Vad(ScriptedVad):
    """ScriptedVad with the reset() a ptt press calls."""

    def reset(self) -> None:
        pass


@pytest.fixture(autouse=True)
def scripted_vad(monkeypatch) -> None:
    monkeypatch.setattr(turns_mod, "VadStream", Vad)


class FailsOnFail(Recognizer):
    """A decode whose scripted text is "FAIL" raises, as a recogniser error."""

    def _work(self, pcm: bytes) -> Transcript:
        result = super()._work(pcm)
        if result.text == "FAIL":
            raise AsrError("decode failed")
        return result


def settings_with(**update) -> Settings:
    """Test settings: echo off, ASR on; `update` overrides [endpoint] or
    [asr] keys (timeout_s is the only [asr] one used here)."""
    base = Settings()
    asr = {"enabled": True}
    if "timeout_s" in update:
        asr["timeout_s"] = update.pop("timeout_s")
    return Settings(
        gateway=GatewaySettings(echo_enabled=False),
        asr=base.asr.model_copy(update=asr),
        endpoint=base.endpoint.model_copy(update=update),
    )


async def wait_for(done, timeout: float = 5.0) -> None:
    deadline = perf_counter() + timeout
    while not done():
        assert perf_counter() < deadline, "timed out waiting"
        await asyncio.sleep(0.005)


class Harness:
    """A TurnPipeline whose send_json the test controls."""

    def __init__(self, rec, llm, hook, mode: str = "vad", **endpoint) -> None:
        self.rec = rec
        self.hook = hook  # message -> True: deliver the final inside this send
        self.sent: list[dict | bytes] = []
        synth = FakeSynthesizer()
        self.pipeline = TurnPipeline(
            settings_with(**endpoint),
            Session(session_id="race", persona="default", mode=mode),
            Telemetry("race"),
            self.send_json,
            self.send_bytes,
            None,  # the scripted VAD needs no model
            rec,
            llm,
            {"hi": synth, "en": synth},
        )

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)
        if self.hook is not None and self.hook(message):
            self.hook = None
            waiting = set(self.pipeline._awaiting_final)
            assert waiting, "no final was pending at the hook"
            self.rec.gate.set()
            # Still inside this send: the final reaches turns.py meanwhile.
            await wait_for(lambda: not waiting & self.pipeline._awaiting_final)

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    async def frames(self, speech: bool, count: int, tag: int = 0) -> None:
        for i in range(count):
            await self.pipeline.on_frame(frame(speech, tag + i))

    def states(self) -> list[str]:
        return [m["state"] for m in self.sent if is_("turn.state")(m)]

    async def until_idle(self) -> None:
        await wait_for(lambda: self.states()[-1:] == ["idle"])
        await self.pipeline.close()


def nth(kind: str, n: int = 1):
    """A hook firing on the n-th message `is_(kind)` matches."""
    seen = 0

    def match(message: dict) -> bool:
        nonlocal seen
        seen += is_(kind)(message)
        return seen == n

    return match


def turn_of(h: Harness, state: str, n: int = 1) -> str:
    """turn_id of the n-th turn.state `state`."""
    return [m for m in h.sent if is_(state)(m)][n - 1]["turn_id"]


def assert_cut_turn_silent(h: Harness, cut: str, next_turn: str) -> None:
    """After audio.flush for `cut`: only its cancelling and its transcript
    (carried, so still shown) name it, and no audio frame comes before the
    next turn's audio.start."""
    flush = next(i for i, m in enumerate(h.sent) if is_("audio.flush")(m))
    assert h.sent[flush]["turn_id"] == cut
    after = h.sent[flush + 1 :]
    named = [
        trace([m])[0] for m in after if isinstance(m, dict) and m.get("turn_id") == cut
    ]
    assert sorted(named) == ["cancelling", "transcript.final"]
    audio_start = next(
        i
        for i, m in enumerate(after)
        if is_("audio.start")(m) and m["turn_id"] == next_turn
    )
    assert not any(isinstance(m, bytes) for m in after[:audio_start])


ONE_REPLY = ["listening", "thinking", "speaking", "idle"]
CUT_THEN_REPLY = ["listening", "thinking", "cancelling", *ONE_REPLY]


# --- 1. Hands-free: the final arrives during audio.flush or cancelling ---------


@pytest.mark.parametrize("window", ["audio.flush", "cancelling"])
def test_a_final_during_the_barge_in_sends_is_carried_once(window) -> None:
    rec = Recognizer("pehla sawaal", "aur doosra", gated=True)
    llm = ScriptedLLM(("Theek hai.",))
    h = Harness(rec, llm, nth(window))

    async def go() -> None:
        await h.frames(True, 20)
        await h.frames(False, 50)  # T1 ends: thinking, its decode held
        await wait_for(rec.started.is_set)
        await h.frames(True, 10, tag=200)  # barge-in; the hook fires inside
        await h.frames(False, 50)  # T2 ends
        await h.until_idle()

    asyncio.run(go())
    assert h.states() == CUT_THEN_REPLY
    assert len(llm.calls) == 1
    assert history(llm, 0) == [("user", "pehla sawaal aur doosra")]
    assert_cut_turn_silent(h, turn_of(h, "thinking"), turn_of(h, "listening", 2))


# --- 2. A FAILED final inside window A ------------------------------------------


def test_a_failed_final_during_audio_flush_moves_nothing() -> None:
    # Before the fix: thinking -> idle mid-barge-in, then idle -> cancelling
    # raised out of on_frame, which ends the session (gateway.py).
    rec = FailsOnFail("FAIL", "aur doosra", gated=True)
    llm = ScriptedLLM(("Theek hai.",))
    h = Harness(rec, llm, nth("audio.flush"))

    async def go() -> None:
        await h.frames(True, 20)
        await h.frames(False, 50)
        await wait_for(rec.started.is_set)
        await h.frames(True, 10, tag=200)  # raises here if the state moved
        await h.frames(False, 50)  # the session goes on: T2 is answered
        await h.until_idle()

    asyncio.run(go())
    assert h.states() == CUT_THEN_REPLY  # no idle between thinking and cancelling
    failed = [m for m in h.sent if is_("error")(m)]
    assert [m["code"] for m in failed] == ["ASR_FAILED"]
    assert history(llm, 0) == [("user", "aur doosra")]


# --- 3. Push-to-talk: speak pressed while thinking ------------------------------


def test_a_final_during_a_press_barge_in_is_carried_once() -> None:
    rec = Recognizer("pehla sawaal", "aur doosra", gated=True)
    llm = ScriptedLLM(("Theek hai.",))
    h = Harness(rec, llm, nth("audio.flush"), mode="ptt")
    pipeline = h.pipeline

    async def go() -> None:
        await pipeline.on_ptt_start()
        await h.frames(True, 20)
        await pipeline.on_ptt_end()  # T1: thinking, its decode held
        await wait_for(rec.started.is_set)
        await pipeline.on_ptt_start()  # barge-in; the hook fires inside
        await h.frames(True, 10, tag=200)
        await pipeline.on_ptt_end()
        await h.until_idle()

    asyncio.run(go())
    assert h.states() == CUT_THEN_REPLY
    assert len(llm.calls) == 1
    assert history(llm, 0) == [("user", "pehla sawaal aur doosra")]
    assert_cut_turn_silent(h, turn_of(h, "thinking"), turn_of(h, "listening", 2))


# --- 4. An older cut turn's final, during a barge-in on a "hmm" ----------------


def test_an_older_final_during_a_barge_in_on_a_hmm_is_carried_once() -> None:
    # T0 is cut while transcribing, T1 is a "hmm" (discarded: min_utterance_ms
    # 300, as in test_barge_in.py) that waits for T0's words, and a barge-in
    # cuts T1. T0's final arrives while T1's audio.flush is sent.
    rec = Recognizer("pehla sawaal", "aur doosra", gated=True)
    llm = ScriptedLLM(("Theek hai.",))
    h = Harness(rec, llm, nth("audio.flush", 2), min_utterance_ms=300)

    async def go() -> None:
        await h.frames(True, 30)
        await h.frames(False, 50)  # T0 ends: thinking, its decode held
        await wait_for(rec.started.is_set)
        await h.frames(True, 10, tag=100)  # barge-in 1: T0 cut, T1 opens
        await h.frames(False, 60)  # T1 too short: thinking, for T0's words
        await h.frames(True, 30, tag=200)  # barge-in 2 on T1; the hook fires
        await h.frames(False, 50)  # T2 ends
        await h.until_idle()

    asyncio.run(go())
    assert h.states() == [
        "listening",
        "thinking",
        "cancelling",
        "listening",
        "thinking",
        "cancelling",
        *ONE_REPLY,
    ]
    assert len(llm.calls) == 1
    assert history(llm, 0) == [("user", "pehla sawaal aur doosra")]
    hmm = turn_of(h, "thinking", 2)
    assert not [m for m in h.sent if is_("agent.text")(m) and m["turn_id"] == hmm]


# --- 5. Regression: ASR_FAILED is followed by idle ------------------------------


@pytest.mark.parametrize("mode", ["vad", "ptt"])
@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_asr_failed_is_followed_by_idle(mode, failure) -> None:
    if failure == "error":
        rec, settings = FailsOnFail("FAIL"), settings_with()
    else:  # the decode is held past [asr].timeout_s
        rec, settings = Recognizer("late", gated=True), settings_with(timeout_s=0.1)
    llm = ScriptedLLM(("Theek hai.",))
    app = create_app(settings, recognizer=rec, llm=llm, synthesizer=FakeSynthesizer())
    try:
        with TestClient(app).websocket_connect("/ws/session") as ws:
            if mode == "ptt":
                start_ptt(ws)
                press(ws)
            else:
                start(ws)
                say(ws)
            msgs = until(ws, is_("idle"))
    finally:
        rec.gate.set()

    steps = trace(msgs)
    assert steps[steps.index("thinking") :] == ["thinking", "error", "idle"]
    assert next(m for m in msgs if is_("error")(m))["code"] == "ASR_FAILED"
    assert llm.calls == []
