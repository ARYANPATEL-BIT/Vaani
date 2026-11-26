"""Chatterbox: the only file in the studio that imports torch or chatterbox.

Two pieces of Chatterbox are used:

* The voice encoder (ve.pt, a small LSTM network, about 6 MB). It turns a
  recording into a speaker embedding: 256 numbers that describe WHO is
  speaking, not WHAT is said. Two recordings of one person give embeddings
  that point in nearly the same direction, and the cosine of the angle
  between them (1.0 = same direction) is the speaker check of ETH-2. It runs
  on CPU, loads at startup, and is the same encoder Chatterbox clones from.

* The full multilingual model (about 2 GB of weights): T3, a Llama-style
  network that predicts speech tokens from text, and S3Gen, which turns those
  tokens into a 24 kHz waveform. It loads on the FIRST generate, not at
  startup, and only one copy ever exists. Every waveform it returns already
  carries Resemble's Perth watermark, an inaudible signal that marks the audio
  as AI-made; nothing in the studio turns it off.

GPU memory: on this laptop the voice agent's Whisper large-v3 may already hold
several GB of the 8 GB card. If CUDA runs out of memory, loading or
generating raises GpuBusy and the half-built model is dropped, so the studio
stays up and the next request simply tries again. The studio is its own
process, so nothing here can touch the voice agent's memory.
"""

import gc
import logging
import threading
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from chatterbox.models.s3gen import S3GEN_SR
from chatterbox.models.voice_encoder import VoiceEncoder
from chatterbox.mtl_tts import MULTILINGUAL_T3_MODELS, ChatterboxMultilingualTTS
from huggingface_hub import snapshot_download

from voice_studio.config import StudioSettings
from voice_studio.model_errors import GpuBusy, ModelError

log = logging.getLogger("voice_studio.model")

# The voice encoder's input rate (a property of the trained network).
ENCODER_RATE = 16_000
MIB = 2**20


def _is_out_of_memory(exc: BaseException) -> bool:
    # cuBLAS reports a failed allocation as a plain RuntimeError, not as
    # torch.OutOfMemoryError, so both shapes count.
    if isinstance(exc, torch.OutOfMemoryError):
        return True
    text = str(exc)
    return isinstance(exc, RuntimeError) and (
        "out of memory" in text or "ALLOC_FAILED" in text
    )


def _release_gpu_memory() -> None:
    gc.collect()  # drop Python's last references to the half-built tensors
    if torch.cuda.is_available():
        torch.cuda.empty_cache()  # hand torch's cached blocks back to the driver


class SpeakerEncoder:
    """Chatterbox's voice encoder on CPU, for the enrolment speaker check."""

    def __init__(self, cfg: StudioSettings) -> None:
        folder = snapshot_download(
            cfg.hf_repo, revision=cfg.hf_revision, allow_patterns=["ve.pt"]
        )
        self._ve = VoiceEncoder()
        state = torch.load(
            Path(folder) / "ve.pt", map_location="cpu", weights_only=True
        )
        self._ve.load_state_dict(state)
        self._ve.eval()

    def embed(self, samples_16k: np.ndarray) -> np.ndarray:
        """Unit-length speaker embedding of one recording (16 kHz floats)."""
        with torch.inference_mode():
            per_clip = self._ve.embeds_from_wavs([samples_16k], ENCODER_RATE)
        vector = per_clip.mean(axis=0)
        return vector / np.linalg.norm(vector)


