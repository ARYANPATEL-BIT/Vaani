"""TTS Provider abstraction package for Vaani live speech.

Provides pluggable TTS backends following the provider/adapter pattern.
Piper is the active default provider; Sarvam adapter is stubbed for future phases.
"""

from pathlib import Path
from typing import Any

from .base import (
    AuthenticationError,
    ModelNotFoundError,
    SynthesisError,
    TTSAudioChunk,
    TTSProvider,
    TTSProviderError,
    TTSResult,
)
from .piper import PiperTTSProvider
from .sarvam import SarvamTTSProvider

DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
DEFAULT_PIPER_ONNX = DEFAULT_MODEL_DIR / "hi_IN-priyamvada-medium.onnx"
DEFAULT_PIPER_JSON = DEFAULT_MODEL_DIR / "hi_IN-priyamvada-medium.onnx.json"


def get_tts_provider(
    provider_name: str = "piper",
    **kwargs: Any,
) -> TTSProvider:
    """Factory to retrieve a configured TTS provider instance.

    Default provider is 'piper', which runs entirely offline without API keys.
    """
    normalized = provider_name.strip().lower()
    if normalized == "piper":
        onnx_path = kwargs.get("model_onnx_path", DEFAULT_PIPER_ONNX)
        json_path = kwargs.get("model_json_path", DEFAULT_PIPER_JSON)
        return PiperTTSProvider(model_onnx_path=onnx_path, model_json_path=json_path)

    if normalized == "sarvam":
        return SarvamTTSProvider(
            api_key=kwargs.get("api_key"),
            speaker=kwargs.get("speaker", "anushka"),
            model=kwargs.get("model", "bulbul:v2"),
        )

    raise ValueError(
        f"Unknown TTS provider: {provider_name}. Expected 'piper' or 'sarvam'."
    )


__all__ = [
    "AuthenticationError",
    "ModelNotFoundError",
    "PiperTTSProvider",
    "SarvamTTSProvider",
    "SynthesisError",
    "TTSAudioChunk",
    "TTSProvider",
    "TTSProviderError",
    "TTSResult",
    "get_tts_provider",
]
