"""Tests for settings loading in vaani.config.

Covers: defaults from config.toml, environment overrides, secrets from the
environment, and the invariant that secrets are not exposed in the object's
string form.
"""

import pytest
from pydantic import ValidationError

from vaani.config import Settings
from vaani.language import LANGUAGES


def test_defaults_from_config_toml() -> None:
    """The committed config.toml supplies the audio defaults."""
    settings = Settings()

    assert settings.app_name == "vaani"
    assert settings.audio.sample_rate == 16000
    assert settings.audio.frame_ms == 20


def test_env_overrides_toml(monkeypatch) -> None:
    """A nested env var (VAANI_AUDIO__SAMPLE_RATE) beats the TOML value."""
    monkeypatch.setenv("VAANI_AUDIO__SAMPLE_RATE", "8000")

    settings = Settings()

    assert settings.audio.sample_rate == 8000


def test_secret_read_from_env(monkeypatch) -> None:
    """A secret is populated from the environment, not from config.toml."""
    monkeypatch.setenv("VAANI_SECRET_KEY", "abc123")

    settings = Settings()

    assert settings.secret_key is not None
    assert settings.secret_key.get_secret_value() == "abc123"


def test_secret_absent_by_default() -> None:
    """With no env var set, the secret is simply None.

    `_env_file=None` skips backend/.env, so a developer's real local secrets
    cannot make this test pass or fail.
    """
    settings = Settings(_env_file=None)

    assert settings.secret_key is None


def test_secret_not_shown_in_repr(monkeypatch) -> None:
    """SecretStr keeps the raw value out of the object's string form."""
    monkeypatch.setenv("VAANI_SECRET_KEY", "do-not-print-me")

    settings = Settings()

    assert "do-not-print-me" not in repr(settings)


def test_llm_settings_from_config_toml() -> None:
    """Model, timeout and provider order come from config.toml."""
    settings = Settings(_env_file=None)

    assert settings.llm.provider_order == ["groq", "gemini"]
    assert settings.llm.gemini.model == "gemini-3.5-flash-lite"
    assert settings.llm.gemini.thinking_level == "minimal"
    assert settings.llm.groq.model  # set in config.toml, never in code
    assert settings.llm.groq.base_url.startswith("https://")
    assert settings.llm.max_requests_per_process > 0


def test_groq_key_only_from_env(monkeypatch) -> None:
    """VAANI_GROQ_API_KEY is read from the environment and stays masked."""
    monkeypatch.setenv("VAANI_GROQ_API_KEY", "groq-test-key")
    settings = Settings(_env_file=None)

    assert settings.groq_api_key.get_secret_value() == "groq-test-key"
    assert "groq-test-key" not in repr(settings)


def test_gemini_key_only_from_env(monkeypatch) -> None:
    """The key is read from VAANI_GEMINI_API_KEY; config.toml never sets one."""
    from vaani.config import _CONFIG_PATH

    monkeypatch.setenv("VAANI_GEMINI_API_KEY", "test-key-value")
    settings = Settings(_env_file=None)

    assert settings.gemini_api_key.get_secret_value() == "test-key-value"
    # No line in config.toml ASSIGNS a key (comments may mention the name).
    toml_lines = _CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    assignments = [ln for ln in toml_lines if "=" in ln and not ln.startswith("#")]
    assert not any("key" in ln.split("=")[0].lower() for ln in assignments)


def test_every_persona_has_a_voice_per_language() -> None:
    """Day 15: [tts.piper.voices] covers exactly the [personas] keys, and
    (feat/english-voice) each one every language, so the committed config
    never stops the server with "no [tts.piper.voices] entry"."""
    settings = Settings()
    voices = settings.tts.piper.voices
    assert voices.keys() == settings.personas.keys()
    assert all(set(v) == set(LANGUAGES) for v in voices.values())


def test_asr_engine_defaults_to_faster_whisper() -> None:
    """feat/groq-stt: local faster-whisper stays the committed default; the
    shared language and prompt now live in [asr], not [asr.whisper]."""
    asr = Settings(_env_file=None).asr

    assert asr.engine == "faster-whisper"
    assert asr.language == "hi"
    assert asr.initial_prompt  # set in config.toml, never in code
    # Not -turbo: with the romanized prompt it wrote Hindi in Latin letters
    # (docs/findings/groq-stt/script_20261125.txt).
    assert asr.groq.model == "whisper-large-v3"
    assert asr.groq.base_url.startswith("https://")
    assert asr.groq.max_requests_per_process > 0


def test_asr_engine_groq_from_env(monkeypatch) -> None:
    monkeypatch.setenv("VAANI_ASR__ENGINE", "groq")

    assert Settings(_env_file=None).asr.engine == "groq"


def test_unknown_asr_engine_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("VAANI_ASR__ENGINE", "whisper")  # the pre-groq name

    with pytest.raises(ValidationError, match="faster-whisper"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("VAANI_ASR__WHISPER__LANGUAGE", "VAANI_ASR__LANGUAGE"),
        ("VAANI_ASR__WHISPER__INITIAL_PROMPT", "VAANI_ASR__INITIAL_PROMPT"),
    ],
)
def test_old_asr_setting_names_stop_startup(monkeypatch, old, new) -> None:
    """A stale backend/.env line must not be silently ignored."""
    monkeypatch.setenv(old, "secret-looking-value")

    with pytest.raises(ValidationError, match=new) as info:
        Settings(_env_file=None)
    # Only the variable's NAME is in the message, never what it was set to.
    assert "secret-looking-value" not in str(info.value)
