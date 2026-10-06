"""Speech synthesis: one chunk of reply text in, audio out.

`build_synthesizer` is the one place that knows which implementation the
`[tts].engine` config value names. It imports that implementation lazily, so
a process with TTS disabled never imports piper at all.
"""

from functools import lru_cache

from vaani.config import TtsSettings
from vaani.tts.base import Synthesizer, TtsError

__all__ = ["Synthesizer", "TtsError", "build_synthesizer"]


def build_synthesizer(cfg: TtsSettings) -> Synthesizer:
    """The process-wide synthesiser for this config, built once.

    Loading a voice takes about a second, so every app built in this process
    with the same settings shares one. lru_cache needs a hashable argument,
    so the config goes in as JSON (as for build_recognizer).
    """
    return _build(cfg.model_dump_json())


@lru_cache
def _build(cfg_json: str) -> Synthesizer:
    cfg = TtsSettings.model_validate_json(cfg_json)
    if cfg.engine == "piper":
        from vaani.tts.piper import PiperSynthesizer

        return PiperSynthesizer(cfg)
    raise TtsError(f"unknown tts.engine {cfg.engine!r}; only 'piper' exists")
