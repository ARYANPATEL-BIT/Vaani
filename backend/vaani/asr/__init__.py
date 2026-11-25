"""Speech recognition: utterance audio in, text out.

`build_recognizer` is the one place that knows which implementation the
`[asr].engine` config value names. It imports that implementation lazily, so
a process with ASR disabled, or with engine = "groq", never imports
faster-whisper at all.
"""

import logging
from functools import lru_cache

from pydantic import SecretStr

from vaani.asr.base import AsrError, Recognizer, Transcript
from vaani.config import AsrSettings
from vaani.spend import RequestCap

__all__ = ["AsrError", "Recognizer", "Transcript", "build_recognizer"]

log = logging.getLogger("vaani.asr")


def build_recognizer(
    cfg: AsrSettings, sample_rate: int, groq_api_key: SecretStr | None
) -> Recognizer:
    """The recogniser [asr].engine names. Raises AsrError if it cannot run.

    `groq_api_key` is Settings.groq_api_key, read only for engine = "groq".
    """
    if cfg.engine == "groq":
        return _build_groq(cfg, sample_rate, groq_api_key)
    return _build_whisper(cfg.model_dump_json(), sample_rate)


def _build_groq(
    cfg: AsrSettings, sample_rate: int, api_key: SecretStr | None
) -> Recognizer:
    """Not cached: there is no model to load, only an HTTP client to make."""
    if api_key is None or not api_key.get_secret_value():
        # Name the variable, never a value.
        raise AsrError(
            "asr.engine is 'groq' but VAANI_GROQ_API_KEY is not set (env or "
            "backend/.env); set it, or set [asr] engine = 'faster-whisper'"
        )
    if cfg.partial_interval_ms:
        raise AsrError(
            "asr.engine is 'groq' but [asr] partial_interval_ms is "
            f"{cfg.partial_interval_ms}; set it to 0: each partial would be "
            "another paid request, and Groq allows 20 a minute"
        )
    from vaani.asr.groq import GroqRecognizer

    # Its own cap, separate from the LLM's ([llm].max_requests_per_process).
    cap = RequestCap(cfg.groq.max_requests_per_process)
    # whisper.py logs its own model load; this is the groq equivalent, so the
    # server log always says which engine is transcribing.
    log.info(
        "asr engine groq: %s, audio is sent to %s", cfg.groq.model, cfg.groq.base_url
    )
    return GroqRecognizer(cfg, sample_rate, api_key, cap)


@lru_cache
def _build_whisper(cfg_json: str, sample_rate: int) -> Recognizer:
    """The process-wide Whisper model for this config, built once.

    Loading a Whisper model takes seconds and hundreds of MB, so every app
    built in this process with the same settings (tests build many) shares
    one. lru_cache needs hashable arguments, so the config goes in as JSON.
    """
    from vaani.asr.whisper import WhisperRecognizer

    return WhisperRecognizer(AsrSettings.model_validate_json(cfg_json), sample_rate)
