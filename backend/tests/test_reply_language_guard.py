"""Reply language per turn, and the forced-language guard (fix/language-and-login).

Through the real gateway, with fakes as in test_reply_language.py: the real
VAD and endpointer on the speech fixture, a recogniser that reports what it
"picked", a scripted model that records every request, and two fake voices
at different rates.

  * Auto mode ("any"): the note after the user's message follows the
    language the ASR picked: English, Hindi, or Hinglish (a hi turn with
    Latin words). Nothing picked: no note, as before.
  * Forced modes: the session's language wins over what was picked.
  * The guard: in a forced session no chunk in the other script is shown or
    said, a wrong first chunk is retried once and then replaced by the
    fallback line, and the Hindi voice never receives a Latin letter.
"""

import logging
import re

import pytest

from tests.fake_asr import FakeRecognizer
from tests.fake_tts import FakeSynthesizer
from tests.test_asr_gateway import START
from tests.test_turn_llm import speak
from tests.test_turn_tts import is_, make_client, until
from tests.test_voice_route import ENGLISH_RATE, HINDI_RATE, spoken_rate
from vaani.asr import Transcript
from vaani.config import Settings
from vaani.language import strip_latin, turn_language
from vaani.providers.base import LLMProvider, TextChunk

NOTES = Settings(_env_file=None).reply_language
LATIN = re.compile(r"[A-Za-z]")


class PickingRecognizer(FakeRecognizer):
    """Hears `text` and reports `picked` as the language it chose."""

    def __init__(self, text: str, picked: str | None) -> None:
        super().__init__(text=text)
        self.picked = picked

    def _work(self, pcm: bytes) -> Transcript:
        heard = super()._work(pcm)
        return Transcript(heard.text, self.picked or "hi", picked=self.picked)


class SequencedLLM(LLMProvider):
    """Answers call N with replies[N] (the last one again after that), and
    records every call's messages."""

    def __init__(self, *replies: tuple[str, ...]) -> None:
        self.replies = replies
        self.calls: list[list] = []

    async def stream(self, messages, cancel):
        self.calls.append(list(messages))
        for text in self.replies[min(len(self.calls), len(self.replies)) - 1]:
            yield TextChunk(text)

    async def aclose(self) -> None:
        pass


def turn(
    reply_language: str,
    *replies: tuple[str, ...],
    heard: str = "kuch bhi",
    picked: str | None = None,
    turns: int = 1,
):
    """One session, `turns` spoken turns. Returns the model, the two voices
    and every message of the last turn up to idle."""
    voices = {
        "hi": FakeSynthesizer(sample_rate=HINDI_RATE, audio_ms_per_char=10),
        "en": FakeSynthesizer(sample_rate=ENGLISH_RATE, audio_ms_per_char=10),
    }
    llm = SequencedLLM(*(replies or (("Theek hai.",),)))
    client = make_client(llm, voices["hi"], PickingRecognizer(heard, picked))
    client.app.state.synthesizers = {"default": voices}
    with client.websocket_connect("/ws/session") as ws:
        ws.send_json({**START, "reply_language": reply_language})
        ws.receive_json()  # session.started
        for _ in range(turns):
            speak(ws)
            msgs = until(ws, is_("idle"))
    return llm, voices, msgs


def user_message(llm: SequencedLLM, call: int = 0) -> str:
    return llm.calls[call][-1].content


def shown(msgs: list) -> str:
    return "".join(m["delta"] for m in msgs if is_("agent.text")(m))


# --- Which note a turn gets (language.turn_language) ------------------------


@pytest.mark.parametrize(
    "forced, picked, transcript, language",
    [
        # Auto: the ASR's pick decides; a hi turn with Latin words is Hinglish.
        (None, "en", "hello, how are you", "en"),
        (None, "hi", "मुझे कल दिल्ली जाना है", "hi"),
        (None, "hi", "इसमें तो English है", "hinglish"),
        (None, None, "hello", None),  # forced ASR: no note at all
        # Forced: the session's language wins over anything picked.
        ("en", "hi", "मुझे कल दिल्ली जाना है", "en"),
        ("hi", "en", "hello, how are you", "hi"),
        ("hi", None, "hello", "hi"),
    ],
)
def test_turn_language(forced, picked, transcript, language) -> None:
    assert turn_language(forced, picked, transcript) == language


# --- Auto mode follows the input ----------------------------------------------


@pytest.mark.parametrize(
    "heard, picked, note",
    [
        ("hello, how are you", "en", "en"),
        ("मुझे कल दिल्ली जाना है", "hi", "hi"),
        ("इसमें तो English है", "hi", "hinglish"),
    ],
)
def test_auto_mode_notes_the_language_the_user_spoke(heard, picked, note) -> None:
    llm, _, _ = turn("any", heard=heard, picked=picked)
    assert user_message(llm) == f"{heard}\n\n{NOTES.reminders[note]}"
    assert "Reply language:" not in llm.calls[0][0].content  # no forced line


