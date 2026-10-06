"""One reply's audio: text chunks in; audio.start, frames, audio.end out.

reply.py decides WHAT to say and hands each chunk to `say` the moment the
chunker cuts it. This file SAYS it: synthesis (vaani/tts/), the audio
messages, the `speaking` state and the tts_first_audio span.

The audio uses the route the day-3 echo built: audio.start (now carrying
the voice's sample rate), binary frames, audio.end, and audio.flush on a
cancel (sent by turns.py). There is no second audio channel.

`speaking` starts when the first FRAME is sent, not when the first text
arrives: the state means "the user can hear the agent". And it lasts until
the browser has (by our estimate) PLAYED the last frame, not just received
it. Frames go out as fast as they are synthesised, seconds ahead of the
speaker; ending `speaking` at the last send would put the server back in
idle while the browser still has seconds of reply queued.

Cancellation: the reply's token is checked immediately before every send,
with no await in between, so after a cancel not one more frame goes out.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from time import perf_counter

from vaani.protocol import TurnState, audio_end, audio_start
from vaani.telemetry import TTS_FIRST_AUDIO, Telemetry
from vaani.tts import Synthesizer

log = logging.getLogger("vaani.speaker")

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]
MoveTo = Callable[[TurnState], Awaitable[None]]

BYTES_PER_SAMPLE = 2  # 16-bit PCM


class Speaker:
    """Speaks one reply. reply.py builds a new one for every reply."""

    def __init__(
        self,
        synth: Synthesizer,
        frame_ms: int,
        turn_id: str,
        cancel: asyncio.Event,
        ended_at: float,
        telemetry: Telemetry,
        send_json: SendJson,
        send_bytes: SendBytes,
        move_to: MoveTo,
    ) -> None:
        self._synth = synth
        self._rate = synth.sample_rate
        # Frames as long as the mic's (20 ms), at the VOICE's rate:
        # 22050 * 20 / 1000 = 441 samples = 882 bytes.
        self._frame_bytes = self._rate * frame_ms // 1000 * BYTES_PER_SAMPLE
        self._turn_id = turn_id
        self._cancel = cancel
        self._ended_at = ended_at  # turn_ended, for the first-audio log line
        self._telemetry = telemetry
        self._send_json = send_json
        self._send_bytes = send_bytes
        self._move_to = move_to
        self._started = False  # audio.start sent
        self._sent_audio = False  # at least one frame sent
        # When the browser will finish playing what we have sent, on our clock.
        # It mirrors the browser's own queue: a chunk starts when the previous
        # one ends, or now if the queue has run dry.
        self._playout_end = 0.0

    async def say(self, text: str) -> None:
        """Synthesise one chunk and send its frames. Raises TtsError."""
        if self._cancel.is_set():
            return  # do not start a synthesis nobody will hear
        pcm = await self._synth.synthesize(text, self._cancel)
        if not pcm or self._cancel.is_set():
            return  # cancelled, or nothing sayable (e.g. only punctuation)
        if not self._started:
            await self._start()
            if self._cancel.is_set():
                return  # a flush landed during those sends
        for i in range(0, len(pcm), self._frame_bytes):
            # The gate: no await between this check and the send.
            if self._cancel.is_set():
                return
            await self._send_bytes(pcm[i : i + self._frame_bytes])
            if not self._sent_audio:
                self._sent_audio = True
                self._first_audio()
        seconds = len(pcm) / BYTES_PER_SAMPLE / self._rate
        self._playout_end = max(perf_counter(), self._playout_end) + seconds

    async def end_audio(self) -> None:
        """audio.end, if this reply sent any audio. A cancelled reply owes
        none: its audio.flush ends it."""
        if self._started and not self._cancel.is_set():
            await self._send_json(audio_end(self._turn_id))

    async def finish(self) -> None:
        """Reply complete: audio.end, then stay `speaking` until it has played.

        Waiting ON THE TOKEN, with the play-out time as the timeout, means a
        cancel during the wait ends it at once instead of after the sleep.
        """
        await self.end_audio()
        remaining = self._playout_end - perf_counter()
        if self._started and remaining > 0:
            with suppress(TimeoutError):
                await asyncio.wait_for(self._cancel.wait(), timeout=remaining)

    async def _start(self) -> None:
        """First audio of the reply: now the agent is speaking."""
        self._started = True
        await self._move_to(TurnState.SPEAKING)
        if not self._cancel.is_set():
            await self._send_json(audio_start(self._turn_id, self._rate))

    def _first_audio(self) -> None:
        # Stamped AFTER the first frame's send returns, like echo_sent.
        span = self._telemetry.record(TTS_FIRST_AUDIO, self._turn_id)
        log.info(
            "session %s: turn %s first audio frame sent, turn_ended->first "
            "audio %.0f ms",
            self._telemetry.session_id,
            self._turn_id,
            (span.at - self._ended_at) * 1000,
        )
