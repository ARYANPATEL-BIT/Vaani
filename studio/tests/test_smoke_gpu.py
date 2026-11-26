"""The real model on a real GPU: one English and one Hindi sentence.

Marked slow (skipped by default) and skipped without CUDA. Run with:
    uv run pytest -m slow
The first run downloads about 2 GB of weights from Hugging Face.

The reference is backend/tests/fixtures/speech_16k_mono.wav, a committed clip
made by the Windows speech synthesiser (08-vad.md): no real person's voice.
"""

import threading
from pathlib import Path

import numpy as np
import perth
import pytest
import torch

from voice_studio.config import StudioSettings
from voice_studio.model import Cloner

REFERENCE = (
    Path(__file__).resolve().parents[2] / "backend/tests/fixtures/speech_16k_mono.wav"
)
# "This is a short test of the voice studio." in Hindi, written as escapes
# so the file stays ASCII.
HINDI = (
    "\u092f\u0939 \u090f\u0915 \u091b\u094b\u091f\u093e "
    "\u092a\u0930\u0940\u0915\u094d\u0937\u0923 \u0939\u0948\u0964"
)


@pytest.mark.slow
@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")
def test_one_english_and_one_hindi_sentence(tmp_path):
    cloner = Cloner(StudioSettings(data_dir=str(tmp_path), device="cuda"))
    waves = cloner.synthesize(
        REFERENCE,
        [("This is a short test of the voice studio.", "en"), (HINDI, "hi")],
        threading.Event(),
    )
    assert len(waves) == 2
    watermarker = perth.PerthImplicitWatermarker()
    for wave in waves:
        seconds = len(wave) / cloner.sample_rate
        assert 1.0 < seconds < 15.0  # said something, did not run away
        assert np.isfinite(wave).all() and np.abs(wave).max() <= 1.0
        # The Perth watermark is in every sentence (1.0 = present).
        assert watermarker.get_watermark(wave, sample_rate=cloner.sample_rate) > 0.5
    assert cloner.stats()["vram_peak_mib"] > 0
