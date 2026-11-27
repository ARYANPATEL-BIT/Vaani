"""pick_language: each ASR engine chooses English or [asr].language per turn.

Why (docs/findings/language/asr_experiment_20261127.txt): forced "hi" writes
some English speech in Devanagari letters, and plain auto-detect writes pure
Hindi as Urdu, in Arabic script. So:
  * Groq sends two requests at once, auto and forced, and keeps the auto one
    only if Groq says it heard English;
  * faster-whisper runs detect_language first, and decodes as English only
    when English's probability reaches english_min_prob.
Either way the Transcript says what it picked (`picked`), which is what the
reply-language note follows (test_reply_language_guard.py). No test here
calls Groq or loads a model.
"""

import asyncio

import faster_whisper
import httpx
import pytest
from pydantic import SecretStr

from tests.test_asr_groq import KEY, PCM, form_fields, groq_cfg
from tests.test_asr_whisper import asr_cfg
from vaani.asr import AsrError, Transcript
from vaani.asr.groq import GroqRecognizer
from vaani.asr.whisper import WhisperRecognizer
from vaani.config import Settings
from vaani.spend import RequestCap

# --- Groq: two requests at once ---------------------------------------------


def two_answers(detected: str, auto_text: str, forced_text: str, seen: list):
    """A handler answering the auto request (no language field) as verbose_json
    with `detected`, and the forced one with `forced_text`."""

    def handler(request: httpx.Request) -> httpx.Response:
        fields = form_fields(request)
        seen.append(fields)
        if "language" in fields:
            return httpx.Response(200, json={"text": forced_text})
        return httpx.Response(200, json={"text": auto_text, "language": detected})

    return handler


def pick_with(handler, cap: RequestCap | None = None) -> GroqRecognizer:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GroqRecognizer(
        groq_cfg(pick=True), 16000, SecretStr(KEY), cap or RequestCap(10), client
    )


def test_the_committed_config_picks_on_groq_but_not_on_cpu_whisper() -> None:
    asr = Settings(_env_file=None).asr
    assert asr.groq.pick_language is True
    # cpu/small: the detection pass costs ~6.8 s and changes no transcript.
    assert asr.whisper.pick_language is False
    assert asr.language == "hi"


def test_groq_sends_one_auto_and_one_forced_request() -> None:
    seen: list = []
    rec = pick_with(two_answers("English", " hello there ", "हेलो देयर", seen))
    asyncio.run(rec.transcribe(PCM, asyncio.Event()))

    auto = [f for f in seen if "language" not in f]
    forced = [f for f in seen if "language" in f]
    assert len(auto) == 1 and len(forced) == 1
    # Only verbose_json names the language Groq detected.
    assert auto[0]["response_format"] == b"verbose_json"
    assert forced[0]["language"] == b"hi"
    assert forced[0]["response_format"] == b"json"
    assert auto[0]["file"] == forced[0]["file"]  # the same audio, twice


def test_groq_keeps_the_auto_text_when_it_heard_english() -> None:
    rec = pick_with(two_answers("English", " hello there ", "हेलो देयर", []))
    result = asyncio.run(rec.transcribe(PCM, asyncio.Event()))
    assert result == Transcript("hello there", "en", picked="en")


@pytest.mark.parametrize("detected", ["Urdu", "Hindi", "Latin", ""])
def test_groq_keeps_the_forced_text_for_anything_but_english(detected) -> None:
    # Urdu is the real case: Groq's auto writes pure Hindi in Arabic script.
    rec = pick_with(two_answers(detected, "مجھے کل", " मुझे कल ", []))
    result = asyncio.run(rec.transcribe(PCM, asyncio.Event()))
    assert result == Transcript("मुझे कल", "hi", picked="hi")


def test_groq_counts_both_requests_before_sending_either() -> None:
    seen: list = []
    cap = RequestCap(3)
    rec = pick_with(two_answers("English", "hi", "hi", seen), cap)
    asyncio.run(rec.transcribe(PCM, asyncio.Event()))
    assert cap.used == 2
    # One request left under the cap: refused whole, nothing sent.
    with pytest.raises(AsrError, match="request cap"):
        asyncio.run(rec.transcribe(PCM, asyncio.Event()))
    assert len(seen) == 2 and cap.used == 2


def test_groq_one_failed_request_fails_the_turn_and_stops_the_other() -> None:
    other_finished = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if "language" in form_fields(request):
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        await asyncio.sleep(5)  # the auto one hangs; TaskGroup must cancel it
        other_finished.append(True)
        return httpx.Response(200, json={"text": "x", "language": "English"})

    rec = pick_with(handler)

    async def scenario() -> None:
        with pytest.raises(AsrError, match="rate limited"):
            await asyncio.wait_for(rec.transcribe(PCM, asyncio.Event()), 2)

    asyncio.run(scenario())
    assert other_finished == []


def test_groq_cancel_mid_pick_returns_none_at_once() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json={"text": "late"})

    rec = pick_with(handler)

    async def scenario() -> Transcript | None:
        cancel = asyncio.Event()
        asyncio.get_running_loop().call_later(0.05, cancel.set)
        return await asyncio.wait_for(rec.transcribe(PCM, cancel), 1)

    assert asyncio.run(scenario()) is None


# --- faster-whisper: detect, then decode forced to the winner ---------------


class DetectingModel:
    """detect_language answers with `english`'s probability; transcribe
    records the language it was forced to."""

    english = 0.0
    detect_calls = 0
    languages: list = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def detect_language(self, audio, vad_filter=False):
        DetectingModel.detect_calls += 1
        assert vad_filter is True  # silence trimmed, as in the decode
        probs = [("en", self.english), ("ur", 0.5), ("hi", 0.4)]
        return "en", self.english, probs

    def transcribe(self, audio, **kwargs):
        DetectingModel.languages.append(kwargs.get("language"))

        class Info:
            language = kwargs.get("language")

        class Segment:
            text = " words "

        return iter([Segment()]), Info()


@pytest.fixture
def detecting_model(monkeypatch):
    DetectingModel.detect_calls, DetectingModel.languages = 0, []
    monkeypatch.setattr(faster_whisper, "WhisperModel", DetectingModel)
    return DetectingModel


@pytest.mark.parametrize(
    "english, picked",
    # 1.00 on every English clip, at most 0.25 on every other (the findings).
    [(1.0, "en"), (0.5, "en"), (0.49, "hi"), (0.25, "hi"), (0.0, "hi")],
)
def test_whisper_picks_english_only_at_or_over_the_threshold(
    detecting_model, english, picked
) -> None:
    detecting_model.english = english
    rec = WhisperRecognizer(asr_cfg(pick_language=True, english_min_prob=0.5), 16000)
    result = asyncio.run(rec.transcribe(b"\x00\x00" * 16000, asyncio.Event()))
    # [0] is the startup warm-up, forced as always.
    assert detecting_model.languages[1:] == [picked]
    assert result == Transcript("words", picked, picked=picked)


def test_whisper_without_pick_never_detects_and_reports_no_pick(
    detecting_model,
) -> None:
    detecting_model.english = 1.0
    rec = WhisperRecognizer(asr_cfg(pick_language=False), 16000)
    result = asyncio.run(rec.transcribe(b"\x00\x00" * 16000, asyncio.Event()))
    assert detecting_model.detect_calls == 0
    assert detecting_model.languages[1:] == ["hi"]
    # Forced: says nothing about what was spoken, so no note follows it.
    assert result == Transcript("words", "hi", picked=None)
