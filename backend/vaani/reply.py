"""One turn's reply: guardrail, prompt, then the model's answer streamed out.

turns.py calls `Responder.start` once a turn's final transcript arrives (the
session is then in `thinking`). That runs `_answer` as a background task,
which in order:
  1. runs the input guardrail on the raw transcript (persona.py), BEFORE the
     transcript is placed in any prompt;
  2. assembles persona prompt + history + transcript;
  3. streams the provider chain's answer, sending each chunk as agent.text
     and moving to `speaking` on the first one;
  4. sends agent.done, records the exchange in history, moves to `idle`.

Cancellation: each reply gets its OWN asyncio.Event as its token. turns.py
calls `cancel()` (dev.flush today, barge-in in week 3), which sets it. The
chain then closes its HTTP stream and ends quietly, and `_answer` sends
nothing more: every send below is directly preceded by a `cancel.is_set()`
check, with no `await` in between. The canceller owns the state from then on
(cancelling -> idle), so `_answer` never moves it again.

Failure is never silence: any provider error sends LLM_FAILED and then idle.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from time import perf_counter

from vaani.config import Settings
from vaani.persona import assemble, looks_like_injection
from vaani.protocol import ErrorCode, TurnState, agent_done, agent_text, error
from vaani.providers.base import LLMProvider, Message, ProviderError
from vaani.session import Session
from vaani.spend import SpendCapExceededError
from vaani.telemetry import LLM_FIRST_TOKEN, Telemetry

log = logging.getLogger("vaani.reply")

SendJson = Callable[[dict], Awaitable[None]]
# TurnPipeline.move_to: checks the transition is legal, then sends turn.state.
MoveTo = Callable[[TurnState], Awaitable[None]]

# Deliberately vague. Naming the rule that matched would teach a person
# exactly what the filter catches and how to step around it.
REJECTED_MESSAGE = "that turn wasn't processed"
FAILED_MESSAGE = "the agent could not answer"


class Responder:
    """Answers one session's turns. Built once per session, in turns.py."""

    def __init__(
        self,
        chain: LLMProvider,
        settings: Settings,
        session: Session,
        telemetry: Telemetry,
        send_json: SendJson,
        move_to: MoveTo,
    ) -> None:
        self._chain = chain
        # Looked up once: the persona is fixed at session.start, and the
        # gateway has already refused a key that is not in config.
        self._system_prompt = settings.personas[session.persona]
        self._history_turns = settings.llm.history_turns
        self._patterns = settings.guardrail.patterns
        self._session = session
        self._telemetry = telemetry
        self._send = send_json
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
        requested_at = perf_counter()
        try:
            async with aclosing(self._chain.stream(messages, cancel)) as chunks:
                async for chunk in chunks:
                    if cancel.is_set():
                        return
                    if not parts:
                        self._first_token(turn_id, requested_at, ended_at)
                        await self._move_to(TurnState.SPEAKING)
                        # The move awaited a send; a flush may have landed.
                        if cancel.is_set():
                            return
                    parts.append(chunk.text)
                    await self._send(agent_text(turn_id, chunk.text))
        except (ProviderError, SpendCapExceededError) as exc:
            if cancel.is_set():
                return
            # Full detail in the server log only; it can name vendors and codes.
            log.warning("session %s: turn %s reply failed: %s", sid, turn_id, exc)
            await self._error_then_idle(ErrorCode.LLM_FAILED, FAILED_MESSAGE, cancel)
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

    def _remember(self, transcript: str, reply: str) -> None:
        """Append the exchange, then keep only the newest history_turns."""
        history = self._session.history
        history.append(Message(role="user", content=transcript))
        history.append(Message(role="assistant", content=reply))
        # Two messages per exchange. max(0, ...) so history_turns = 0 keeps
        # nothing (a bare `history[:-0]` would mean "keep everything").
        del history[: max(0, len(history) - 2 * self._history_turns)]
