"""Day 12: the real Piper voice behind the Synthesizer interface.

NOT marked slow: loading the voice takes about a second and a chunk tens of
ms, so these run everywhere, CI included. They need the voice file, which is
not committed: run `uv run python scripts/fetch_models.py` first (CI does).
A missing voice fails here with that instruction, rather than skipping.
"""

import asyncio

import pytest

from vaani.config import Settings
from vaani.tts import TtsError, build_synthesizer
from vaani.tts.piper import PiperSynthesizer

CFG = Settings().tts


def synthesize(text: str, cancel: asyncio.Event | None = None) -> bytes | None:
    synth = build_synthesizer(CFG)  # cached: the voice loads once per run
    return asyncio.run(synth.synthesize(text, cancel or asyncio.Event()))


def test_voice_rate_is_read_from_the_voice_config() -> None:
    assert build_synthesizer(CFG).sample_rate == 22050


def test_a_chunk_becomes_pcm_of_plausible_length() -> None:
    pcm = synthesize("Theek hai, main aapko yaad dila doongi.")
    assert pcm is not None and len(pcm) % 2 == 0  # whole 16-bit samples
    seconds = len(pcm) / 2 / 22050
    assert 0.5 < seconds < 8.0, f"{seconds:.2f} s of audio"
    assert max(pcm[1::2]) > 0  # high bytes not all zero: not silence


def test_cancelled_before_start_returns_none() -> None:
    cancel = asyncio.Event()
    cancel.set()
    assert synthesize("namaste", cancel) is None


def test_wrong_hash_refuses_to_load() -> None:
    bad = CFG.model_copy(
        update={"piper": CFG.piper.model_copy(update={"model_sha256": "0" * 64})}
    )
    with pytest.raises(TtsError, match="sha256"):
        PiperSynthesizer(bad)
