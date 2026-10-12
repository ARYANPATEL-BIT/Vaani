"""The turn state machine: what the agent is doing, as one value.

The five states (idle, listening, thinking, speaking, cancelling) are wire
values, so they live in protocol.py. WHICH moves between them are legal is
decided here: `_LEGAL` lists every allowed move, and `TurnStateMachine.move_to`
is the only way to change state. It raises on anything else and tells the
browser about every change with turn.state.

turns.py moves the state as turns open, end and are barged in on; reply.py
and speaker.py move it as the agent answers. All go through `move_to`.

feat/database: because every move goes through `move_to`, so does every
turn's end (a move to idle or cancelling). `on_change`, when set, hears
every move; TurnPipeline sets it to the turn log (turn_log.py).
"""

import logging
from collections.abc import Awaitable, Callable

from vaani.protocol import TurnState, turn_state
from vaani.session import Session

log = logging.getLogger("vaani.turns")

SendJson = Callable[[dict], Awaitable[None]]
# (old state, new state). Synchronous: runs inside move_to, before its send.
OnChange = Callable[[TurnState, TurnState], None]

# Every legal move, and nothing else. An unlisted move is a bug in the
# caller, so it raises instead of quietly happening.
_LEGAL: dict[TurnState, set[TurnState]] = {
    TurnState.IDLE: {TurnState.LISTENING},  # speech started: a turn opens
    # Turn over -> thinking. Too short, flushed, or no model -> idle.
    TurnState.LISTENING: {TurnState.THINKING, TurnState.IDLE},
    # First audio -> speaking; failed or nothing to say -> idle;
    # barge-in -> cancelling.
    TurnState.THINKING: {TurnState.SPEAKING, TurnState.IDLE, TurnState.CANCELLING},
    # Reply played or failed -> idle; barge-in -> cancelling.
    TurnState.SPEAKING: {TurnState.IDLE, TurnState.CANCELLING},
    # Only a barge-in cancels, and the user's speech that caused it opens
    # their new turn straight away (day 13). There is no cancelling -> idle:
    # it went with dev.flush, the one cancel that had no speech behind it.
    TurnState.CANCELLING: {TurnState.LISTENING},
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
        # Set after construction by TurnPipeline, once the turn log exists
        # (it needs the Responder, which needs this machine's move_to).
        self.on_change: OnChange | None = None

    async def move_to(self, new: TurnState) -> None:
        """The ONLY way the state changes: check, record, tell the browser.

        Recorded BEFORE the send, like a flush mark: anything that runs during
        the send's await must already see the new state.
        """
        check_transition(self.state, new)
        old, self.state = self.state, new
        turn_id = None if new is TurnState.IDLE else self._session.current_turn_id
        log.info("session %s: %s -> %s", self._session.session_id, old, new)
        if self.on_change is not None:
            # No await before it: it sees the turn exactly as it ended.
            self.on_change(old, new)
        await self._send_json(turn_state(turn_id, new))
