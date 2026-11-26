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

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, SecretStr, field_validator, model_validator
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
    echo_enabled: bool = False


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
    # Less voiced audio than this, counted from speech_started, makes no turn.
    min_utterance_ms: int = 40
    # Audio kept from BEFORE speech_started, so the first syllable survives.
    preroll_ms: int = 300
    # Longest utterance kept; past this the turn is forced to end.
    max_utterance_ms: int = 30000


class BargeInSettings(BaseModel):
    """Interrupting the agent, under [barge_in] in config.toml.

    Starting values; tuned on day 14. Defaults mirror the TOML.
    """

    # Speech needed, counted from its onset, before it stops the agent.
    min_speech_ms: int = 200
    # Speech probability a frame needs to count toward min_speech_ms.
    threshold: float = 0.5


# Settings that moved out of [asr.whisper] into [asr] (feat/groq-stt), because
# both engines now read them: old key -> its new environment variable.
_MOVED_TO_ASR = {
    "language": "VAANI_ASR__LANGUAGE",
    "initial_prompt": "VAANI_ASR__INITIAL_PROMPT",
}


class WhisperSettings(BaseModel):
    """faster-whisper parameters, under [asr.whisper] in config.toml.

    No defaults: like an LLM model ID, these are written only in config.toml
    (or overridden from the environment on a GPU machine).
    """

    # Whisper size ("small", "large-v3") or a path to a converted model folder.
    model: str
    # "cpu" or "cuda". cuda never falls back to cpu: startup fails instead.
    device: str
    # Number format for the weights at run time, e.g. "int8", "float16".
    compute_type: str
    # CPU threads per inference; 0 lets CTranslate2 choose.
    cpu_threads: int
    # Candidate sequences kept while decoding; higher is slower, slightly better.
    beam_size: int
    # Temperatures tried in turn when a decode looks bad. [0.0] = one decode.
    temperature: list[float]

    @model_validator(mode="before")
    @classmethod
    def _refuse_moved_keys(cls, data: object) -> object:
        """Fail on an old-style language/prompt setting instead of ignoring it.

        A stale VAANI_ASR__WHISPER__LANGUAGE in backend/.env (or the old key
        left in config.toml) would otherwise be dropped without a word, since
        unknown keys are ignored. "before" means this sees the raw merged
        values from every source, before pydantic checks the fields. Only the
        key is named in the error, never its value.
        """
        if isinstance(data, dict):
            for key, new_var in _MOVED_TO_ASR.items():
                if key in data:
                    raise ValueError(
                        f"asr.whisper.{key} has moved to asr.{key}: rename "
                        f"VAANI_ASR__WHISPER__{key.upper()} to {new_var} in "
                        f"backend/.env or the environment (or move the key "
                        f"from [asr.whisper] to [asr] in config.toml)"
                    )
        return data


class GroqAsrSettings(BaseModel):
    """Groq's hosted Whisper, under [asr.groq] in config.toml.

    Used only when [asr].engine = "groq". The API key is the same
    VAANI_GROQ_API_KEY the LLM provider uses (Settings.groq_api_key).
    """

    # Exact model ID, e.g. "whisper-large-v3".
    model: str
    # Groq's OpenAI-compatible API root; /audio/transcriptions is appended.
    base_url: str
    # Sampling temperature, 0 to 1. 0 = always the most likely text.
    temperature: float
    # Per-process cap on transcription requests, checked before each one is
    # sent. Separate from [llm].max_requests_per_process.
    max_requests_per_process: int


class AsrSettings(BaseModel):
    """Speech recognition, under [asr] in config.toml."""

    # When false the gateway never transcribes and no model is loaded.
    enabled: bool = True
    # Which recogniser to build: local faster-whisper, or Groq's hosted Whisper.
    engine: Literal["faster-whisper", "groq"]
    # Process-wide inference threads; also the number of sessions that can be
    # transcribed at the same moment. faster-whisper only.
    max_concurrent: int
    # Longest we wait for one transcription before giving up on it.
    timeout_s: float
    # Re-decode the growing utterance this often while the user speaks, to
    # produce transcript.partial. 0 = partials off.
    partial_interval_ms: int
    # Forced language code, for both engines. Never auto-detect (see
    # docs/spikes/asr-hinglish.md).
    language: str
    # Example text in the style we want back (romanized Hinglish), for both
    # engines: faster-whisper's initial_prompt, Groq's prompt.
    initial_prompt: str
    whisper: WhisperSettings
    groq: GroqAsrSettings


