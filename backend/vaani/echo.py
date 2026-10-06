"""Day-3 echo (development only): send each turn's frames straight back.

Echo proved the return audio path (audio.start, binary frames, audio.end,
and the day-4 flush) before anything real produced audio. It is off by
default; `[gateway].echo_enabled = true` turns it back on.

turns.py owns WHEN a turn opens and ends; this class only sends the echo
traffic for it, and does nothing at all when echo is off.
"""

from collections.abc import Awaitable, Callable

from vaani.protocol import audio_end, audio_start
from vaani.session import Session
from vaani.telemetry import ECHO_SENT, FRAME_RECEIVED, Telemetry

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


class Echo:
    """One session's echo. Built by TurnPipeline."""

    def __init__(
        self,
        enabled: bool,
        sample_rate: int,
        session: Session,
        telemetry: Telemetry,
        send_json: SendJson,
        send_bytes: SendBytes,
    ) -> None:
        self._enabled = enabled
        self._sample_rate = sample_rate  # echoed audio is the mic's own format
        self._session = session
        self._telemetry = telemetry
        self._send_json = send_json
        self._send_bytes = send_bytes

    async def start(self, turn_id: str) -> None:
        """A turn opened: audio.start must precede its first echoed frame."""
        if self._enabled:
            await self._send_json(audio_start(turn_id, self._sample_rate))

    async def frame(self, data: bytes) -> None:
        """Send the frame back if echo is on and a turn is open."""
        turn_id = self._session.current_turn_id
        if not self._enabled or not self._session.turn_open or turn_id is None:
            return
        self._telemetry.record(FRAME_RECEIVED, turn_id)
        # Late-frame gate. There is NO await between this check and
        # send_bytes, so nothing can flush the turn in between: if the turn
        # is flushed, this frame is dropped, never sent.
        if self._session.is_flushed(turn_id):
            self._session.late_frames_dropped += 1
            return
        await self._send_bytes(data)
        # Stamped AFTER the send returns, so the gap includes the send itself.
        self._telemetry.record(ECHO_SENT, turn_id)

    async def end(self) -> None:
        """audio.end for the open turn, if echo sent it audio. A flushed turn
        owes no audio.end: the flush already ended it."""
        turn_id = self._session.current_turn_id
        if (
            self._enabled
            and self._session.turn_open
            and turn_id is not None
            and not self._session.is_flushed(turn_id)
        ):
            await self._send_json(audio_end(turn_id))
