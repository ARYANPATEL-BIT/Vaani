"""Unit tests for the TTS provider architecture in spikes/tts-hinglish.

Verifies:
1. Provider contract and factory
2. Piper provider availability and synthesis (offline, no API key)
3. Sarvam adapter boundary behavior (no network calls, credential guard)
"""

import sys
from pathlib import Path

# Add spikes/tts-hinglish to sys.path so providers is importable
SPIKE_DIR = Path(__file__).resolve().parent
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))

from providers import (  # noqa: E402
    AuthenticationError,
    PiperTTSProvider,
    SarvamTTSProvider,
    TTSResult,
    get_tts_provider,
)


def test_factory_default_piper() -> None:
    provider = get_tts_provider()
    assert isinstance(provider, PiperTTSProvider)
    assert provider.name == "piper"


def test_piper_is_available() -> None:
    provider = get_tts_provider("piper")
    assert provider.is_available() is True


def test_piper_synthesizes_hinglish_romanized() -> None:
    provider = get_tts_provider("piper")
    text = "Namaste, aaj hum real-time voice conversation ke baare mein baat karenge."
    result = provider.synthesize(text)

    assert isinstance(result, TTSResult)
    assert len(result.wav_bytes) > 100_000
    assert result.latency_s > 0
    assert result.sample_rate == 22050
    assert result.channels == 1
    assert result.sample_width == 2
    assert result.provider_name == "piper"


def test_piper_synthesizes_hinglish_devanagari() -> None:
    provider = get_tts_provider("piper")
    text = "नमस्ते, आज हम real-time voice conversation के बारे में बात करेंगे।"
    result = provider.synthesize(text)

    assert isinstance(result, TTSResult)
    assert len(result.wav_bytes) > 100_000
    assert result.latency_s > 0
    assert result.sample_rate == 22050
    assert result.channels == 1
    assert result.sample_width == 2
    assert result.provider_name == "piper"


def test_sarvam_adapter_boundary_without_key() -> None:
    provider = get_tts_provider("sarvam")
    assert isinstance(provider, SarvamTTSProvider)
    assert provider.name == "sarvam"
    assert provider.is_available() is False

    raised = False
    try:
        provider.synthesize("test sentence")
    except AuthenticationError as e:
        raised = True
        assert "not configured" in str(e)
    if not raised:
        raise AssertionError("Should have raised AuthenticationError")


def test_sarvam_adapter_boundary_with_key_raises_not_implemented() -> None:
    provider = get_tts_provider("sarvam", api_key="dummy-key-not-used")
    assert provider.is_available() is True

    raised = False
    try:
        provider.synthesize("test sentence")
    except NotImplementedError as e:
        raised = True
        assert "not implemented" in str(e).lower()
    if not raised:
        raise AssertionError("Should have raised NotImplementedError")


def test_invalid_provider_raises() -> None:
    raised = False
    try:
        get_tts_provider("nonexistent")
    except ValueError as e:
        raised = True
        assert "Unknown TTS provider" in str(e)
    if not raised:
        raise AssertionError("Should have raised ValueError")


if __name__ == "__main__":
    print("Running TTS provider tests...")
    test_factory_default_piper()
    print("  ✓ test_factory_default_piper passed")
    test_piper_is_available()
    print("  ✓ test_piper_is_available passed")
    test_piper_synthesizes_hinglish_romanized()
    print("  ✓ test_piper_synthesizes_hinglish_romanized passed")
    test_piper_synthesizes_hinglish_devanagari()
    print("  ✓ test_piper_synthesizes_hinglish_devanagari passed")
    test_sarvam_adapter_boundary_without_key()
    print("  ✓ test_sarvam_adapter_boundary_without_key passed")
    test_sarvam_adapter_boundary_with_key_raises_not_implemented()
    print("  ✓ test_sarvam_adapter_boundary_with_key_raises_not_implemented passed")
    test_invalid_provider_raises()
    print("  ✓ test_invalid_provider_raises passed")
    print("All TTS provider unit tests PASSED successfully!")