class PersonaVoice(BaseModel):
    """One persona's voice in one language: [tts.piper.voices.<persona>.<lang>]."""

    voice: str  # Piper voice name, e.g. "hi_IN-priyamvada-medium"
    sha256: str  # of <voice>.onnx; checked at load and by fetch_models.py
    # Piper's length_scale: 1.0 = the voice's own pace, above 1 = slower.
    # None = the value in the voice's .onnx.json.
    length_scale: float | None = None


class PiperSettings(BaseModel):
    """Piper voices, under [tts.piper] in config.toml."""

    # Where <voice>.onnx (fetched) and <voice>.onnx.json (committed) live.
    models_dir: str
    # The piper-voices repository, pinned to one revision; fetch_models.py
    # appends the path it builds from each voice name.
    voices_url: str
    # Persona key -> language ("hi", "en") -> its voice. Every key of
    # [personas] needs one per language in vaani/language.py's LANGUAGES.
    voices: dict[str, dict[str, PersonaVoice]]
    # ONNX Runtime threads per synthesis. 0 = its default, one per CPU core
    # it can see (feat/render-deploy: the Docker image sets 1).
    intra_op_threads: int = 0


class TtsSettings(BaseModel):
    """Speech synthesis, under [tts] in config.toml."""

    # When false the agent replies in text only and no voice is loaded.
    enabled: bool = True
    # Which synthesiser to build. Only "piper" exists today.
    engine: str
    # Synthesis threads for the whole process.
    max_concurrent: int
    piper: PiperSettings


class ChunkerSettings(BaseModel):
    """Clause chunking of the reply, under [chunker] in config.toml."""

    # The first chunk is cut at the earliest boundary once it has this many
    # characters, and at a word boundary if it reaches first_max_chars.
    first_min_chars: int
    first_max_chars: int
    # Later chunks wait for a sentence end, up to this many characters.
    max_chars: int
    # Words whose trailing "." is not a sentence end ("Dr.").
    abbreviations: list[str]
    # Words a chunk may be cut in front of ("but", "lekin").
    conjunctions: list[str]


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

    # When false no provider chain is built and turns get no reply. Tests and
    # CI run with it off: they have no API keys, and build_chain refuses to
    # start without them.
    enabled: bool = True
    # Providers to try, first choice first. ProviderChain fails over along
    # this list.
    provider_order: list[str]
    # Paid requests allowed per process, across ALL providers together.
    max_requests_per_process: int
    # Completed user+assistant exchanges re-sent with every request.
    history_turns: int
    # IANA time zone of the date and time line added to every system prompt
    # (persona.assemble), e.g. "Asia/Kolkata".
    timezone: str
    gemini: GeminiSettings
    groq: GroqSettings

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, timezone: str) -> str:
        # A misspelt zone fails at startup, not on a user's turn.
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown time zone {timezone!r}") from exc
        return timezone


class GuardrailSettings(BaseModel):
    """Input guardrail, under [guardrail] in config.toml."""

    # Regular expressions, matched case-insensitively against the transcript
    # BEFORE it is put into a prompt. Any match blocks the turn.
    patterns: list[str]

    @field_validator("patterns")
    @classmethod
    def _compiles(cls, patterns: list[str]) -> list[str]:
        # A typo in a pattern fails at startup, not on a user's turn.
        for pattern in patterns:
            re.compile(pattern)
        return patterns


class DbSettings(BaseModel):
    """The session and turn database, under [db] in config.toml."""

    # When false no database is opened and nothing is recorded.
    enabled: bool = True
    # SQLite file; relative paths are resolved against backend/.
    path: str = "data/vaani.db"
    # At shutdown, how long to wait for queued rows to be written.
    close_timeout_s: float = 2.0


