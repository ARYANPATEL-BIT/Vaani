"""One session's turns: VAD -> endpointing -> turns -> ASR -> reply.

The gateway validates a frame and hands it to `TurnPipeline.on_frame`. From
there, in order:
  1. VAD (vad.py) says whether speech started or ended on this frame;
  2. the Endpointer (endpoint.py) decides whether the user's turn is over;
  3. turns open and close here. A TURN IS ONE USER UTTERANCE: its turn_id is
     created when speech starts, so partial transcripts, the final
     transcript, any echo audio and the agent's reply all carry the same id;
  4. ASR (asr/runner.py) is asked for partials while the user speaks and for
     the final when the turn ends — asked only: recognition never runs here;
  5. the final transcript goes to reply.py, which streams the model's answer
     and has it spoken (chunker.py, speaker.py, tts/);
  6. echo (echo.py; day 3, development only) sends the turn's frames back.

Everything in on_frame is quick: VAD is ~1 ms, the rest microseconds. The
slow steps, recognition and the model, run as background tasks, so the frame
loop never waits for them.

The TURN STATE MACHINE (day 11, turn_state.py) is what the agent is doing,
as one value. Every change goes through its `move_to`.

BARGE-IN (day 13): while the agent is thinking or speaking, frames go to
barge_in.py. Speech it judges an interruption stops the reply and opens the
user's next turn (`_barge_in`). Words of a turn cut before any of its reply
was heard are CARRIED: the next reply answers them with the new turn.

PUSH-TO-TALK (protocol v0.9, ptt.py): in a "ptt" session the user's presses
replace step 2. ptt.start opens a turn (or barges in, through the same
`_interrupt` that speech uses), ptt.end ends it at once, and VAD only counts
voiced frames. There is no Endpointer and no speech-judged barge-in.
"""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from vaani.asr import Recognizer
from vaani.asr.runner import AsrRunner
from vaani.barge_in import BargeIn, join_speech, stop_reply
from vaani.config import Settings
from vaani.db import DbWriter
from vaani.echo import Echo
from vaani.endpoint import Endpointer, TurnEnded
from vaani.protocol import TurnState
from vaani.providers.base import LLMProvider
from vaani.ptt import PttBuffer
from vaani.reply import Responder
from vaani.session import Session
from vaani.telemetry import SPEECH_END, TURN_ENDED, Telemetry
from vaani.tts import Synthesizer
from vaani.turn_log import TurnLog
from vaani.turn_state import TurnStateMachine
from vaani.vad import SpeechEvent, VadStream

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
        chain: LLMProvider | None,
        voices: dict[str, Synthesizer] | None,  # language -> voice; None: no TTS
        db: DbWriter | None = None,  # None: [db] disabled, nothing recorded
    ) -> None:
        self._session = session
        self._telemetry = telemetry
        self._send_json = send_json
        self._frame_ms = settings.audio.frame_ms
        self._machine = TurnStateMachine(session, send_json)
        self._echo = Echo(
            settings.gateway.echo_enabled,
            settings.audio.sample_rate,
            session,
            telemetry,
            send_json,
            send_bytes,
        )
        # Each stage needs the one before it: no VAD, no endpointing; no
        # endpointing (no utterances), nothing to transcribe; no transcript
        # (or no model), nothing to answer. A ptt session swaps the
        # Endpointer for a PttBuffer: presses, not silences, end its turns.
        ptt = session.mode == "ptt"
        self._vad = (
            VadStream(vad_model, settings.vad, settings.audio)
            if settings.vad.enabled
            else None
        )
        self._endpointer = (
            Endpointer(
                settings.endpoint,
                self._frame_ms,
                settings.vad.threshold,
                session.session_id,
            )
            if self._vad is not None and settings.endpoint.enabled and not ptt
            else None
        )
        self._ptt = (
            PttBuffer(
                settings.endpoint,
                self._frame_ms,
                settings.vad.threshold,
                session.session_id,
            )
            if self._vad is not None and ptt
            else None
        )
        self._asr = (
            AsrRunner(
                recognizer,
                settings.asr,
                self._frame_ms,
                send_json,
                telemetry,
                self._on_final,
            )
            if (self._endpointer or self._ptt) is not None and recognizer is not None
            else None
        )
        self._responder = (
            Responder(
                chain,
                voices,
                settings,
                session,
                telemetry,
                send_json,
                send_bytes,
                self._machine.move_to,
            )
            if self._asr is not None and chain is not None
            else None
        )
        self._barge = BargeIn(settings.barge_in, settings.vad, self._frame_ms)
        # Rows only for sessions that can reply: a turn is a question + answer.
        self._log = None
        if db is not None and self._responder is not None:
            self._log = TurnLog(db, session, telemetry, self._responder)
            self._machine.on_change = self._log.state_changed
        # perf_counter of the last turn_ended, for the first-token log line.
        self._ended_at = 0.0
        # Turns whose final transcript has been asked for and not yet come.
        self._awaiting_final: set[str] = set()
        # Words of turns a barge-in cut before the user heard any reply.
        self._carried = ""
        # The turn after a cut was too short: answer carried words on arrival.
        self._answer_carried = False

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
        if self._ptt is not None:
            # Push-to-talk: the frame joins the open press, if there is one.
            if self._ptt.push(data, self._vad.probability):
                await self._release()  # held past max_utterance_ms
        elif self._endpointer is not None:
            # THE ROUTING SEAM: who gets the user's speech right now.
            if self._machine.state in (TurnState.THINKING, TurnState.SPEAKING):
                await self._watch(data, speech_event)
            else:
                if self._barge.judging:
                    # The reply ended while speech begun over it was being
                    # judged: it is the user's next turn, first frames included.
                    for frame, event, probability in self._barge.take():
                        await self._endpoint(frame, event, probability)
                await self._endpoint(data, speech_event, self._vad.probability)
        await self._echo.frame(data)

    async def on_ptt_start(self) -> None:
        """ptt.start: the user pressed speak (ptt sessions only)."""
        sid = self._session.session_id
        if self._ptt is None:
            log.warning("session %s: ptt.start ignored, VAD is off", sid)
            return
        if self._ptt.holding:
            # A key held down repeats its keydown, so this is normal.
            log.info("session %s: ptt.start ignored, press already open", sid)
            return
        if self._machine.state in (TurnState.THINKING, TurnState.SPEAKING):
            await self._interrupt(perf_counter())
        else:
            await self._open_turn()
        # No frame can arrive before these two lines run: the gateway handles
        # one message at a time. The client sent no frames since the last
        # press, so VAD's memory is of old audio: start it clean.
        assert self._vad is not None  # a PttBuffer is built only with VAD
        self._vad.reset()
        self._ptt.press()

    async def on_ptt_end(self) -> None:
        """ptt.end: the user pressed stop. The turn ends now, no silence wait."""
        if self._ptt is None or not self._ptt.holding:
            sid = self._session.session_id
            log.info("session %s: ptt.end ignored, no press open", sid)
            return
        await self._release()

    async def on_session_end(self) -> None:
        """Clean session.end: close the open echo turn before the socket."""
        await self._echo.end()

    async def close(self, reason: str = "disconnect") -> None:
        """Session over, cleanly or not. Sends nothing: the socket may be gone.
        `reason` is the session row's end_reason (client_end, disconnect, error)."""
        if self._responder is not None:
            self._responder.cancel()
            try:
                await self._responder.wait()  # every reply's HTTP stream closed
            except Exception:
                # Typically a send on the socket that has just closed.
                log.exception("session %s: reply ended badly", self._session.session_id)
        if self._asr is not None:
            await self._asr.close()
        if self._endpointer is not None:
            self._endpointer.close()
        if self._ptt is not None:
            self._ptt.close()
        if self._log is not None:
            self._log.session_closed(reason, self._machine.state)

    # --- Routing -------------------------------------------------------------

    async def _endpoint(
        self, data: bytes, speech_event: SpeechEvent | None, probability: float
    ) -> None:
        """Agent not busy: the user's speech opens and ends turns."""
        ep = self._endpointer
        assert ep is not None  # on_frame routes here only when it exists
        was_open = ep.utterance_open
        turn = ep.push(data, speech_event, probability)
        if turn is not None:
            await self._end_turn(turn)
        elif was_open and not ep.utterance_open:
            await self._discard_turn()  # shorter than min_utterance_ms
        # Opens on speech_started, and again straight after a forced end
        # (max_utterance_ms) - unless that end just made the agent busy.
        if (
            ep.utterance_open
            and not self._session.turn_open
            and self._machine.state is TurnState.IDLE
        ):
            await self._open_turn()
        turn_id = self._session.current_turn_id
        if self._asr is not None and turn_id is not None:
            self._asr.maybe_request_partial(turn_id, ep)

    async def _watch(self, data: bytes, speech_event: SpeechEvent | None) -> None:
        """Agent busy: is the user's speech an interruption? (barge_in.py)"""
        assert self._vad is not None and self._endpointer is not None
        if self._barge.push(data, speech_event, self._vad.probability):
            await self._barge_in()
        elif not self._barge.judging:
            # No speech, or a noise that stopped short. The endpointer still
            # gets every frame, as silence: its pre-roll stays the latest audio.
            for frame, _, _ in self._barge.take():
                self._endpointer.push(frame, None, 0.0)

    async def _barge_in(self) -> None:
        """The user is talking over the agent: stop it, then open their turn."""
        assert self._barge.started is not None
        await self._interrupt(self._barge.started.at)
        # 5. The speech so far, pre-roll included, as if endpointed live.
        for frame, event, probability in self._barge.take():
            await self._endpoint(frame, event, probability)

    async def _interrupt(self, onset_at: float) -> None:
        """Steps 1 to 4 of a barge-in, by speech (_barge_in) or by a press
        (on_ptt_start). `onset_at`: perf_counter of the speech or the press."""
        assert self._responder is not None  # thinking and speaking need one
        # The new turn answers carried words. Reset BEFORE stop_reply's first
        # await: an older cut turn's final arriving while audio.flush is sent
        # must not start a reply for the turn being cut (_on_final).
        self._answer_carried = False
        # 1-3 (barge_in.py): silence first, then stream, synthesis, history.
        carried = await stop_reply(
            self._responder,
            self._session,
            self._telemetry,
            self._send_json,
            onset_at,
            self._machine.state,
        )
        self._carried = join_speech(self._carried, carried)
        # 4. Close the agent's turn; the new turn_id is the user's.
        await self._machine.move_to(TurnState.CANCELLING)
        await self._open_turn()

    # --- Turn lifecycle ----------------------------------------------------

    async def _open_turn(self) -> None:
        turn_id = self._session.open_turn()
        log.info("session %s: turn %s opened", self._session.session_id, turn_id)
        await self._machine.move_to(TurnState.LISTENING)
        await self._echo.start(turn_id)

    async def _end_turn(self, turn: TurnEnded) -> None:
        turn_id = self._session.current_turn_id
        assert turn_id is not None  # a turn ends only after one opened
        self._telemetry.record(TURN_ENDED, turn_id)
        self._telemetry.record(SPEECH_END, turn_id, at=turn.speech_ended_at or turn.at)
        self._ended_at = turn.at
        waited = (
            "forced"
            if turn.speech_ended_at is None
            else f"waited {(turn.at - turn.speech_ended_at) * 1000:.0f} ms"
        )
        log.info(
            "session %s: turn_ended turn %s frames %d-%d, %d ms, %d ms voiced, "
            "%d frames buffered (%s)",
            self._session.session_id,
            turn_id,
            turn.start_frame,
            turn.end_frame,
            turn.duration_ms,
            turn.voiced_frames * self._frame_ms,
            turn.frame_count,
            waited,
        )
        await self._echo.end()
        self._session.close_turn()
        # Thinking only if a model will answer. Without one the transcript is
        # still sent, but the agent itself is idle.
        if self._asr is None or self._responder is None:
            await self._machine.move_to(TurnState.IDLE)
        else:
            await self._machine.move_to(TurnState.THINKING)
            self._awaiting_final.add(turn_id)
        if self._asr is not None:
            self._asr.request_final(turn_id, turn.audio, turn.duration_ms, turn.at)

    async def _release(self) -> None:
        """Close the open press: a turn, or a discarded one if it was empty."""
        assert self._ptt is not None
        turn = self._ptt.release()
        if turn is None:
            await self._discard_turn()  # listening -> idle (or carried words)
        else:
            await self._end_turn(turn)

    async def _discard_turn(self) -> None:
        turn_id = self._session.current_turn_id
        assert turn_id is not None
        log.info(
            "session %s: turn %s discarded (too short)",
            self._session.session_id,
            turn_id,
        )
        await self._echo.end()
        self._session.close_turn()
        if self._asr is not None:
            self._asr.abandon_turn(turn_id)
        if not self._carried and not self._awaiting_final:
            await self._machine.move_to(TurnState.IDLE)
            return
        # Too short to be a turn (a "hmm"), but it cut words off that were
        # never answered: answer them, now or when their transcript comes.
        await self._machine.move_to(TurnState.THINKING)
        self._ended_at = perf_counter()
        self._answer_carried = bool(self._awaiting_final)
        if not self._answer_carried:
            await self._reply(turn_id)

    # --- Reply lifecycle ---------------------------------------------------

    async def _on_final(self, turn_id: str, text: str | None) -> None:
        """AsrRunner's hand-over. `text` is None if transcription failed (the
        runner already sent ASR_FAILED). Must return quickly."""
        if self._responder is None:
            return  # no model: the turn already went idle
        self._awaiting_final.discard(turn_id)
        current = self._session.current_turn_id
        if turn_id != current or self._session.is_flushed(turn_id):
            # A turn a barge-in cut while it was still being transcribed: the
            # next turn is open, or (flushed) the barge-in is still sending
            # audio.flush or cancelling and has not opened it yet. Its words
            # (none if it failed) are carried, never answered as this turn.
            if turn_id == current:
                log.info(
                    "session %s: final for turn %s arrived during its barge-in, "
                    "carried",
                    self._session.session_id,
                    turn_id,
                )
            self._carried = join_speech(self._carried, text)
            if self._answer_carried and not self._awaiting_final:
                await self._reply(current)
            return
        await self._reply(turn_id, text)

    async def _reply(self, turn_id: str, text: str | None = None) -> None:
        """Answer `text`, after any carried words. The state is `thinking`."""
        assert self._responder is not None  # thinking needs one
        text = join_speech(self._carried, text)
        self._carried, self._answer_carried = "", False
        if not text:  # failed, or nothing to answer
            await self._machine.move_to(TurnState.IDLE)
            return
        self._responder.start(turn_id, text, self._ended_at)
