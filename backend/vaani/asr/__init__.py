"""Speech recognition: utterance audio in, text out.

`build_recognizer` is the one place that knows which implementation the
`[asr].engine` config value names. It imports that implementation lazily, so
a process with ASR disabled never imports faster-whisper at all.
"""

from functools import lru_cache

from vaani.asr.base import AsrError, Recognizer, Transcript
from vaani.config import AsrSettings

__all__ = ["AsrError", "Recognizer", "Transcript", "build_recognizer"]


def build_recognizer(cfg: AsrSettings, sample_rate: int) -> Recognizer:
    """The process-wide recogniser for this config, built once.

    Loading a Whisper model takes seconds and hundreds of MB, so every app
    built in this process with the same settings (tests build many) shares
    one. lru_cache needs hashable arguments, so the config goes in as JSON.
    """
    return _build(cfg.model_dump_json(), sample_rate)


@lru_cache
def _build(cfg_json: str, sample_rate: int) -> Recognizer:
    cfg = AsrSettings.model_validate_json(cfg_json)
    if cfg.engine == "whisper":
        from vaani.asr.whisper import WhisperRecognizer

        return WhisperRecognizer(cfg, sample_rate)
    raise AsrError(f"unknown asr.engine {cfg.engine!r}; only 'whisper' exists")
