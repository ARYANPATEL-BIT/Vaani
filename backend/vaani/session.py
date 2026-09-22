"""Per-connection session state for the WebSocket gateway.

A Session is the server's memory of one live conversation: who it is, when it
started, and how many valid audio frames it has seen. Exactly one Session
exists per WebSocket connection, owned by the coroutine handling that socket.
Nothing here is shared between connections, so no locking is needed.
"""

from dataclasses import dataclass, field
from time import monotonic


@dataclass
class Session:
    """State for a single live session.

    `frame_count` is the running total for the whole session (handy for a
    closing log line). `frames_this_interval` is the short-lived counter the
    per-interval logger reads and then resets — it answers "how many frames in
    the last second?" rather than "how many ever?".
    """

    session_id: str
    persona: str
    # monotonic() is a clock that only moves forward and is immune to system
    # time changes — correct for measuring elapsed time, not wall-clock dates.
    created_at: float = field(default_factory=monotonic)
    frame_count: int = 0
    frames_this_interval: int = 0

    def record_frame(self) -> None:
        """Count one valid audio frame."""
        self.frame_count += 1
        self.frames_this_interval += 1

    def take_interval_count(self) -> int:
        """Return frames seen since the last call, and reset the interval
        counter to zero for the next window."""
        count = self.frames_this_interval
        self.frames_this_interval = 0
        return count
