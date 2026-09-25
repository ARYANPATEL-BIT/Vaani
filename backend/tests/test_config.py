"""Tests for settings loading in vaani.config.

Covers: defaults from config.toml, environment overrides, secrets from the
environment, and the invariant that secrets are not exposed in the object's
string form.
"""

from vaani.config import Settings


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

    assert settings.llm.provider_order == ["gemini"]
    assert settings.llm.gemini.model == "gemini-3.5-flash-lite"
    assert settings.llm.gemini.thinking_level == "minimal"
    assert settings.llm.max_requests_per_process > 0


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