class Cloner:
    """The one Chatterbox Multilingual model, loaded on first use."""

    sample_rate = S3GEN_SR  # 24 kHz, the rate every sentence comes out at

    def __init__(self, cfg: StudioSettings) -> None:
        self._cfg = cfg
        self._model: ChatterboxMultilingualTTS | None = None

    def _ensure_loaded(self) -> ChatterboxMultilingualTTS:
        if self._model is not None:
            return self._model
        cfg = self._cfg
        if cfg.device == "cuda" and not torch.cuda.is_available():
            # Never fall back to CPU silently: a 10x slower run would look
            # like a bug in the studio, not a missing GPU.
            raise ModelError("device is cuda but torch finds no CUDA device")
        t3_file = MULTILINGUAL_T3_MODELS[cfg.t3_model]
        # The files from_local reads. No conds.pt: that is Resemble's built-in
        # voice, and the studio must only ever speak in an enrolled voice.
        files = [
            "ve.pt",
            t3_file,
            "s3gen.pt",
            "grapheme_mtl_merged_expanded_v1.json",
            "Cangjie5_TC.json",
        ]
        # Downloads on the first run only; later runs read the local cache.
        folder = snapshot_download(
            cfg.hf_repo, revision=cfg.hf_revision, allow_patterns=files
        )
        started = perf_counter()
        try:
            model = ChatterboxMultilingualTTS.from_local(
                folder, cfg.device, t3_model=cfg.t3_model
            )
        except Exception as exc:
            if _is_out_of_memory(exc):
                _release_gpu_memory()
                raise GpuBusy("not enough GPU memory to load the model") from exc
            raise
        # The spike found perth's watermarker silently None when setuptools
        # was too new. Refuse to run unwatermarked rather than find out later.
        if not callable(getattr(model.watermarker, "apply_watermark", None)):
            raise ModelError("the Perth watermarker did not load; refusing to run")
        self._model = model
        log.info(
            "chatterbox %s loaded on %s in %.1f s, %s",
            cfg.t3_model,
            cfg.device,
            perf_counter() - started,
            self._vram_text(),
        )
        return model

    def synthesize(
        self, reference: Path, sentences: list[tuple[str, str]], stop: threading.Event
    ) -> list[np.ndarray] | None:
        """Speak each (text, language) in the voice of `reference`.

        BLOCKING, runs on a worker thread. `stop` is the cancellation token:
        a sentence already inside the model cannot be interrupted, so it is
        checked between sentences. Returns None if it was set.
        """
        model = self._ensure_loaded()  # the first call can take ~40 s, uninterruptible
        if stop.is_set():
            return None  # the browser left during the load: skip conditioning too
        try:
            # Conditioning: the reference becomes the speaker embedding and
            # style tokens every sentence below is generated from.
            model.prepare_conditionals(str(reference))
            waves = []
            for text, language in sentences:
                if stop.is_set():
                    return None
                started = perf_counter()
                wave = model.generate(text, language_id=language)[0].numpy()
                spent = perf_counter() - started
                seconds = len(wave) / self.sample_rate
                log.info(
                    "sentence %s %d chars: %.2f s audio in %.2f s (rtf %.2f)",
                    language,
                    len(text),
                    seconds,
                    spent,
                    spent / max(seconds, 1e-6),
                )
                waves.append(wave)
            return waves
        except Exception as exc:
            if _is_out_of_memory(exc):
                _release_gpu_memory()
                raise GpuBusy("not enough GPU memory to generate") from exc
            raise
        finally:
            # No user's voice stays loaded between requests (ETH-4: after a
            # delete, nothing of that voice is left in this process).
            model.conds = None

    def stats(self) -> dict:
        on_cuda = self._cfg.device == "cuda" and torch.cuda.is_available()
        return {
            "model_loaded": self._model is not None,
            "device": self._cfg.device,
            "vram_allocated_mib": (
                round(torch.cuda.memory_allocated() / MIB) if on_cuda else None
            ),
            "vram_peak_mib": (
                round(torch.cuda.max_memory_allocated() / MIB) if on_cuda else None
            ),
        }

    def _vram_text(self) -> str:
        s = self.stats()
        if s["vram_allocated_mib"] is None:
            return "cpu"
        return f"vram {s['vram_allocated_mib']} MiB (peak {s['vram_peak_mib']} MiB)"
