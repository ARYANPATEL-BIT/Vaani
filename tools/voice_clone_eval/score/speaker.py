"""Speaker embeddings with SpeechBrain ECAPA-TDNN, and cosine similarity.

A speaker embedding is a fixed-length vector (192 numbers for this model) that
summarises *who* is speaking, not *what* is said. Two clips of the same person
give vectors that point in nearly the same direction; cosine similarity measures
that angle: 1.0 = same direction, 0 = unrelated.
"""

from pathlib import Path

import soundfile as sf
import torch
import torchaudio.functional as AF
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "spkrec-ecapa-voxceleb"
ECAPA_RATE = 16_000  # the model was trained on 16 kHz audio


def load_encoder(device: str = "cpu") -> EncoderClassifier:
    # COPY instead of the default symlink: Windows refuses symlinks without
    # Developer Mode, and a failed symlink would abort the download.
    return EncoderClassifier.from_hparams(
        source=MODEL_SOURCE,
        savedir=str(MODEL_DIR),
        run_opts={"device": device},
        local_strategy=LocalStrategy.COPY,
    )


def embed_wave(
    encoder: EncoderClassifier, wave: torch.Tensor, rate: int
) -> torch.Tensor:
    """wave: 1-D float tensor. Returns a 1-D embedding."""
    if rate != ECAPA_RATE:
        wave = AF.resample(wave, rate, ECAPA_RATE)
    with torch.inference_mode():
        return encoder.encode_batch(wave.unsqueeze(0)).squeeze()


def embed_file(encoder: EncoderClassifier, path: Path) -> torch.Tensor:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    return embed_wave(encoder, torch.from_numpy(data.mean(axis=1)), rate)


def cosine(a: torch.Tensor, b: torch.Tensor) -> float:
    return float(torch.nn.functional.cosine_similarity(a, b, dim=0))
