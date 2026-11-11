"""One reply's audio: text chunks in; audio.start, frames, audio.end out.

reply.py decides WHAT to say and hands each chunk to `say` the moment the
chunker cuts it. This file SAYS it: synthesis (vaani/tts/), the audio
messages, the `speaking` state and the tts_first_audio span.

The audio uses the route the day-3 echo built: audio.start (now carrying
the voice's sample rate), binary frames, audio.end, and audio.flush on a
barge-in (sent by barge_in.py). There is no second audio channel.

`speaking` starts when the first FRAME is sent, not when the first text
arrives: the state means "the user can hear the agent". And it lasts until
the browser has (by our estimate) PLAYED the last frame, not just received
it. Frames go out as fast as they are synthesised, seconds ahead of the
speaker; ending `speaking` at the last send would put the server back in
idle while the browser still has seconds of reply queued.

Cancellation: the reply's token is checked immediately before every send,
with no await in between, so after a cancel not one more frame goes out.

Day 13: each chunk's play-out window is kept in `spoken`, so a barge-in can
work out how much of the reply the user had heard (barge_in.heard_text).

English replies (feat/english-voice): each persona has a voice per language
("hi", "en"). The FIRST chunk's script picks one (language.reply_language)
and it is locked for the whole reply: audio.start declares one sample rate
per reply, and switching voices mid-reply would sound like a second speaker.
A later chunk in the other script is still said by the locked voice, partly
misread, and logged as drift.

Reply language (protocol v0.10): in a session that forces "en" or "hi", that
language picks the voice instead, for the whole reply, whatever script the
first chunk is in. The model was told to write in that language, so a first
chunk in the other script ("OK," opening a Hindi reply) is the model
slipping, not the reply's language: it is logged and said by the forced
voice. The script is still kept (first_script), for the turn's database row.

Latin words inside a Hindi reply (feat/guardrails): the prompt asks for
every word in Devanagari, but a model still writes "WiFi" now and then. Each
such chunk is logged with its Latin words, before synthesis. It is a count,
not a fix: the words are still said, and still misread.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from time import perf_counter
from typing import NamedTuple

from vaani.language import latin_words, reply_language
from vaani.protocol import TurnState, audio_end, audio_start
from vaani.telemetry import TTS_FIRST_AUDIO, TTS_START, Telemetry
from vaani.tts import Synthesizer

log = logging.getLogger("vaani.speaker")

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]
MoveTo = Callable[[TurnState], Awaitable[None]]

BYTES_PER_SAMPLE = 2  # 16-bit PCM


class Spoken(NamedTuple):
    """One chunk sent, and when the browser should play it (server clock)."""

    text: str
    start: float
    end: float


class Speaker:
    """Speaks one reply. reply.py builds a new one for every reply."""

    def __init__(
        self,
        voices: dict[str, Synthesizer],
        forced_voice: str | None,  # "en" / "hi" when forced (v0.10); None: "any"
        frame_ms: int,
        turn_id: str,
        cancel: asyncio.Event,
        ended_at: float,
        telemetry: Telemetry,
        send_json: SendJson,
        send_bytes: SendBytes,
        move_to: MoveTo,
    ) -> None:
        self._voices = voices  # language ("hi", "en") -> that language's voice
        self._forced_voice = forced_voice
        self._frame_ms = frame_ms
        # Set by the first chunk (_lock_voice): until then no voice is chosen.
        # `language` is the voice's language; `first_script` the first
        # chunk's script. They differ only when a forced reply began in the
        # other script.
        self.language: str | None = None
        self.first_script: str | None = None
        self._synth: Synthesizer | None = None
        self._rate = 0
        self._frame_bytes = 0
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
        # Every chunk sent, with its play-out window: what a barge-in cut
        # had been heard (barge_in.heard_text).
        self.spoken: list[Spoken] = []

    async def say(self, text: str) -> None:
        """Synthesise one chunk and send its frames. Raises TtsError."""
        if self._cancel.is_set():
            return  # do not start a synthesis nobody will hear
        if self._synth is None:
            self._lock_voice(text)
        elif (language := reply_language(text)) != self.language:
            # The model switched script mid-reply. The locked voice says it
            # anyway (and partly misreads it): see the module docstring.
            log.warning(
                "session %s: turn %s script drift: %s chunk said by the %s voice",
                self._telemetry.session_id,
                self._turn_id,
                language,
                self.language,
            )
        # A Devanagari chunk of a Hindi reply that still holds English letters
        # ("WiFi"): the Hindi voice will misread those words. Only logged, to
        # count how often it happens. A chunk with no Devanagari at all was
        # already logged as drift just above, so it is not logged twice.
        if self.language == "hi" and reply_language(text) == "hi":
            if words := latin_words(text):
                log.warning(
                    "session %s: turn %s %d Latin word(s) in a hi chunk: %s",
                    self._telemetry.session_id,
                    self._turn_id,
                    len(words),
                    " ".join(words),  # ASCII only: latin_words finds A-Z, a-z
                )
        assert self._synth is not None  # locked just above, on the first chunk
        began = perf_counter()
        pcm = await self._synth.synthesize(text, self._cancel)
        if not self._started:
            # Debug: when the first chunk's synthesis ran, on the same
            # turn_ended clock as reply.py's first-cut line.
            log.debug(
                "session %s: turn %s first chunk synthesis %.0f -> %.0f ms "
                "after turn_ended (%d chars)",
                self._telemetry.session_id,
                self._turn_id,
                (began - self._ended_at) * 1000,
                (perf_counter() - self._ended_at) * 1000,
                len(text),
            )
        if not pcm or self._cancel.is_set():
            return  # cancelled, or nothing sayable (e.g. only punctuation)
        if not self._started:
            await self._start()
            if self._cancel.is_set():
                return  # a flush landed during those sends
        # Play-out window BEFORE the frames go: a cut part-way through the
        # sends must still know this chunk was playing.
        start = max(perf_counter(), self._playout_end)
        self._playout_end = start + len(pcm) / BYTES_PER_SAMPLE / self._rate
        self.spoken.append(Spoken(text, start, self._playout_end))
        for i in range(0, len(pcm), self._frame_bytes):
            # The gate: no await between this check and the send.
            if self._cancel.is_set():
                return
            await self._send_bytes(pcm[i : i + self._frame_bytes])
            if not self._sent_audio:
                self._sent_audio = True
                self._first_audio()

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

    def _lock_voice(self, first_chunk: str) -> None:
        """Pick this reply's voice, for good: the session's forced language
        if there is one (v0.10), else the first chunk's script."""
        self.first_script = reply_language(first_chunk)
        self.language = self._forced_voice or self.first_script
        if self.language != self.first_script:
            # Only possible when forced: the model began in the other script.
            log.warning(
                "session %s: turn %s forced %s reply began in %s script; "
                "said by the %s voice",
                self._telemetry.session_id,
                self._turn_id,
                self.language,
                self.first_script,
                self.language,
            )
        self._synth = self._voices[self.language]
        self._rate = self._synth.sample_rate
        # Frames as long as the mic's (20 ms), at the VOICE's rate:
        # 22050 * 20 / 1000 = 441 samples = 882 bytes.
        self._frame_bytes = self._rate * self._frame_ms // 1000 * BYTES_PER_SAMPLE
        log.info(
            "session %s: turn %s speaks with the %s voice (%d Hz)",
            self._telemetry.session_id,
            self._turn_id,
            self.language,
            self._rate,
        )
        # Once per reply, just before its first synthesis begins.
        self._telemetry.record(TTS_START, self._turn_id)

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
