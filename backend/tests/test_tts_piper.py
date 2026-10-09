"""Day 12: the real Piper voice behind the Synthesizer interface.

NOT marked slow: loading the voice takes about a second and a chunk tens of
ms, so these run everywhere, CI included. They need the voice files, which are
not committed: run `uv run python scripts/fetch_models.py default` first (CI
does). A missing voice fails here with that instruction, rather than skipping.

Day 15: personas have their own voices, but these tests LOAD only the default
persona's voices, the ones CI fetches: Hindi, and since feat/english-voice
English. The other voices are checked through their committed .onnx.json
files, without their 63 MB .onnx.
"""

import asyncio
import json
from pathlib import Path

import pytest
from piper import PiperConfig

from vaani.app import create_app
from vaani.config import PersonaVoice, Settings, TtsSettings
from vaani.language import LANGUAGES
from vaani.tts import TtsError, build_synthesizers

CFG = Settings().tts
DEFAULT_HI = CFG.piper.voices["default"]["hi"]
DEFAULT_EN = CFG.piper.voices["default"]["en"]
MODELS = Path(__file__).resolve().parent.parent / CFG.piper.models_dir


def only(**voices: dict[str, PersonaVoice]) -> TtsSettings:
    """The committed [tts] with just these persona voices, switched on."""
    piper = CFG.piper.model_copy(update={"voices": voices})
    return CFG.model_copy(update={"enabled": True, "piper": piper})


# The default voices, and the Hindi voice file 1.5x slower: no other file.
TWO = only(
    default={"hi": DEFAULT_HI, "en": DEFAULT_EN},
    slow={"hi": DEFAULT_HI.model_copy(update={"length_scale": 1.5})},
)


def synthesize(
    text: str, cancel: asyncio.Event | None = None, persona="default", language="hi"
):
    synth = build_synthesizers(TWO)[persona][language]  # cached: loads once
    return asyncio.run(synth.synthesize(text, cancel or asyncio.Event()))


def committed_rate(voice: str) -> int:
    """The rate in the voice's committed .onnx.json, read as piper reads it."""
    text = (MODELS / f"{voice}.onnx.json").read_text(encoding="utf-8")
    return PiperConfig.from_dict(json.loads(text)).sample_rate


def test_voice_rate_is_read_from_the_voice_config() -> None:
    synths = build_synthesizers(TWO)["default"]
    assert synths["hi"].sample_rate == committed_rate(DEFAULT_HI.voice)
    assert synths["en"].sample_rate == committed_rate(DEFAULT_EN.voice)


@pytest.mark.parametrize(
    "persona, language",
    [(p, lang) for p in sorted(CFG.piper.voices) for lang in LANGUAGES],
)
def test_every_persona_voice_has_a_committed_config_with_a_rate(
    persona, language
) -> None:
    # What audio.start will declare for this persona, without its .onnx.
    assert committed_rate(CFG.piper.voices[persona][language].voice) == 22050


def test_a_chunk_becomes_pcm_of_plausible_length() -> None:
    pcm = synthesize("ठीक है, मैं आपको याद दिला दूँगी।")
    assert pcm is not None and len(pcm) % 2 == 0  # whole 16-bit samples
    seconds = len(pcm) / 2 / 22050
    assert 0.5 < seconds < 8.0, f"{seconds:.2f} s of audio"
    assert max(pcm[1::2]) > 0  # high bytes not all zero: not silence


def test_the_english_voice_speaks_latin_text() -> None:
    # The real English voice: its espeak-ng English data must load on this
    # machine (and on CI's Linux), not just the Hindi one.
    pcm = synthesize("Sure, I'll remind you at eight tomorrow.", language="en")
    assert pcm is not None and len(pcm) % 2 == 0
    seconds = len(pcm) / 2 / 22050
    assert 0.5 < seconds < 8.0, f"{seconds:.2f} s of audio"
    assert max(pcm[1::2]) > 0


def test_personas_sharing_a_voice_share_one_load_and_one_pool() -> None:
    synths = build_synthesizers(TWO)
    assert synths["default"]["hi"]._voice is synths["slow"]["hi"]._voice
    # One pool for every voice and language: max_concurrent holds.
    assert synths["default"]["hi"]._pool is synths["slow"]["hi"]._pool
    assert synths["default"]["hi"]._pool is synths["default"]["en"]._pool


def test_length_scale_slows_the_voice_down() -> None:
    text = "ठीक है, मैं कल सुबह आठ बजे आपको याद दिला दूँगी।"
    normal = len(synthesize(text) or b"")
    slow = len(synthesize(text, persona="slow") or b"")
    # 1.5x every sound's length. Durations are predicted with some noise,
    # so the check is loose: clearly longer, not exactly 1.5x.
    assert slow > 1.25 * normal, f"{slow / normal:.2f}x"


def test_cancelled_before_start_returns_none() -> None:
    cancel = asyncio.Event()
    cancel.set()
    assert synthesize("namaste", cancel) is None


def test_wrong_hash_refuses_to_load() -> None:
    with pytest.raises(TtsError, match="sha256"):
        build_synthesizers(
            only(default={"hi": DEFAULT_HI.model_copy(update={"sha256": "0" * 64})})
        )


def test_startup_refuses_a_missing_voice_and_names_the_fetch_command() -> None:
    gone = PersonaVoice(voice="hi_IN-nobody-medium", sha256="0" * 64)
    voices = {p: dict.fromkeys(LANGUAGES, gone) for p in Settings().personas}
    with pytest.raises(TtsError, match="scripts/fetch_models.py"):
        create_app(Settings(tts=only(**voices)))


def test_startup_refuses_a_persona_without_a_voice() -> None:
    with pytest.raises(TtsError, match="tutor"):
        create_app(Settings(tts=only(default={"hi": DEFAULT_HI, "en": DEFAULT_EN})))


def test_startup_refuses_a_persona_without_an_english_voice() -> None:
    hindi_only = {p: {"hi": DEFAULT_HI} for p in Settings().personas}
    with pytest.raises(TtsError, match=r"default\.en"):
        create_app(Settings(tts=only(**hindi_only)))
