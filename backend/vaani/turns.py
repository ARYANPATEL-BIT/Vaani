"""The per-frame audio path of one session: VAD -> endpointing -> turns -> ASR.

The gateway validates a frame and hands it to `TurnPipeline.on_frame`. From
there, in order:
  1. VAD (vad.py) says whether speech started or ended on this frame;
  2. the Endpointer (endpoint.py) decides whether the user's turn is over;
  3. turns open and close here. A TURN IS ONE USER UTTERANCE: its turn_id is
     created when speech starts, so partial transcripts, the final
     transcript and any echo audio all carry the same id;
  4. ASR (asr/runner.py) is asked for partials while the user speaks and for
     the final when the turn ends — asked only: recognition never runs here;
  5. echo (day 3, development only) sends the turn's frames back.

Everything in on_frame is quick: VAD is ~1 ms, the rest microseconds. The
expensive step, recognition, is handed to the runner's background task, so
the frame loop never waits for it.
"""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from vaani.asr import Recognizer
from vaani.asr.runner import AsrRunner
from vaani.config import Settings
from vaani.endpoint import Endpointer, TurnEnded, ms_to_frames
from vaani.protocol import audio_end, audio_start
from vaani.session import Session
from vaani.telemetry import ECHO_SENT, FRAME_RECEIVED, TURN_ENDED, Telemetry
from vaani.vad import VadStream

log = logging.getLogger("vaani.turns")

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


