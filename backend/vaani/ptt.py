"""Push-to-talk (protocol v0.9): the user's presses mark where a turn starts
and ends, instead of the user's silences.

In a ptt session turns.py builds a PttBuffer INSTEAD OF the Endpointer
(endpoint.py). ptt.start opens a press, every frame until ptt.end is kept,
and ptt.end closes it at once: no 700 ms silence wait and no pre-roll. The
client sends frames only while a press is open (docs/contracts.md 2.8), so
there is nothing before the press to keep.

VAD still runs on every frame, for one job: counting VOICED frames (speech
probability at or above [vad].threshold), so an empty press, speak then stop
with no speech, is rejected by the same min_utterance_ms rule hands-free mode
uses, instead of sending silence to Whisper.

Like endpoint.py, it is synchronous, does no I/O and counts time in frames,
so there is nothing here to cancel. turns.py decides what a closed press
becomes (a turn, or a discarded one).
"""

import logging
from time import perf_counter

from vaani.config import EndpointSettings
from vaani.endpoint import TurnEnded, ms_to_frames

log = logging.getLogger("vaani.ptt")


class PttBuffer:
    """One ptt session's open press: its frames and how many were voiced."""

    def __init__(
        self,
        cfg: EndpointSettings,
        frame_ms: int,
        vad_threshold: float,
        session_id: str,
    ) -> None:
        self._frame_ms = frame_ms
        self._vad_threshold = vad_threshold
        self._min_frames = ms_to_frames(cfg.min_utterance_ms, frame_ms)
        self._max_frames = ms_to_frames(cfg.max_utterance_ms, frame_ms)
        self._session_id = session_id
        # Counts every frame pushed, from 0, as VadStream and Endpointer do.
        self._frame_index = -1
        self._frames: list[bytes] | None = None  # None: no press open
        self._start_frame = 0  # index of the press's first frame
        self._voiced = 0  # voiced frames in the open press
        self._dropped = 0  # frames that arrived with no press open

    @property
    def holding(self) -> bool:
        """True from ptt.start until the press is released."""
        return self._frames is not None

    def press(self) -> None:
        """ptt.start: open a press. Its audio starts with the next frame."""
        self._frames = []
        self._start_frame = self._frame_index + 1
        self._voiced = 0

    def push(self, frame: bytes, probability: float) -> bool:
        """Feed one frame and its speech probability.

        True when the press has reached max_utterance_ms: the caller then
        releases it, exactly as if ptt.end had arrived.
        """
        self._frame_index += 1
        if self._frames is None:
            # The client should not send these (contracts.md 2.8). Dropped.
            self._dropped += 1
            return False
        self._frames.append(frame)
        if probability >= self._vad_threshold:
            self._voiced += 1
        return len(self._frames) >= self._max_frames

    def release(self) -> TurnEnded | None:
        """Close the press. Its turn, or None if it held too little speech."""
        frames, self._frames = self._frames, None
        assert frames is not None  # turns.py releases only an open press
        forced = len(frames) >= self._max_frames
        if forced:
            log.warning(
                "session %s: press hit max_utterance_ms, ending the turn",
                self._session_id,
            )
        # The SAME rule as Endpointer._finish (endpoint.py): fewer voiced
        # frames than min_utterance_ms makes no turn. Change one, change both.
        # One difference: a press at the length cap is checked too, since a
        # 30 s press of silence is still empty.
        if not frames or self._voiced < self._min_frames:
            log.info(
                "session %s: press of %d ms, %d ms voiced, ignored (min_utterance_ms)",
                self._session_id,
                len(frames) * self._frame_ms,
                self._voiced * self._frame_ms,
            )
            return None
        at = perf_counter()
        return TurnEnded(
            start_frame=self._start_frame,
            end_frame=self._start_frame + len(frames) - 1,
            duration_ms=len(frames) * self._frame_ms,
            audio=b"".join(frames),
            frame_count=len(frames),
            forced=forced,
            at=at,
            # The press ended the turn: no silence was waited for, so the
            # "speech ended" moment is the release itself (logged as 0 ms).
            speech_ended_at=None if forced else at,
            voiced_frames=self._voiced,
        )

    def close(self) -> None:
        """Session ending: an open press has nobody to receive it."""
        if self._frames is not None:
            log.info(
                "session %s: discarding open press (%d frames) at close",
                self._session_id,
                len(self._frames),
            )
        if self._dropped:
            log.info(
                "session %s: %d frames arrived outside a press and were dropped",
                self._session_id,
                self._dropped,
            )
