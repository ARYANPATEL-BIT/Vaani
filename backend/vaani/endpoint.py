"""Endpointing: has the user FINISHED their turn?

VAD (vad.py) answers a smaller question: is there speech right now? It fires
speech_ended after 200 ms of silence, which happens at every comma and every
"umm". This module sits on top of those events and decides when a pause is
long enough to mean "I am done, your turn". It emits one TurnEnded per turn.

Two rules, both from [endpoint] in config.toml:
  * end_of_turn_silence_ms: after speech_ended, wait this long. If speech
    starts again inside the window, the pending end is cancelled and the same
    utterance continues.
  * min_utterance_ms: an utterance shorter than this (a cough, a lone "mm")
    produces no turn at all.

It also keeps the utterance's AUDIO (UtteranceBuffer), because speech
recognition will need it: a short pre-roll from before speech_started, then
every frame up to speech_ended. The buffer is capped by max_utterance_ms.

Time is counted in FRAMES, not with a wall clock. Frames arrive from the
microphone in real time (one every 20 ms), so 35 frames is 700 ms of audio.
That keeps this module free of timers and I/O, and makes tests exact.

This module never runs the VAD model and never looks inside a frame; frames
are opaque bytes it stores. It is synchronous and does no I/O, so there is
nothing here to cancel.
"""

import logging
import math
from collections import deque
from dataclasses import dataclass
from time import perf_counter

from vaani.config import EndpointSettings
from vaani.vad import SPEECH_ENDED, SPEECH_STARTED, SpeechEvent

log = logging.getLogger("vaani.endpoint")


@dataclass(frozen=True)
class TurnEnded:
    """One finished user turn.

    `start_frame` is the frame that confirmed speech_started; `end_frame` the
    frame that confirmed the last speech_ended (or, for a forced end, the
    frame that hit the length cap). Both are 0-based session frame indexes,
    the same numbering VAD uses. `duration_ms` spans start_frame..end_frame.
    `audio` is pre-roll + every frame from start_frame to end_frame, and
    `frame_count` is how many frames that is. `speech_ended_at` is the
    perf_counter time of the speech_ended that began the silence window
    (None for a forced end), so the caller can measure the wait.
    """

    start_frame: int
    end_frame: int
    duration_ms: int
    audio: bytes
    frame_count: int
    forced: bool
    at: float
    speech_ended_at: float | None


def ms_to_frames(ms: int, frame_ms: int) -> int:
    """Whole frames covering `ms`, rounded UP so a window is never shorter
    than configured (e.g. 700 ms / 20 ms = 35; 710 ms -> 36)."""
    return math.ceil(ms / frame_ms)


class UtteranceBuffer:
    """Audio frames for one utterance, plus a rolling pre-roll.

    While nobody is speaking, every frame goes into `_preroll`, a deque with a
    maxlen: appending to a full one silently drops the oldest frame, so it
    always holds just the last N frames. When speech_started arrives, those N
    frames become the front of the utterance. That matters because VAD
    confirms speech only on its 4th speech frame (80 ms late): without the
    pre-roll the first syllable would be cut off.
    """

    def __init__(self, preroll_frames: int) -> None:
        self._preroll: deque[bytes] = deque(maxlen=preroll_frames)
        self._frames: list[bytes] = []
        self._preroll_count = 0  # how many of _frames came from the pre-roll

    @property
    def speech_frames(self) -> int:
        """Frames since speech_started (pre-roll not counted)."""
        return len(self._frames) - self._preroll_count

    def add_idle(self, frame: bytes) -> None:
        """No utterance open: keep the frame only as possible pre-roll."""
        self._preroll.append(frame)

    def open(self, first_frame: bytes, with_preroll: bool) -> None:
        """Start an utterance. `first_frame` is the speech_started frame."""
        self._frames = list(self._preroll) if with_preroll else []
        self._preroll_count = len(self._frames)
        self._preroll.clear()
        self._frames.append(first_frame)

    def add(self, frame: bytes) -> None:
        self._frames.append(frame)

    def take(self, speech_frames: int) -> list[bytes]:
        """Close the utterance, keeping pre-roll + the first `speech_frames`.

        Frames after that (the silence we waited through) are dropped from
        the utterance but refill the pre-roll: they are the most recent audio,
        and the next utterance may start a moment from now.
        """
        keep = self._preroll_count + speech_frames
        kept, rest = self._frames[:keep], self._frames[keep:]
        self._preroll.extend(rest)  # maxlen keeps only the newest N
        self._frames = []
        self._preroll_count = 0
        return kept


