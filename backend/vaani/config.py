"""Typed application settings for the Vaani backend.

All configuration for the backend is funnelled through the single `Settings`
object defined here. Non-secret values come from `config.toml`; secrets come
only from environment variables. Callers never read files or `os.environ`
directly — they call `get_settings()` and get one validated, typed object.

Why split by source: config.toml is committed and safe to read in review;
secrets must never be committed, so they are kept out of the file entirely and
injected from the environment at runtime — either real environment variables
or the gitignored backend/.env file.
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
# backend/.env: optional, gitignored, holds secrets for local development.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


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
    # When true, every valid frame the server receives is sent straight back to
    # the client (the day-3 "echo" loopback). Turned off once real audio flows.
    echo_enabled: bool = True


class VadSettings(BaseModel):
    """Voice activity detection parameters, under [vad] in config.toml.

    The model file and its checksum have no defaults: like a provider model
    ID, they are set only in config.toml. The tuning values mirror the TOML so
    a test can build a VadSettings without restating every field.
    """

    # When false the gateway does not run VAD at all.
    enabled: bool = True
    # Silero ONNX file; relative paths are resolved against backend/.
    model_path: str
    # Expected sha256 of that file, verified at load.
    model_sha256: str
    # Speech probability at or above which a frame counts as speech.
    threshold: float = 0.5
    # Consecutive speech frames before speech_started fires.
    start_frames: int = 4
    # Consecutive silence frames before speech_ended fires.
    end_frames: int = 10


class EndpointSettings(BaseModel):
    """End-of-turn detection, under [endpoint] in config.toml.

    Deliberately separate from VadSettings: VAD's end_frames decides "speech
    stopped", these decide "the turn is over". Defaults mirror the TOML.
    """

    # When false (or when VAD is off) the gateway does no endpointing.
    enabled: bool = True
    # Silence after speech_ended before the turn counts as over.
    end_of_turn_silence_ms: int = 700
    # An utterance shorter than this produces no turn (a cough, a lone "mm").
    min_utterance_ms: int = 300
    # Audio kept from BEFORE speech_started, so the first syllable survives.
    preroll_ms: int = 300
    # Longest utterance kept; past this the turn is forced to end.
    max_utterance_ms: int = 30000


class GeminiSettings(BaseModel):
    """Gemini provider parameters, under [llm.gemini] in config.toml.

    No defaults here on purpose: a model ID or endpoint written in code would
    be a hardcoded value. config.toml is the only place these are set.
    """

    # Exact model ID, never a moving "-latest" alias, so latency numbers stay
    # reproducible across days.
    model: str
    # API root; the provider appends /models/{model}:streamGenerateContent.
    base_url: str
    # Seconds httpx waits for EACH step (connect, first byte, next chunk) —
    # not a limit on the whole response.
    timeout_s: float
    # Reasoning the model does before its first token. Lowest level = least
    # delay before we can start speaking.
    thinking_level: str


class GroqSettings(BaseModel):
    """Groq provider parameters, under [llm.groq] in config.toml.

    Like GeminiSettings, the required fields have no defaults: config.toml is
    the only place a model ID or endpoint is written.
    """

    # Exact model ID as Groq's /models endpoint lists it.
    model: str
    # API root of Groq's OpenAI-compatible API; the provider appends
    # /chat/completions.
    base_url: str
    # Seconds httpx waits for EACH step, as for Gemini.
    timeout_s: float
    # Only for reasoning models (gpt-oss). Left out of config => not sent,
    # because non-reasoning models reject these fields.
    reasoning_effort: str | None = None
    include_reasoning: bool | None = None


class LLMSettings(BaseModel):
    """Language model settings, under [llm] in config.toml."""

    # Providers to try, first choice first. ProviderChain fails over along
    # this list.
    provider_order: list[str]
    # Paid requests allowed per process, across ALL providers together.
    max_requests_per_process: int
    gemini: GeminiSettings
    groq: GroqSettings


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
        # Local secrets file. Missing is fine; real env vars still win.
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        # Ignore unknown keys rather than erroring, so config.toml can carry
        # comments/keys this version does not yet model.
        extra="ignore",
    )

    # Non-secret settings (filled from config.toml, overridable by env).
    app_name: str = "vaani"
    audio: AudioSettings = AudioSettings()
    gateway: GatewaySettings = GatewaySettings()
    vad: VadSettings
    endpoint: EndpointSettings = EndpointSettings()
    llm: LLMSettings

    # Secret settings (env only; never written to config.toml). SecretStr keeps
    # the value out of logs and reprs unless explicitly unwrapped.
    secret_key: SecretStr | None = None
    # Env var VAANI_GEMINI_API_KEY. None if unset; the provider refuses to run.
    gemini_api_key: SecretStr | None = None
    # Env var VAANI_GROQ_API_KEY. Required only if "groq" is in provider_order.
    groq_api_key: SecretStr | None = None

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
        in the environment always beats a committed default. The .env file
        sits just below real env vars, so an exported variable overrides it.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
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
