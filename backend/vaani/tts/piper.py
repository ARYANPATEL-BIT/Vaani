"""Piper behind the Synthesizer interface.

Piper turns text into speech in two steps: espeak-ng converts the letters to
phonemes (the sounds), then a neural network (VITS, run with ONNX Runtime)
turns those phonemes into audio samples. Both run on the CPU.

Synthesis is too slow for the event loop (tens to hundreds of ms against
VAD's ~1 ms), so it runs on a worker thread from a pool this class owns, as
Whisper does. ONNX Runtime releases Python's GIL while it computes, so the
event loop keeps ingesting frames meanwhile.

Piper is NOT a streaming synthesiser: one call to the network produces one
sentence's audio, all at once, and cannot be stopped part-way. It yields one
piece per sentence of the text it is given, so the earliest a synthesis can
stop is between sentences. The chunker hands it about one clause or sentence
at a time, so in practice a cancelled chunk runs to its end on the thread
and its audio is thrown away.
"""

import asyncio
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from vaani.config import TtsSettings
from vaani.tts.base import Synthesizer, TtsError

log = logging.getLogger("vaani.tts")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve(path: str) -> Path:
    """config.toml paths are relative to backend/, whatever the cwd is."""
    p = Path(path)
    return p if p.is_absolute() else _BACKEND_ROOT / p


class PiperSynthesizer(Synthesizer):
    """One loaded Piper voice, shared by every session in the process."""

    def __init__(self, cfg: TtsSettings) -> None:
        p = cfg.piper
        model = _resolve(p.model_path)
        if not model.exists():
            raise TtsError(
                f"Piper voice {model} is missing; run "
                "`uv run python scripts/fetch_models.py`"
            )
        # Checked before the file reaches ONNX Runtime, like the VAD model: a
        # wrong or truncated voice fails at startup, not on a user's turn.
        actual = hashlib.sha256(model.read_bytes()).hexdigest()
        if actual != p.model_sha256:
            raise TtsError(
                f"Piper voice {model} has sha256 {actual}, "
                f"config expects {p.model_sha256}"
            )
        # Imported here, not at the top: a process with TTS disabled never
        # imports piper at all.
        from piper import PiperVoice

        started = perf_counter()
        self._voice = PiperVoice.load(model, config_path=_resolve(p.config_path))
        # 22050 Hz for the medium voices; read from the voice, never assumed.
        self.sample_rate = self._voice.config.sample_rate
        # Our own pool, sized from config, as for Whisper: nothing else queues
        # on it, and its size is ours to set.
        self._pool = ThreadPoolExecutor(
            max_workers=cfg.max_concurrent, thread_name_prefix="tts"
        )
        # The first synthesis loads espeak-ng and warms ONNX Runtime; do it
        # now so a user's first reply does not pay for it.
        self._run("namaste", threading.Event())
        log.info(
            "piper %s (%d Hz) loaded and warmed up in %.2f s",
            model.name,
            self.sample_rate,
            perf_counter() - started,
        )

    def _run(self, text: str, stop: threading.Event) -> bytes | None:
        """Runs on a pool thread. Returns None if `stop` was set."""
        parts: list[bytes] = []
        # One AudioChunk per sentence of `text`. Each step runs the network
        # once; between steps is the only place synthesis can be stopped.
        for chunk in self._voice.synthesize(text):
            if stop.is_set():
                return None
            parts.append(chunk.audio_int16_bytes)
        if stop.is_set():
            return None
        return b"".join(parts)

    async def synthesize(self, text: str, cancel: asyncio.Event) -> bytes | None:
        # `stop` is a threading.Event, not the asyncio.Event: the worker thread
        # reads it, and asyncio objects are only safe on the loop's own thread.
        stop = threading.Event()
        loop = asyncio.get_running_loop()
        work = loop.run_in_executor(self._pool, self._run, text, stop)
        cancelled = asyncio.ensure_future(cancel.wait())
        try:
            await asyncio.wait({work, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            if cancel.is_set():
                # Ask the thread to stop at its next sentence, then wait for
                # it: returning means "the thread is free again".
                stop.set()
                await asyncio.wait({work})
                return None
            return work.result()
        except asyncio.CancelledError:
            raise  # teardown: `finally` tells the thread to stop
        except Exception as exc:
            raise TtsError(f"piper synthesis failed: {exc}") from exc
        finally:
            cancelled.cancel()
            if not work.done():
                # Our task was cancelled mid-synthesis. The thread runs on to
                # its next sentence; nobody will read its result.
                stop.set()
                work.add_done_callback(_ignore_result)


def _ignore_result(future: asyncio.Future) -> None:
    """Retrieve an abandoned synthesis's exception so asyncio does not log
    "exception was never retrieved" for it."""
    if not future.cancelled():
        future.exception()