def test_auto_mode_with_a_forced_asr_adds_no_note() -> None:
    llm, _, _ = turn("any", heard="hello", picked=None)
    assert user_message(llm) == "hello"


def test_the_hindi_and_hinglish_notes_ask_for_english_words_in_devanagari() -> None:
    for language in ("hi", "hinglish"):
        assert "English word" in NOTES.reminders[language]
        assert "मीटिंग" in NOTES.reminders[language]


def test_history_keeps_the_words_as_spoken_without_the_note() -> None:
    llm, _, _ = turn("any", heard="hello", picked="en", turns=2)
    second = llm.calls[1]
    assert second[1].role == "user" and second[1].content == "hello"
    assert second[-1].content.endswith(NOTES.reminders["en"])


# --- Forced modes override ------------------------------------------------------


@pytest.mark.parametrize(
    "forced, heard, picked, reply",
    [
        ("en", "मुझे कल दिल्ली जाना है", "hi", "Sure."),
        ("hi", "hello, how are you", "en", "ठीक है।"),
    ],
)
def test_a_forced_language_beats_the_language_spoken(
    forced, heard, picked, reply
) -> None:
    llm, voices, msgs = turn(forced, (reply,), heard=heard, picked=picked)
    assert user_message(llm) == f"{heard}\n\n{NOTES.reminders[forced]}"
    assert voices[forced].texts == [reply]
    assert spoken_rate(msgs) == (HINDI_RATE if forced == "hi" else ENGLISH_RATE)


# --- The forced-Hindi guard -----------------------------------------------------


def test_forced_hindi_strips_latin_letters_before_the_voice(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.speaker"):
        _, voices, msgs = turn("hi", ("ठीक है, WiFi का पासवर्ड यह है।",))
    # The chunker cuts at the comma; the second chunk loses "WiFi".
    assert voices["hi"].texts == ["ठीक है,", "का पासवर्ड यह है।"]
    assert "WiFi" in shown(msgs)  # the screen keeps the word as written
    assert "stripped 4 Latin letter(s) from a hi chunk" in caplog.text
    assert caplog.text.isascii()  # a count, never the Devanagari text


@pytest.mark.parametrize(
    "reply",
    [
        ("ठीक है। ", "Here is the code: print(x). ", "बस इतना।"),
        ("आपका OTP 4821 है। ", "UPI से भेजिए।"),
        ("नमस्ते! ", "मैं meeting का link भेज दूँगी। ", "OK? ", "ठीक।"),
    ],
)
def test_the_hindi_voice_never_receives_a_latin_letter(reply) -> None:
    _, voices, _ = turn("hi", reply)
    assert voices["hi"].texts  # something was said
    assert not any(LATIN.search(text) for text in voices["hi"].texts)
    assert voices["en"].texts == []


def test_a_latin_chunk_mid_reply_is_not_spoken(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.speaker"):
        _, voices, _ = turn("hi", ("ठीक है। ", "Here is the code. ", "बस इतना।"))
    assert voices["hi"].texts == ["ठीक है।", "बस इतना।"]
    assert "en chunk not spoken in a forced hi reply" in caplog.text


def test_a_wrong_first_chunk_is_retried_and_never_shown(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.reply"):
        llm, voices, msgs = turn("hi", ("OK, sure. ", "Here you go."), ("ठीक है।",))
    assert len(llm.calls) == 2
    assert user_message(llm, 1).endswith(NOTES.retry_note)
    assert shown(msgs) == "ठीक है।"  # the first attempt never reached the screen
    done = next(m for m in msgs if is_("agent.done")(m))
    assert done["text"] == "ठीक है।"
    assert voices["hi"].texts == ["ठीक है।"]
    assert "forced hi reply began in en script" in caplog.text


@pytest.mark.parametrize(
    "forced, wrong", [("hi", ("Sure, here it is.",)), ("en", ("ठीक है।",))]
)
def test_two_wrong_attempts_say_the_fallback(forced, wrong) -> None:
    llm, voices, msgs = turn(forced, wrong)
    assert len(llm.calls) == 2  # one retry, no more
    fallback = NOTES.fallback[forced]
    assert shown(msgs) == fallback
    assert voices[forced].texts == [fallback]
    other = "en" if forced == "hi" else "hi"
    assert voices[other].texts == []


def test_auto_mode_has_no_check_and_no_strip() -> None:
    # "any": the first chunk's script still picks the voice (test_voice_route).
    llm, voices, msgs = turn("any", ("OK, ", "ठीक है।"))
    assert len(llm.calls) == 1
    assert voices["en"].texts == ["OK,", "ठीक है।"]
    assert shown(msgs) == "OK, ठीक है।"


def test_strip_latin_counts_letters_and_closes_up_spaces() -> None:
    assert strip_latin("WiFi का पासवर्ड") == ("का पासवर्ड", 4)
    assert strip_latin("ठीक है।") == ("ठीक है।", 0)
