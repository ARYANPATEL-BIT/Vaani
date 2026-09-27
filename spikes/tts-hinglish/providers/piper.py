"""Piper TTS provider implementation using local ONNX neural models.

Requires no external network connection, no API keys, and runs entirely locally.
"""

import io
import time
import wave
from pathlib import Path

from .base import (
    ModelNotFoundError,
    SynthesisError,
    TTSProvider,
    TTSResult,
)


class PiperTTSProvider(TTSProvider):
    """Local neural TTS engine backed by piper-tts and ONNX runtime."""

    def __init__(
        self,
        model_onnx_path: Path | str,
        model_json_path: Path | str,
    ) -> None:
        self.model_onnx = Path(model_onnx_path)
        self.model_json = Path(model_json_path)

    @property
    def name(self) -> str:
        return "piper"

    def is_available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return (
            self.model_onnx.exists()
            and self.model_onnx.stat().st_size > 10_000
            and self.model_json.exists()
        )

    def synthesize(self, text: str) -> TTSResult:
        if not self.is_available():
            raise ModelNotFoundError(
                f"Piper model not found or piper-tts not installed. "
                f"Expected ONNX: {self.model_onnx}"
            )

        from piper.voice import PiperVoice  # type: ignore

        voice = PiperVoice.load(str(self.model_onnx), config_path=str(self.model_json))

        buf = io.BytesIO()
        t0 = time.perf_counter()

        chunks = list(voice.synthesize(text))
        if not chunks:
            raise SynthesisError(
                "Piper returned 0 audio chunks — "
                "model may have failed to phonemize the input."
            )

        sample_rate = chunks[0].sample_rate
        sample_width = chunks[0].sample_width
        sample_channels = chunks[0].sample_channels

        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(sample_channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            for chunk in chunks:
                wav_file.writeframes(chunk.audio_int16_bytes)

        latency = time.perf_counter() - t0
        wav_bytes = buf.getvalue()

        return TTSResult(
            wav_bytes=wav_bytes,
            latency_s=latency,
            sample_rate=sample_rate,
            channels=sample_channels,
            sample_width=sample_width,
            provider_name=self.name,
            model_name=self.model_onnx.name,
        )
