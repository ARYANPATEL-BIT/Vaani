"""Provider-neutral interface for live speech Text-to-Speech (TTS) engines.

Follows the same provider/adapter architecture established in Vaani LLM providers,
decoupling caller logic from specific TTS implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TTSAudioChunk:
    """A chunk of synthesized PCM audio data with sample metadata."""

    audio_bytes: bytes
    sample_rate: int
    sample_width: int
    sample_channels: int


@dataclass(frozen=True)
class TTSResult:
    """The result of synthesizing text into a full audio waveform."""

    wav_bytes: bytes
    latency_s: float
    sample_rate: int
    channels: int
    sample_width: int
    provider_name: str
    model_name: str


class TTSProviderError(Exception):
    """Base error for all TTS provider failures."""


class ModelNotFoundError(TTSProviderError):
    """Raised when the specified model or configuration file cannot be found."""


class AuthenticationError(TTSProviderError):
    """Raised when provider credentials are missing or invalid."""


class SynthesisError(TTSProviderError):
    """Raised when audio synthesis fails."""


class TTSProvider(ABC):
    """Abstract base class for all TTS providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier of the provider (e.g. 'piper', 'sarvam')."""

    @abstractmethod
    def synthesize(self, text: str) -> TTSResult:
        """Synthesize text into a complete WAV audio result."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the provider is currently usable (model/deps present)."""
