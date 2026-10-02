"""A stand-in Recognizer for tests that must not load a real model.

It copies WhisperRecognizer's threading contract exactly: the blocking work
runs on its own thread pool, it cannot be interrupted once started, and after
the cancel token is set transcribe() returns None only when the thread is
free again. The "work" is time.sleep, which (like CTranslate2) releases the
GIL, so the event loop keeps running while it sleeps.

A gate (threading.Event) can hold the work open until a test releases it,
which makes "abandon while inference is running" deterministic.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from vaani.asr.base import Recognizer, Transcript


class FakeRecognizer(Recognizer):
    def __init__(
        self,
        decode_s: float = 0.05,
        text: str = "namaste duniya",
        workers: int = 2,
        gated: bool = False,
    ) -> None:
        self.decode_s = decode_s
        self.text = text
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.gate = threading.Event()
        if not gated:
            self.gate.set()
        self.started = threading.Event()  # set when any decode begins
        self.windows: list[tuple[float, float]] = []  # (start, end) per decode
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0  # most decodes ever running at once

    def _work(self, pcm: bytes) -> Transcript:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        start = perf_counter()
        self.started.set()
        try:
            self.gate.wait(timeout=10)  # held open by gated tests
            time.sleep(self.decode_s)  # releases the GIL, like CTranslate2
            return Transcript(self.text, "hi")
        finally:
            self.windows.append((start, perf_counter()))
            with self._lock:
                self.active -= 1

    async def transcribe(self, pcm: bytes, cancel: asyncio.Event) -> Transcript | None:
        loop = asyncio.get_running_loop()
        work = loop.run_in_executor(self.pool, self._work, pcm)
        cancelled = asyncio.ensure_future(cancel.wait())
        try:
            await asyncio.wait({work, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            if cancel.is_set():
                await asyncio.wait({work})  # returned == thread free
                return None
            return work.result()
        finally:
            cancelled.cancel()
