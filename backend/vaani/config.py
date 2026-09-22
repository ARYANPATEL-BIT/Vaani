"""Typed application settings for the Vaani backend.

All configuration for the backend is funnelled through the single `Settings`
object defined here. Non-secret values come from `config.toml`; secrets come
only from environment variables. Callers never read files or `os.environ`
directly — they call `get_settings()` and get one validated, typed object.

Why split by source: config.toml is committed and safe to read in review;
secrets must never be committed, so they are kept out of the file entirely and
injected from the environment at runtime.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

# config.toml lives beside the backend/ project root, one level above this
# package. Resolve it from this file's location so it is found no matter what
# the current working directory is.
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


class AudioSettings(BaseModel):
    """Audio capture parameters, grouped under [audio] in config.toml."""

    # Samples captured per second (Hz). 16 kHz is what the speech models expect.
    sample_rate: int = 16000
    # Number of audio channels. 1 = mono.
    channels: int = 1
    # Length of one audio frame in milliseconds.
    frame_ms: int = 20


class GatewaySettings(BaseModel):
    """WebSocket gateway parameters, grouped under [gateway] in config.toml."""

    # How often the gateway logs the per-interval valid-frame count, in seconds.
    frame_log_interval_s: float = 1.0


class Settings(BaseSettings):
    """The one typed settings object for the whole backend.

    Precedence (highest wins): values passed to the constructor, then
    environment variables, then config.toml, then pydantic defaults.
    """

    model_config = SettingsConfigDict(
        # Every backend env var is prefixed VAANI_ to avoid collisions.
        env_prefix="VAANI_",
        # Nested fields use a double underscore, e.g. VAANI_AUDIO__SAMPLE_RATE.
        env_nested_delimiter="__",
        # The TOML file the TomlConfigSettingsSource below will read.
        toml_file=_CONFIG_PATH,
        # Ignore unknown keys rather than erroring, so config.toml can carry
        # comments/keys this version does not yet model.
        extra="ignore",
    )

    # Non-secret settings (filled from config.toml, overridable by env).
    app_name: str = "vaani"
    audio: AudioSettings = AudioSettings()
    gateway: GatewaySettings = GatewaySettings()

    # Secret settings (env only; never written to config.toml). SecretStr keeps
    # the value out of logs and reprs unless explicitly unwrapped.
    secret_key: SecretStr | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Declare where settings come from and in what priority order.

        Order matters: the first source in the tuple wins on conflict. We put
        environment variables ahead of the TOML file so a secret or an override
        in the environment always beats a committed default.
        """
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings, building it once and caching it.

    Reading config and the environment happens a single time per process. The
    cache also gives every caller the same object. Tests that need a fresh read
    (e.g. after changing an env var) construct `Settings()` directly instead of
    calling this.
    """
    return Settings()
