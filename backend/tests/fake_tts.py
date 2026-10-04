"""A stand-in Synthesizer for gateway tests that must not load a real voice.

It copies PiperSynthesizer's threading contract: the work runs on its own
thread pool, cannot be interrupted once started, and after the cancel token
is set synthesize() returns None only when the thread is free again. The
"work" is time.sleep, which (like ONNX Runtime) releases the GIL, so the
event loop keeps running meanwhile.

`gate_from=N` holds every call from the N-th (0-based) open until the test
sets `gate`, which makes "cancel while synthesis is running" deterministic.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from vaani.tts import Synthesizer, TtsError

SAMPLE_RATE = 22050  # the Piper voice's rate, so tests see a non-16 kHz rate


class FakeSynthesizer(Synthesizer):
    def __init__(
        self,
        synth_s: float = 0.01,
        audio_ms_per_char: float = 2.0,
        gate_from: int | None = None,
        fail_on: int | None = None,
    ) -> None:
        self.sample_rate = SAMPLE_RATE
        self.synth_s = synth_s
        self.audio_ms_per_char = audio_ms_per_char
        self.gate_from = gate_from
        self.fail_on = fail_on  # 0-based call index that raises TtsError
        self.gate = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.texts: list[str] = []  # every chunk asked for, in order
        self.windows: list[tuple[float, float]] = []  # (start, end) per call
        self.gated = threading.Event()  # set when a gated call is waiting

    def _work(self, index: int, text: str) -> bytes:
        start = perf_counter()
        try:
            if self.gate_from is not None and index >= self.gate_from:
                self.gated.set()
                self.gate.wait(timeout=10)
            time.sleep(self.synth_s)  # releases the GIL, like ONNX Runtime
            if index == self.fail_on:
                raise RuntimeError("voice exploded")
            samples = round(len(text) * self.audio_ms_per_char * SAMPLE_RATE / 1000)
            return b"\x01\x00" * samples
        finally:
            self.windows.append((start, perf_counter()))

    async def synthesize(self, text: str, cancel: asyncio.Event) -> bytes | None:
        index = len(self.texts)
        self.texts.append(text)
        loop = asyncio.get_running_loop()
        work = loop.run_in_executor(self.pool, self._work, index, text)
        cancelled = asyncio.ensure_future(cancel.wait())
        try:
            await asyncio.wait({work, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            if cancel.is_set():
                await asyncio.wait({work})  # returned == thread free
                return None
            return work.result()
        except RuntimeError as exc:
            raise TtsError(str(exc)) from exc
        finally:
            cancelled.cancel()
