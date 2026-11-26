"""Typed settings for the voice studio, read once at startup.

Same pattern as backend/vaani/config.py: non-secret values in studio/config.toml
(committed), overrides from the environment. The studio has NO secrets of its
own. The session cookie secret is the backend's, and the studio reads it
through the backend's own settings object (vaani.config.get_settings), so the
secret is defined in one place and never copied.

Overrides use the prefix VAANI_STUDIO__, for example VAANI_STUDIO__DEVICE=cuda.
They can also go in backend/.env, the one gitignored file for local overrides:
the backend ignores keys it does not model, and so does this class.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from vaani.config import WhisperSettings

# studio/ (the project root), whatever the working directory is.
STUDIO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = STUDIO_ROOT / "config.toml"
_ENV_PATH = STUDIO_ROOT.parent / "backend" / ".env"


class StudioSettings(BaseSettings):
    """Every studio setting. The comments in config.toml say why each value."""

    model_config = SettingsConfigDict(
        env_prefix="VAANI_STUDIO__",
        env_nested_delimiter="__",
        toml_file=_CONFIG_PATH,
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # --- the process -------------------------------------------------------
    host: str
    port: int
    # Per-user folders and the provenance log; relative to studio/.
    data_dir: str

    # --- the model -----------------------------------------------------------
    device: Literal["cpu", "cuda"]
    hf_repo: str
    # A Hugging Face commit hash, so the weights never change under us.
    hf_revision: str
    # Chatterbox's name for the multilingual checkpoint: "v3".
    t3_model: str

    # --- enrolment -----------------------------------------------------------
    sample_min_s: float
    sample_max_s: float
    challenge_max_s: float
    max_upload_bytes: int
    min_snr_db: float
    challenge_words: list[str]
    challenge_word_count: int
    challenge_ttl_s: float
    min_challenge_match: float
    min_speaker_similarity: float
    consent_text: str
    # The Whisper model that checks the challenge phrase. Its own copy, small
    # and on CPU, NOT the voice agent's (which may be large-v3 on the GPU).
    challenge_language: str
    whisper: WhisperSettings

    # --- generation ----------------------------------------------------------
    max_script_chars: int
    max_sentence_chars: int
    sentence_gap_ms: int
    max_generations_per_day: int
    disconnect_poll_s: float

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # First wins: constructor, real env vars, backend/.env, config.toml.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
        )

    def data_path(self) -> Path:
        return (STUDIO_ROOT / self.data_dir).resolve()


@lru_cache
def get_studio_settings() -> StudioSettings:
    return StudioSettings()
