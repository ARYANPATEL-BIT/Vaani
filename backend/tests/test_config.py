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
    """With no env var set, the secret is simply None."""
    settings = Settings()

    assert settings.secret_key is None


def test_secret_not_shown_in_repr(monkeypatch) -> None:
    """SecretStr keeps the raw value out of the object's string form."""
    monkeypatch.setenv("VAANI_SECRET_KEY", "do-not-print-me")

    settings = Settings()

    assert "do-not-print-me" not in repr(settings)
