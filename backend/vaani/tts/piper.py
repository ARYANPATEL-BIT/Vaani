"""Piper behind the Synthesizer interface: one synthesiser per persona.

Piper turns text into speech in two steps: espeak-ng converts the letters to
phonemes (the sounds), then a neural network (VITS, run with ONNX Runtime)
turns those phonemes into audio samples. Both run on the CPU.

Synthesis is too slow for the event loop (tens to hundreds of ms against
VAD's ~1 ms), so it runs on a worker thread, as Whisper does. ONNX Runtime
releases Python's GIL while it computes, so the event loop keeps ingesting
frames meanwhile.

Piper is NOT a streaming synthesiser: one call to the network produces one
sentence's audio, all at once, and cannot be stopped part-way. It yields one
piece per sentence of the text it is given, so the earliest a synthesis can
stop is between sentences. The chunker hands it about one clause or sentence
at a time, so in practice a cancelled chunk runs to its end on the thread
and its audio is thrown away.

Day 15: each persona has its own voice ([tts.piper.voices]). `build_piper`
loads each voice FILE once, however many personas use it, and gives every
persona's synthesiser the SAME thread pool, so [tts].max_concurrent still
caps syntheses for the whole process, not per voice.
"""

import asyncio
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from piper import PiperVoice, SynthesisConfig

from vaani.config import PersonaVoice, TtsSettings
from vaani.tts.base import Synthesizer, TtsError

log = logging.getLogger("vaani.tts")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def build_piper(cfg: TtsSettings) -> dict[str, "PiperSynthesizer"]:
    """Persona key -> its synthesiser. Raises TtsError if a voice is bad."""
    # ONE pool for every voice: three pools of max_concurrent would allow
    # three times as many syntheses at once as config says.
    pool = ThreadPoolExecutor(max_workers=cfg.max_concurrent, thread_name_prefix="tts")
    models_dir = Path(cfg.piper.models_dir)
    if not models_dir.is_absolute():  # relative to backend/, whatever the cwd
        models_dir = _BACKEND_ROOT / models_dir
    # Keyed by name AND hash: two personas naming the same voice share one
    # load, and a typo in one of their hashes still fails the check.
    loaded: dict[tuple[str, str], PiperVoice] = {}
    synths = {}
    for persona, pv in cfg.piper.voices.items():
        key = (pv.voice, pv.sha256)
        if key not in loaded:
            loaded[key] = _load(models_dir, pv)
        synths[persona] = PiperSynthesizer(loaded[key], pv.length_scale, pool)
    return synths


def _load(models_dir: Path, pv: PersonaVoice) -> PiperVoice:
    """Check, load and warm up one voice file."""
    model = models_dir / f"{pv.voice}.onnx"
    if not model.exists():
        raise TtsError(
            f"Piper voice {model} is missing; run "
            "`uv run python scripts/fetch_models.py`"
        )
    # Checked before the file reaches ONNX Runtime, like the VAD model: a
    # wrong or truncated voice fails at startup, not on a user's turn.
    actual = hashlib.sha256(model.read_bytes()).hexdigest()
    if actual != pv.sha256:
        raise TtsError(
            f"Piper voice {model} has sha256 {actual}, config expects {pv.sha256}"
        )
    started = perf_counter()
    voice = PiperVoice.load(model, config_path=models_dir / f"{pv.voice}.onnx.json")
    # The first synthesis loads espeak-ng and warms ONNX Runtime; do it now
    # so a user's first reply does not pay for it.
    for _ in voice.synthesize("namaste"):
        pass
    log.info(
        "piper %s (%d Hz) loaded and warmed up in %.2f s",
        pv.voice,
        voice.config.sample_rate,
        perf_counter() - started,
    )
    return voice


class PiperSynthesizer(Synthesizer):
    """One persona's voice and pace. The voice may be shared with others."""

    def __init__(
        self, voice: PiperVoice, length_scale: float | None, pool: ThreadPoolExecutor
    ) -> None:
        self._voice = voice
        # length_scale None = the voice's own value from its .onnx.json.
        self._syn_config = SynthesisConfig(length_scale=length_scale)
        self._pool = pool
        # 22050 Hz for the medium voices; read from the voice, never assumed.
        self.sample_rate = voice.config.sample_rate

    def _run(self, text: str, stop: threading.Event) -> bytes | None:
        """Runs on a pool thread. Returns None if `stop` was set."""
        parts: list[bytes] = []
        # One AudioChunk per sentence of `text`. Each step runs the network
        # once; between steps is the only place synthesis can be stopped.
        for chunk in self._voice.synthesize(text, self._syn_config):
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
