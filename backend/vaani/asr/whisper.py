"""faster-whisper behind the Recognizer interface.

Three things are stacked here:
  * Whisper — OpenAI's speech recognition model (the trained weights);
  * CTranslate2 — a C++ inference engine that runs those weights fast;
  * int8 / float16 — the number format the weights are run in (compute_type).
faster-whisper is the Python package that joins them.

Inference is far too slow to run on the event loop (hundreds of ms against
VAD's ~1 ms), so every decode runs on a worker thread from a pool this class
owns. That gives real parallelism, not just deferred work, because
CTranslate2 releases Python's GIL while it computes: the event loop thread
keeps running Python (ingesting frames) while the worker runs C++.

A decode cannot be interrupted once CTranslate2 is inside it. faster-whisper
yields one segment per 30 s window of audio, so the earliest we can stop is
between segments; an utterance under 30 s is a single segment.
"""

import asyncio
import importlib.util
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np

from vaani.asr.base import AsrError, Recognizer, Transcript
from vaani.config import AsrSettings

log = logging.getLogger("vaani.asr")

# Always transcribe. "translate" makes Whisper output an English translation,
# losing the words actually spoken. Not a config value: never a valid choice.
TASK = "transcribe"
# Whisper hallucinates words into silence (5 s of silence took 13 s to decode
# in the spike) unless its built-in VAD trims non-speech first. Not a config
# value for the same reason.
VAD_FILTER = True
# Whisper's input rate. A property of the model, not a tunable.
WHISPER_SAMPLE_RATE = 16000


def _add_windows_cuda_dll_dirs() -> None:
    """Make the pip-installed NVIDIA DLLs findable, on Windows only.

    The `gpu` extra installs cuBLAS/cuDNN/NVRTC as DLLs under
    site-packages/nvidia/<lib>/bin, which is not on Windows' DLL search path.
    os.add_dll_directory covers DLLs CTranslate2 loads itself; cuDNN then
    loads its own sub-libraries through PATH, so PATH is extended too. Must
    run BEFORE ctranslate2 is imported. On Linux this does nothing.
    """
    if sys.platform != "win32":
        return
    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        raise AsrError(
            "asr.whisper.device is 'cuda' but the NVIDIA libraries are not "
            "installed; run `uv sync --extra gpu`"
        )
    for root in spec.submodule_search_locations:
        for bin_dir in sorted(Path(root).glob("*/bin")):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def pcm_to_float(pcm: bytes) -> np.ndarray:
    """16-bit little-endian PCM bytes -> float32 samples in [-1, 1).

    Whisper takes floats; dividing by 32768 (2**15) maps the int16 range.
    """
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


class WhisperRecognizer(Recognizer):
    """One loaded Whisper model, shared by every session in the process."""

    def __init__(self, cfg: AsrSettings, sample_rate: int) -> None:
        if sample_rate != WHISPER_SAMPLE_RATE:
            raise AsrError(f"Whisper needs {WHISPER_SAMPLE_RATE} Hz audio")
        w = cfg.whisper
        if w.device == "cuda":
            _add_windows_cuda_dll_dirs()
        # Imported here, not at the top: on Windows the DLL path above must be
        # set before CTranslate2 loads, and a CPU-only process that never
        # builds this class never pays for the import.
        import ctranslate2
        from faster_whisper import WhisperModel

        if w.device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            # Never fall back to CPU: that would turn a GPU benchmark into a
            # CPU benchmark without anyone noticing.
            raise AsrError(
                "asr.whisper.device is 'cuda' but CTranslate2 finds no CUDA "
                "device; refusing to fall back to CPU"
            )
        self._cfg = w
        started = perf_counter()
        # num_workers lets CTranslate2 run that many decodes at once, one per
        # pool thread; with 1 they would queue inside the engine instead.
        self._model = WhisperModel(
            w.model,
            device=w.device,
            compute_type=w.compute_type,
            cpu_threads=w.cpu_threads,
            num_workers=cfg.max_concurrent,
        )
        # Our own pool, sized from config, instead of asyncio's shared default
        # pool: its size is ours to set, and nothing else queues on it.
        self._pool = ThreadPoolExecutor(
            max_workers=cfg.max_concurrent, thread_name_prefix="asr"
        )
        self._warm_up()
        log.info(
            "whisper %s on %s/%s loaded and warmed up in %.1f s (%d threads)",
            w.model,
            w.device,
            w.compute_type,
            perf_counter() - started,
            cfg.max_concurrent,
        )

    def _warm_up(self) -> None:
        """Run one tiny decode at startup.

        The first decode on a fresh model is slow (about 1 s extra on the GPU
        in the spike), and on cuda it is when cuDNN is first loaded, so a
        broken GPU install fails here at startup instead of on a user's turn.
        vad_filter is off so the decoder really runs; max_new_tokens keeps it
        short whatever it hallucinates into this near-silence.
        """
        noise = np.random.default_rng(0).normal(0, 0.01, WHISPER_SAMPLE_RATE)
        segments, _ = self._model.transcribe(
            noise.astype(np.float32),
            language=self._cfg.language,
            task=TASK,
            vad_filter=False,
            max_new_tokens=4,
        )
        for _ in segments:  # segments is lazy: iterating runs the decode
            pass

    def _decode(self, audio: np.ndarray, stop: threading.Event) -> Transcript | None:
        """Runs on a pool thread. Returns None if `stop` was set."""
        w = self._cfg
        segments, info = self._model.transcribe(
            audio,
            language=w.language,
            task=TASK,
            initial_prompt=w.initial_prompt,
            beam_size=w.beam_size,
            temperature=w.temperature,
            vad_filter=VAD_FILTER,
        )
        parts: list[str] = []
        # `segments` is a generator: each step decodes the next 30 s window.
        # Between steps is the only place a decode can be stopped.
        for segment in segments:
            if stop.is_set():
                return None
            parts.append(segment.text.strip())
        if stop.is_set():
            return None
        return Transcript(" ".join(p for p in parts if p), info.language)

    async def transcribe(self, pcm: bytes, cancel: asyncio.Event) -> Transcript | None:
        audio = pcm_to_float(pcm)
        # `stop` is a threading.Event, not the asyncio.Event: the worker thread
        # reads it, and asyncio objects are only safe on the loop's own thread.
        stop = threading.Event()
        loop = asyncio.get_running_loop()
        work = loop.run_in_executor(self._pool, self._decode, audio, stop)
        cancelled = asyncio.ensure_future(cancel.wait())
        try:
            await asyncio.wait({work, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            if cancel.is_set():
                # Ask the thread to stop at its next segment boundary, then
                # wait for it: returning means "the thread is free again".
                stop.set()
                await asyncio.wait({work})
                return None
            return work.result()
        except AsrError:
            raise
        except asyncio.CancelledError:
            raise  # teardown: `finally` tells the thread to stop
        except Exception as exc:
            raise AsrError(f"whisper decode failed: {exc}") from exc
        finally:
            cancelled.cancel()
            if not work.done():
                # Our task was cancelled mid-decode. The thread runs on until
                # the next segment boundary; nobody will read its result.
                stop.set()
                work.add_done_callback(_ignore_result)


def _ignore_result(future: asyncio.Future) -> None:
    """Retrieve an abandoned decode's exception so asyncio does not log
    "exception was never retrieved" for it."""
    if not future.cancelled():
        future.exception()