class Endpointer:
    """One session's endpointing: VAD events in, TurnEnded out.

    Three states, held in two fields:
      * idle:     _start_frame is None. Frames feed the pre-roll.
      * speaking: _start_frame set, _ended_frame None.
      * pending:  both set. Silence since _ended_frame; if it lasts
                  _silence_frames, the turn ends. speech_started cancels it.
    """

    def __init__(
        self, cfg: EndpointSettings, frame_ms: int, session_id: str = "-"
    ) -> None:
        self._frame_ms = frame_ms
        self._silence_frames = ms_to_frames(cfg.end_of_turn_silence_ms, frame_ms)
        self._min_frames = ms_to_frames(cfg.min_utterance_ms, frame_ms)
        self._max_frames = ms_to_frames(cfg.max_utterance_ms, frame_ms)
        self._session_id = session_id
        self._buffer = UtteranceBuffer(ms_to_frames(cfg.preroll_ms, frame_ms))
        # Counts every frame pushed, starting at 0, exactly as VadStream does,
        # so our indexes and SpeechEvent.frame_index agree.
        self._frame_index = -1
        self._start_frame: int | None = None
        self._ended_frame: int | None = None
        self._ended_at: float | None = None

    def push(self, frame: bytes, event: SpeechEvent | None) -> TurnEnded | None:
        """Feed one frame and the VAD event it produced (usually None).

        Must be called for EVERY valid frame, in order, even silent ones:
        the frame count is our clock.
        """
        self._frame_index += 1
        i = self._frame_index

        if self._start_frame is None:  # idle
            if event is not None and event.kind == SPEECH_STARTED:
                self._start_frame = i
                self._buffer.open(frame, with_preroll=True)
            else:
                self._buffer.add_idle(frame)
            return None

        self._buffer.add(frame)
        if event is not None and event.kind == SPEECH_ENDED:
            # Start the silence window. Not the end yet: the user may go on.
            self._ended_frame, self._ended_at = i, event.at
        elif event is not None and event.kind == SPEECH_STARTED:
            # Speech resumed inside the window: cancel the pending end. The
            # pause frames are already in the buffer, so audio stays continuous.
            self._ended_frame = self._ended_at = None

        if self._ended_frame is not None:
            if i - self._ended_frame >= self._silence_frames:
                return self._finish(self._ended_frame, forced=False)
        elif self._buffer.speech_frames >= self._max_frames:
            # The cap is checked only while speaking. The silence window can
            # add at most _silence_frames more, so the buffer never holds more
            # than pre-roll + max + silence window frames.
            return self._force_while_speaking(i)
        return None

    def close(self) -> None:
        """Session ending: an open utterance has nobody to receive it."""
        if self._start_frame is not None:
            log.info(
                "session %s: discarding unfinished utterance (%d frames) at close",
                self._session_id,
                self._buffer.speech_frames,
            )

    def _finish(self, end_frame: int, forced: bool) -> TurnEnded | None:
        """Close the utterance at `end_frame`; None if it was too short."""
        start = self._start_frame
        assert start is not None  # only called with an utterance open
        speech_frames = end_frame - start + 1
        ended_at = self._ended_at
        frames = self._buffer.take(speech_frames)
        self._start_frame = self._ended_frame = self._ended_at = None

        if speech_frames < self._min_frames and not forced:
            log.info(
                "session %s: utterance of %d ms ignored (min_utterance_ms)",
                self._session_id,
                speech_frames * self._frame_ms,
            )
            return None
        return TurnEnded(
            start_frame=start,
            end_frame=end_frame,
            duration_ms=speech_frames * self._frame_ms,
            audio=b"".join(frames),
            frame_count=len(frames),
            forced=forced,
            at=perf_counter(),
            speech_ended_at=None if forced else ended_at,
        )

    def _force_while_speaking(self, i: int) -> TurnEnded | None:
        """Length cap hit mid-speech: end the turn at this frame.

        The user is still talking and VAD will not fire speech_started again
        (it is still in speech), so the next frame opens a new utterance
        straight away, with no pre-roll: it follows on directly, nothing lost.
        """
        log.warning(
            "session %s: utterance hit max_utterance_ms, forcing turn end",
            self._session_id,
        )
        turn = self._finish(i, forced=True)
        # take() left the buffer empty, so the next frame goes in via add().
        self._start_frame = i + 1
        return turn