class TurnPipeline:
    """One session's frame-by-frame processing. Built on session.start."""

    def __init__(
        self,
        settings: Settings,
        session: Session,
        telemetry: Telemetry,
        send_json: SendJson,
        send_bytes: SendBytes,
        vad_model,
        recognizer: Recognizer | None,
    ) -> None:
        self._session = session
        self._telemetry = telemetry
        self._send_json = send_json
        self._send_bytes = send_bytes
        self._frame_ms = settings.audio.frame_ms
        self._echo = settings.gateway.echo_enabled
        # Each stage needs the one before it: no VAD, no endpointing; no
        # endpointing (no utterances), nothing to transcribe.
        self._vad = (
            VadStream(vad_model, settings.vad, settings.audio)
            if settings.vad.enabled
            else None
        )
        self._endpointer = (
            Endpointer(settings.endpoint, self._frame_ms, session.session_id)
            if self._vad is not None and settings.endpoint.enabled
            else None
        )
        self._asr = (
            AsrRunner(recognizer, settings.asr, send_json, telemetry)
            if self._endpointer is not None and recognizer is not None
            else None
        )
        # Partial re-decode interval in frames; 0 = partials off.
        interval = settings.asr.partial_interval_ms
        self._partial_frames = ms_to_frames(interval, self._frame_ms) if interval else 0
        # frames_since_start at which the last partial was requested.
        self._last_partial_at = 0

    async def on_frame(self, data: bytes) -> None:
        """Process one valid frame. Must be called for every frame, in order."""
        speech_event = None
        if self._vad is not None:
            # Plain synchronous CPU work on the event loop: while it runs,
            # every session on this loop waits, so its cost is timed per frame.
            vad_started = perf_counter()
            speech_event = self._vad.push(data)
            self._telemetry.record_vad_decision(vad_started)
            if speech_event is not None:
                log.info(
                    "session %s: %s at frame %d (%.2fs into audio)",
                    self._session.session_id,
                    speech_event.kind,
                    speech_event.frame_index,
                    (speech_event.frame_index + 1) * self._frame_ms / 1000,
                )
        if self._endpointer is not None:
            # Routing seam. No agent speech exists yet, so the user's audio
            # always goes to the endpointer. Week 3: while the agent is
            # speaking, route speech_event to barge-in here instead.
            was_open = self._endpointer.utterance_open
            turn = self._endpointer.push(data, speech_event)
            if turn is not None:
                await self._end_turn(turn)
            elif was_open and not self._endpointer.utterance_open:
                await self._discard_turn()  # shorter than min_utterance_ms
            # Opens on speech_started, and again straight after a forced end
            # (max_utterance_ms), where the next utterance follows at once.
            if self._endpointer.utterance_open and not self._session.turn_open:
                await self._open_turn()
            self._maybe_request_partial()
        await self._echo_frame(data)

    def on_flush(self, turn_id: str) -> None:
        """The turn was flushed (today dev.flush; week 3 barge-in): abandon
        its recognition so no transcript is ever sent for it."""
        if self._asr is not None:
            self._asr.abandon_turn(turn_id)

    async def on_session_end(self) -> None:
        """Clean session.end: close the open echo turn before the socket."""
        await self._send_echo_end()

    async def close(self) -> None:
        """Session over, cleanly or not: abandon recognition in flight."""
        if self._asr is not None:
            await self._asr.close()
        if self._endpointer is not None:
            self._endpointer.close()

    # --- Turn lifecycle ----------------------------------------------------

    async def _open_turn(self) -> None:
        turn_id = self._session.open_turn()
        self._last_partial_at = 0
        log.info("session %s: turn %s opened", self._session.session_id, turn_id)
        if self._echo:
            # audio.start must precede the turn's first echoed frame.
            await self._send_json(audio_start(turn_id))

    async def _end_turn(self, turn: TurnEnded) -> None:
        turn_id = self._session.current_turn_id
        assert turn_id is not None  # a turn ends only after one opened
        self._telemetry.record(TURN_ENDED, turn_id)
        waited = (
            "forced"
            if turn.speech_ended_at is None
            else f"waited {(turn.at - turn.speech_ended_at) * 1000:.0f} ms"
        )
        log.info(
            "session %s: turn_ended turn %s frames %d-%d, %d ms, "
            "%d frames buffered (%s)",
            self._session.session_id,
            turn_id,
            turn.start_frame,
            turn.end_frame,
            turn.duration_ms,
            turn.frame_count,
            waited,
        )
        await self._send_echo_end()
        self._session.close_turn()
        # A flushed (interrupted) turn gets no transcript: on_flush already
        # abandoned its recognition, and nothing may restart it.
        if self._asr is not None and not self._session.is_flushed(turn_id):
            self._asr.request_final(turn_id, turn.audio, turn.duration_ms, turn.at)

    async def _discard_turn(self) -> None:
        turn_id = self._session.current_turn_id
        assert turn_id is not None
        log.info(
            "session %s: turn %s discarded (too short)",
            self._session.session_id,
            turn_id,
        )
        await self._send_echo_end()
        self._session.close_turn()
        if self._asr is not None:
            self._asr.abandon_turn(turn_id)

    def _maybe_request_partial(self) -> None:
        """Ask for a partial every `partial_interval_ms` of an utterance.

        Only while the user is actively speaking (a re-decode in the silence
        window would hear nothing new) and only once the utterance is longer
        than min_utterance_ms. The utterance then cannot be discarded as too
        short later, so the browser never shows a partial whose turn vanishes.
        """
        ep = self._endpointer
        if self._asr is None or not self._partial_frames or ep is None:
            return
        frames = ep.frames_since_start
        turn_id = self._session.current_turn_id
        if not ep.speaking or frames < ep.min_frames or turn_id is None:
            return
        if self._session.is_flushed(turn_id):
            return
        if frames - self._last_partial_at >= self._partial_frames:
            self._last_partial_at = frames
            self._asr.request_partial(turn_id, ep.snapshot())

    # --- Echo (day 3, development only) -----------------------------------

    async def _echo_frame(self, data: bytes) -> None:
        """Send the frame back if echo is on and a turn is open."""
        turn_id = self._session.current_turn_id
        if not self._echo or not self._session.turn_open or turn_id is None:
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

    async def _send_echo_end(self) -> None:
        """audio.end for the open turn, if echo sent it audio. A flushed turn
        owes no audio.end: the flush already ended it."""
        turn_id = self._session.current_turn_id
        if (
            self._echo
            and self._session.turn_open
            and turn_id is not None
            and not self._session.is_flushed(turn_id)
        ):
            await self._send_json(audio_end(turn_id))
