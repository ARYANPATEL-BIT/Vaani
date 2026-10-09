"""Speech synthesis: one chunk of reply text in, audio out.

`build_synthesizers` is the one place that knows which implementation the
`[tts].engine` config value names. It imports that implementation lazily, so
a process with TTS disabled never imports piper at all.
"""

from functools import lru_cache

from vaani.config import TtsSettings
from vaani.tts.base import Synthesizer, TtsError

__all__ = ["Synthesizer", "TtsError", "build_synthesizers"]


def build_synthesizers(cfg: TtsSettings) -> dict[str, dict[str, Synthesizer]]:
    """Persona key -> language -> the process-wide synthesiser, built once.

    Loading a voice takes about a second and a half, so every app built in
    this process with the same settings shares them. lru_cache needs a
    hashable argument, so the config goes in as JSON (as for build_recognizer).
    """
    return _build(cfg.model_dump_json())


@lru_cache
def _build(cfg_json: str) -> dict[str, dict[str, Synthesizer]]:
    cfg = TtsSettings.model_validate_json(cfg_json)
    if cfg.engine == "piper":
        from vaani.tts.piper import build_piper

        return build_piper(cfg)
    raise TtsError(f"unknown tts.engine {cfg.engine!r}; only 'piper' exists")
