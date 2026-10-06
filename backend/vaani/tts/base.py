"""The provider-neutral interface every speech synthesiser implements.

Callers (vaani/speaker.py) depend on `Synthesizer` and `TtsError` here -
never on piper. Adding the intended alternative, a hosted synthesiser such as
Sarvam Bulbul, means writing one new class.

The shape fits BOTH kinds of synthesiser:
  * local (Piper): CPU work on a worker thread, which cannot be interrupted
    once the model is running;
  * hosted (an HTTPS request): network I/O, which can be aborted at once.
So the unit of work is one chunk of text in, that chunk's whole audio out.
Neither Piper nor Bulbul's REST API returns audio before the whole chunk is
done, so streaming audio out of one call is not part of the interface.
"""

import asyncio
from abc import ABC, abstractmethod


class TtsError(Exception):
    """A synthesis failed. The message never contains a secret."""


class Synthesizer(ABC):
    """Turns one chunk of reply text into speech."""

    # Samples per second of the audio `synthesize` returns. A property of the
    # voice, fixed for the synthesiser's lifetime; sent to the browser in
    # audio.start so it can play the audio at the right speed.
    sample_rate: int

    @abstractmethod
    async def synthesize(self, text: str, cancel: asyncio.Event) -> bytes | None:
        """Speak `text`: return mono 16-bit little-endian PCM at `sample_rate`.

        `cancel` is the cancellation token. Once it is set, the implementation
        stops as soon as it safely can and returns None (a cancelled synthesis
        is not an error). For an HTTP call that is at once; for local
        inference it returns only when the worker thread is free again.

        Raises TtsError on failure.
        """
