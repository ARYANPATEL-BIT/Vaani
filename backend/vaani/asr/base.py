"""The provider-neutral interface every speech recogniser implements.

Callers (vaani/asr/runner.py) depend on `Recognizer`, `Transcript` and
`AsrError` here — never on faster-whisper. Adding the intended fallback, a
hosted recogniser such as Sarvam's saaras, means writing one new class.

The shape is chosen to fit BOTH kinds of recogniser:
  * local (faster-whisper): CPU/GPU work on a worker thread, which cannot be
    interrupted mid-decode;
  * hosted (an HTTPS upload): network I/O, which can be aborted at once.
So the unit of work is one whole utterance in, one text out. Streaming
recognition is not part of the interface: Whisper cannot do it (partials are
made by calling transcribe() again on the longer buffer).
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Transcript:
    """What a recogniser heard in one piece of audio.

    `text` may be empty: silence, or speech too unclear to decode.
    `language` is what the recogniser reports, or None if it does not say.
    """

    text: str
    language: str | None


class AsrError(Exception):
    """A transcription failed. The message never contains a secret."""


class Recognizer(ABC):
    """Turns one utterance of audio into text."""

    @abstractmethod
    async def transcribe(self, pcm: bytes, cancel: asyncio.Event) -> Transcript | None:
        """Transcribe `pcm`: 16 kHz mono 16-bit little-endian samples.

        `cancel` is the cancellation token. Once it is set, the implementation
        stops the underlying work as soon as it safely can and returns None
        (a cancelled transcription is not an error). It returns only when that
        work has really stopped: for an HTTP call that is at once; for local
        inference it is the next point the engine can stop at. The caller
        relies on this to know when a worker thread is free again.

        If the awaiting task itself is cancelled (session teardown), the
        implementation stops waiting at once and lets the work wind down on
        its own.

        Raises AsrError on failure.
        """
