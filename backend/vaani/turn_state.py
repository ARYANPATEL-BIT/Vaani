"""The turn state machine: what the agent is doing, as one value.

The five states (idle, listening, thinking, speaking, cancelling) are wire
values, so they live in protocol.py. WHICH moves between them are legal is
decided here: `_LEGAL` lists every allowed move, and `TurnStateMachine.move_to`
is the only way to change state. It raises on anything else and tells the
browser about every change with turn.state.

turns.py moves the state as turns open and end; reply.py moves it as the
agent answers. Both go through the same `move_to`.
"""

import logging
from collections.abc import Awaitable, Callable

from vaani.protocol import TurnState, turn_state
from vaani.session import Session

log = logging.getLogger("vaani.turns")

SendJson = Callable[[dict], Awaitable[None]]

# Every legal move, and nothing else. An unlisted move is a bug in the
# caller, so it raises instead of quietly happening.
_LEGAL: dict[TurnState, set[TurnState]] = {
    TurnState.IDLE: {TurnState.LISTENING},  # speech started: a turn opens
    # Turn over -> thinking. Too short, flushed, or no model -> idle.
    TurnState.LISTENING: {TurnState.THINKING, TurnState.IDLE},
    # First reply text -> speaking; failed or nothing to say -> idle.
    TurnState.THINKING: {TurnState.SPEAKING, TurnState.IDLE, TurnState.CANCELLING},
    # Reply done or failed -> idle; dev.flush -> cancelling.
    TurnState.SPEAKING: {TurnState.IDLE, TurnState.CANCELLING},
    # dev.flush (no speech caused it) -> idle. Week-3 barge-in (the user's
    # speech caused it and already opened the new turn) -> listening.
    TurnState.CANCELLING: {TurnState.IDLE, TurnState.LISTENING},
}


class IllegalTransition(Exception):
    """A move `_LEGAL` does not allow was attempted."""


def check_transition(current: TurnState, new: TurnState) -> None:
    """Raise IllegalTransition unless current -> new is in `_LEGAL`."""
    if new not in _LEGAL[current]:
        raise IllegalTransition(f"{current} -> {new}")


class TurnStateMachine:
    """One session's current state. Built by TurnPipeline."""

    def __init__(self, session: Session, send_json: SendJson) -> None:
        self._session = session
        self._send_json = send_json
        self.state = TurnState.IDLE

    async def move_to(self, new: TurnState) -> None:
        """The ONLY way the state changes: check, record, tell the browser.

        Recorded BEFORE the send, like a flush mark: anything that runs during
        the send's await must already see the new state.
        """
        check_transition(self.state, new)
        old, self.state = self.state, new
        turn_id = None if new is TurnState.IDLE else self._session.current_turn_id
        log.info("session %s: %s -> %s", self._session.session_id, old, new)
        await self._send_json(turn_state(turn_id, new))
