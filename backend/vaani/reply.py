"""One turn's reply: guardrail, prompt, then the model's answer streamed out.

turns.py calls `Responder.start` once a turn's final transcript arrives (the
session is then in `thinking`). That runs `_answer` as a background task,
which in order:
  1. runs the input guardrail on the raw transcript (persona.py), BEFORE the
     transcript is placed in any prompt;
  2. assembles persona prompt + history + transcript;
  3. streams the provider chain's answer, sending each piece as agent.text
     and feeding it to the chunker (chunker.py). Each chunk the chunker
     cuts is spoken AT ONCE by speaker.py, while the model is still
     generating: waiting for the whole reply would add seconds;
  4. sends agent.done, records the exchange in history, waits for the
     audio to finish playing (speaker.finish), moves to `idle`.

Day 12: `speaking` is entered by speaker.py on the first AUDIO frame, not
here on the first text. With [tts] disabled the reply is text only and the
state goes thinking -> idle.

Cancellation: each reply gets its OWN asyncio.Event as its token. turns.py
calls `cancel()` (dev.flush today, barge-in in week 3), which sets it. The
chain then closes its HTTP stream and ends quietly, and `_answer` sends
nothing more: every send below is directly preceded by a `cancel.is_set()`
check, with no `await` in between. The canceller owns the state from then on
(cancelling -> idle), so `_answer` never moves it again.

Failure is never silence: any provider error sends LLM_FAILED and then idle;
a synthesis error stops the reply and sends TTS_FAILED. agent.text already
sent stays on screen, so the text can show more than was spoken.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from time import perf_counter

from vaani.chunker import ClauseChunker
from vaani.config import Settings
from vaani.persona import assemble, looks_like_injection
from vaani.protocol import ErrorCode, TurnState, agent_done, agent_text, error
from vaani.providers.base import LLMProvider, Message, ProviderError
from vaani.session import Session
from vaani.speaker import Speaker
from vaani.spend import SpendCapExceededError
from vaani.telemetry import LLM_FIRST_TOKEN, Telemetry
from vaani.tts import Synthesizer, TtsError

log = logging.getLogger("vaani.reply")

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]
# TurnStateMachine.move_to: checks the transition is legal, then sends turn.state.
MoveTo = Callable[[TurnState], Awaitable[None]]

# Deliberately vague. Naming the rule that matched would teach a person
# exactly what the filter catches and how to step around it.
REJECTED_MESSAGE = "that turn wasn't processed"
FAILED_MESSAGE = "the agent could not answer"
SPEAK_FAILED_MESSAGE = "the agent could not speak its answer"


class Responder:
    """Answers one session's turns. Built once per session, in turns.py."""

    def __init__(
        self,
        chain: LLMProvider,
        synth: Synthesizer | None,
        settings: Settings,
        session: Session,
        telemetry: Telemetry,
        send_json: SendJson,
        send_bytes: SendBytes,
        move_to: MoveTo,
    ) -> None:
        self._chain = chain
        self._synth = synth  # None: [tts] disabled, the reply is text only
        self._chunker_cfg = settings.chunker
        self._frame_ms = settings.audio.frame_ms
        # Looked up once: the persona is fixed at session.start, and the
        # gateway has already refused a key that is not in config.
        self._system_prompt = settings.personas[session.persona]
        self._history_turns = settings.llm.history_turns
        self._patterns = settings.guardrail.patterns
        self._session = session
        self._telemetry = telemetry
        self._send = send_json
        self._send_bytes = send_bytes
        self._move_to = move_to
        # The reply in flight and its token. A fresh Event per reply: a set
        # Event would have to be cleared for the next turn, and a slow stream
        # from the previous turn would then read "not cancelled" and carry on.
        self._task: asyncio.Task | None = None
        self._cancel: asyncio.Event | None = None

    def start(self, turn_id: str, transcript: str, ended_at: float) -> None:
        """Begin replying in the background. Returns at once."""
        self._cancel = asyncio.Event()
        self._task = asyncio.create_task(
            self._answer(turn_id, transcript, self._cancel, ended_at)
        )

    def cancel(self) -> None:
        """Set the current reply's token. From this line on it sends nothing.

        Synchronous on purpose, so the caller can set it BEFORE its own next
        await. A no-op when nothing has started (still transcribing).
        """
        if self._cancel is not None:
            self._cancel.set()

    async def wait(self) -> None:
        """Wait for the reply task to end (after cancel: its stream is closed)."""
        if self._task is not None:
            await self._task

    async def _answer(
        self, turn_id: str, transcript: str, cancel: asyncio.Event, ended_at: float
    ) -> None:
        """Reply to one transcript. `ended_at` is the turn_ended perf_counter."""
        sid = self._session.session_id
        if cancel.is_set():
            return  # cancelled before this task even started running
        # 1. Guardrail, while the transcript is still a separate string.
        if looks_like_injection(transcript, self._patterns):
            log.warning("session %s: turn %s blocked by guardrail", sid, turn_id)
            await self._error_then_idle(
                ErrorCode.INPUT_REJECTED, REJECTED_MESSAGE, cancel
            )
            return

        # 2. Only now does the transcript meet the system prompt.
        messages = assemble(self._system_prompt, self._session.history, transcript)

        # 3. Stream. aclosing: if we leave the loop early, the chain's stream
        # (and its HTTP connection) is closed at once, not at garbage collection.
        parts: list[str] = []
        chunker = ClauseChunker(self._chunker_cfg)
        speaker = None
        if self._synth is not None:
            speaker = Speaker(
                self._synth,
                self._frame_ms,
                turn_id,
                cancel,
                ended_at,
                self._telemetry,
                self._send,
                self._send_bytes,
                self._move_to,
            )
        requested_at = perf_counter()
        # Each delta until the first chunk is cut: (ms after turn_ended, its
        # text). Tells "waiting for tokens" apart from "waiting on synthesis"
        # in the debug log.
        arrivals: list[tuple[float, str]] = []
        first_cut = False
        try:
            async with aclosing(self._chain.stream(messages, cancel)) as chunks:
                async for chunk in chunks:
                    if cancel.is_set():
                        return
                    if not parts:
                        self._first_token(turn_id, requested_at, ended_at)
                    parts.append(chunk.text)
                    if not first_cut:
                        arrivals.append(
                            ((perf_counter() - ended_at) * 1000, chunk.text)
                        )
                    await self._send(agent_text(turn_id, chunk.text))
                    if speaker is not None:
                        pieces = chunker.push(chunk.text)
                        if pieces and not first_cut:
                            first_cut = True
                            self._log_first_cut(
                                turn_id,
                                ended_at,
                                arrivals,
                                pieces[0],
                                chunker.first_rule,
                            )
                        # Synthesis runs inside this loop: while it does, the
                        # next tokens wait unread in the HTTP stream. Nothing
                        # is lost, and the speech is never waiting on text.
                        for piece in pieces:
                            await speaker.say(piece)
            if speaker is not None and (last := chunker.flush()):
                if not first_cut:  # the whole reply arrived without a cut
                    self._log_first_cut(
                        turn_id, ended_at, arrivals, last, chunker.first_rule
                    )
                await speaker.say(last)
        except (ProviderError, SpendCapExceededError) as exc:
            if cancel.is_set():
                return
            # Full detail in the server log only; it can name vendors and codes.
            log.warning("session %s: turn %s reply failed: %s", sid, turn_id, exc)
            await self._error_then_idle(ErrorCode.LLM_FAILED, FAILED_MESSAGE, cancel)
            return
        except TtsError as exc:
            # aclosing has already closed the model's stream on the way out.
            if cancel.is_set():
                return
            log.warning("session %s: turn %s speech failed: %s", sid, turn_id, exc)
            assert speaker is not None  # only a speaker raises TtsError
            await speaker.end_audio()
            await self._error_then_idle(
                ErrorCode.TTS_FAILED, SPEAK_FAILED_MESSAGE, cancel
            )
            return

        if cancel.is_set():
            return  # a cancelled stream ends quietly: no agent.done
        if not parts:
            # The model said nothing at all (e.g. its output was filtered).
            # Silence is not an answer.
            log.warning("session %s: turn %s got an empty reply", sid, turn_id)
            await self._error_then_idle(ErrorCode.LLM_FAILED, FAILED_MESSAGE, cancel)
            return

        # 4. Complete. Remember the exchange BEFORE the await, so a flush
        # landing during the send cannot leave a sent reply out of history.
        reply = "".join(parts)
        self._remember(transcript, reply)
        await self._send(agent_done(turn_id, reply))
        if speaker is not None and not cancel.is_set():
            await speaker.finish()  # audio.end, then wait until it has played
        if cancel.is_set():
            return
        await self._move_to(TurnState.IDLE)

    async def _error_then_idle(
        self, code: ErrorCode, message: str, cancel: asyncio.Event
    ) -> None:
        """The protocol's failure ending: error, then turn.state idle.

        Callers have just checked `cancel`. It is checked again after the
        send's await: if a flush landed meanwhile, the canceller now owns the
        state and will move it to idle itself.
        """
        await self._send(error(code, message))
        if not cancel.is_set():
            await self._move_to(TurnState.IDLE)

    def _first_token(self, turn_id: str, requested_at: float, ended_at: float) -> None:
        span = self._telemetry.record(LLM_FIRST_TOKEN, turn_id)
        log.info(
            "session %s: turn %s first token: %.0f ms after request, "
            "turn_ended->first agent.text %.0f ms",
            self._session.session_id,
            turn_id,
            (span.at - requested_at) * 1000,
            (span.at - ended_at) * 1000,
        )

    def _log_first_cut(
        self,
        turn_id: str,
        ended_at: float,
        arrivals: list[tuple[float, str]],
        chunk: str,
        rule: str | None,
    ) -> None:
        # Debug: off in normal runs, switched on for latency tuning. %a
        # escapes non-ASCII, so Devanagari never reaches the console raw.
        log.debug(
            "session %s: turn %s first chunk %a cut %.0f ms after turn_ended "
            "by rule %r; deltas (ms, chars, text): %a",
            self._session.session_id,
            turn_id,
            chunk,
            (perf_counter() - ended_at) * 1000,
            rule,
            [(round(at), len(text), text) for at, text in arrivals],
        )

    def _remember(self, transcript: str, reply: str) -> None:
        """Append the exchange, then keep only the newest history_turns."""
        history = self._session.history
        history.append(Message(role="user", content=transcript))
        history.append(Message(role="assistant", content=reply))
        # Two messages per exchange. max(0, ...) so history_turns = 0 keeps
        # nothing (a bare `history[:-0]` would mean "keep everything").
        del history[: max(0, len(history) - 2 * self._history_turns)]
