"""Each reply is spoken by the voice of the script it is written in.

The rule itself (vaani/language.py), then the gateway end to end with fakes:
real VAD and endpointer on the speech fixture, the fake recogniser, a
scripted model and two fake voices. The two fakes run at DIFFERENT rates, so
audio.start and the frame size prove which voice spoke, not just which fake
was called.
"""

import logging

import pytest

from tests.fake_tts import FakeSynthesizer
from tests.test_turn_llm import ScriptedLLM, speak, start
from tests.test_turn_tts import is_, make_client, until
from vaani.language import reply_language

HINDI_RATE = 22050
ENGLISH_RATE = 16000  # no real voice runs at 16 kHz: here it marks "English"


@pytest.mark.parametrize(
    "text, language",
    [
        ("Sure, I'll remind you at 8 a.m.", "en"),
        ("ठीक है, मैं याद दिला दूँगी।", "hi"),
        # Mixed: one Devanagari word is enough for the Hindi voice.
        ("OK, मैं meeting set कर दूँगी।", "hi"),
        # Romanized Hindi has no Devanagari: the script, not the language.
        ("Theek hai, main kal yaad dila doongi.", "en"),
        ("8", "en"),
    ],
)
def test_reply_language_is_decided_by_script(text, language) -> None:
    assert reply_language(text) == language


def speak_reply(chunks: tuple[str, ...]):
    """Run one turn whose reply streams as `chunks`. Returns the two fake
    voices and every message up to idle."""
    # 10 ms of audio per character: even "Sure." (50 ms) fills a whole 20 ms
    # frame, so spoken_rate can check the frame size.
    voices = {
        "hi": FakeSynthesizer(sample_rate=HINDI_RATE, audio_ms_per_char=10),
        "en": FakeSynthesizer(sample_rate=ENGLISH_RATE, audio_ms_per_char=10),
    }
    client = make_client(ScriptedLLM(chunks), voices["hi"])
    client.app.state.synthesizers = {"default": voices}
    with client.websocket_connect("/ws/session") as ws:
        start(ws)
        speak(ws)
        msgs = until(ws, is_("idle"))
    return voices, msgs


def spoken_rate(msgs: list) -> int:
    """The rate audio.start declared; checked against the frames' size too."""
    rate = next(m for m in msgs if is_("audio.start")(m))["sample_rate"]
    frames = [m for m in msgs if isinstance(m, bytes)]
    assert max(len(f) for f in frames) == rate * 20 // 1000 * 2  # 20 ms frames
    return rate


def test_an_english_reply_is_spoken_by_the_english_voice() -> None:
    voices, msgs = speak_reply(("Sure, ", "I'll remind you at 8 a.m. tomorrow."))
    assert voices["en"].texts == ["Sure,", "I'll remind you at 8 a.m. tomorrow."]
    assert voices["hi"].texts == []
    assert spoken_rate(msgs) == ENGLISH_RATE


def test_a_mixed_reply_is_spoken_by_the_hindi_voice() -> None:
    voices, msgs = speak_reply(("ठीक है, ", "मैं meeting का link भेज दूँगी।"))
    assert voices["hi"].texts == ["ठीक है,", "मैं meeting का link भेज दूँगी।"]
    assert voices["en"].texts == []
    assert spoken_rate(msgs) == HINDI_RATE


def test_a_reply_that_drifts_script_stays_on_its_first_voice(caplog) -> None:
    # Known issue, by design: the voice is locked on the first chunk, so the
    # Devanagari sentence is said (and partly misread) by the English voice.
    with caplog.at_level(logging.WARNING, logger="vaani.speaker"):
        voices, msgs = speak_reply(("Sure. ", "ठीक है।"))
    assert voices["en"].texts == ["Sure.", "ठीक है।"]
    assert voices["hi"].texts == []
    assert spoken_rate(msgs) == ENGLISH_RATE
    assert "script drift: hi chunk said by the en voice" in caplog.text