class FrontendSettings(BaseModel):
    """The built browser app, under [frontend] in config.toml."""

    # Vite's production build (npm run build), relative to backend/. app.py
    # serves it at / only when the folder exists: in the Docker image. In
    # local development Vite's own server serves the page instead.
    dist_dir: str = "../frontend/dist"


class AuthSettings(BaseModel):
    """Google sign-in and the session cookie, under [auth] (vaani/auth.py).

    google_client_id, session_secret and allowed_emails come from the
    environment or backend/.env only (VAANI_AUTH__...), never config.toml.
    create_app refuses to start, naming the variable, when auth is enabled
    and one is missing.
    """

    # When false nothing is checked: no sign-in, every socket accepted.
    enabled: bool = True
    # The OAuth client ID our Google ID tokens must be issued for (their aud).
    google_client_id: str | None = None
    # Key for the cookie's HMAC signature. At least 32 characters.
    session_secret: SecretStr | None = None
    # The only Google accounts allowed in. Compared lowercased.
    allowed_emails: list[str] = []
    # True: any Google account with a verified email gets in, and
    # allowed_emails is ignored (it may be empty). Anyone can then spend the
    # shared LLM quota, and one user cannot be locked out by email.
    allow_all_emails: bool = False
    # Exact browser origins (scheme://host:port) allowed to sign in and to
    # open /ws/session. Also the CORS allow-list.
    allowed_origins: list[str] = []
    # Send the cookie over HTTPS only. False for http://localhost in dev.
    secure_cookie: bool = False
    # Days a sign-in lasts before the cookie expires.
    cookie_days: int = 7
    # Seconds of clock difference with Google tolerated on iat/exp.
    clock_skew_s: int = 10
    # Seconds to wait for Google's certificate download on sign-in.
    google_timeout_s: float = 5.0

    @field_validator("allowed_emails")
    @classmethod
    def _lowercase(cls, emails: list[str]) -> list[str]:
        return [email.strip().lower() for email in emails]


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
        # A config error names the field and the reason but never the value:
        # pydantic would otherwise append "input_value=..." to the message,
        # which could print a secret, or a stale value from backend/.env
        # (WhisperSettings._refuse_moved_keys). Only the outermost model's
        # setting counts, so it is set here, once, for every section.
        hide_input_in_errors=True,
    )

    # Non-secret settings (filled from config.toml, overridable by env).
    app_name: str = "vaani"
    audio: AudioSettings = AudioSettings()
    gateway: GatewaySettings = GatewaySettings()
    vad: VadSettings
    endpoint: EndpointSettings = EndpointSettings()
    barge_in: BargeInSettings = BargeInSettings()
    asr: AsrSettings
    llm: LLMSettings
    tts: TtsSettings
    chunker: ChunkerSettings
    guardrail: GuardrailSettings
    db: DbSettings = DbSettings()
    auth: AuthSettings = AuthSettings()
    # Persona key -> system prompt. session.start's "persona" must be a key.
    personas: dict[str, str]
    # Which [personas] this server serves (feat/render-deploy). Only their
    # voices load at startup, about 100 MB of RAM each. Unset = every persona:
    # the validator below fills it in, so once loaded it is always a list.
    served_personas: list[str] | None = None
    # The built browser app, served at / when it exists (app.py).
    frontend: FrontendSettings = FrontendSettings()

    # Secret settings (env only; never written to config.toml). SecretStr keeps
    # the value out of logs and reprs unless explicitly unwrapped.
    secret_key: SecretStr | None = None
    # Env var VAANI_GEMINI_API_KEY. None if unset; the provider refuses to run.
    gemini_api_key: SecretStr | None = None
    # Env var VAANI_GROQ_API_KEY. Required only if "groq" is in provider_order.
    groq_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _served_are_personas(self) -> "Settings":
        """Unset served_personas means every persona; a name that is not a
        [personas] key, or an empty list, stops the server starting."""
        if self.served_personas is None:
            self.served_personas = list(self.personas)
        unknown = sorted(set(self.served_personas) - self.personas.keys())
        if unknown:
            raise ValueError(
                f"served_personas names {unknown}, which are not keys of [personas]"
            )
        if not self.served_personas:
            raise ValueError(
                "served_personas is empty; unset it to serve every persona"
            )
        return self

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
