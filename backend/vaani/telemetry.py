"""Timing spans for the conversation path, plus one rolling latency statistic.

A "span" here is the simplest possible unit of measurement: a *named point in
time*, stamped with a high-resolution monotonic clock and tagged with the
session and, when there is one, the turn it belongs to. It is not a
duration on its own — a duration is the gap between two spans, e.g.
frame_received -> echo_sent.

Every name below is recorded somewhere except playback_start: the browser,
not the server, knows when audio starts playing. Some fire only when config
turns their feature on: frame_received and echo_sent need
[gateway].echo_enabled, asr_partial needs [asr].partial_interval_ms above 0.
The names live in one place so every stage records against a fixed, agreed
vocabulary instead of inventing strings ad hoc.

A monotonic clock only ever moves forward and is unaffected by the wall clock
being changed (NTP steps, daylight saving, a manual clock set). That makes it
the correct kind of clock for measuring elapsed time; wall-clock time can jump
backwards and produce negative or absurd durations.

We use `time.perf_counter`, not `time.monotonic`. Both are monotonic, but on
Windows `time.monotonic` is backed by GetTickCount64 and only ticks every
15.6 ms, so any gap shorter than that reads as 0.0 ms. `perf_counter` uses
QueryPerformanceCounter (sub-microsecond) on Windows and is at least as fine
everywhere else.

feat/database: every span recorded WITH a turn_id is also kept, per turn,
latest stamp per name, until `pop_turn` hands them over. turn_log.py turns
them into the five per-stage timings of the turn's database row.
"""

from collections import deque
from dataclasses import dataclass
from math import ceil
from statistics import median
from time import perf_counter

# --- Span names -------------------------------------------------------------
# Constants, not free strings, so every producer and reader spells them the
# same way. Which ones are recorded: see the module docstring.
FRAME_RECEIVED = "frame_received"
ECHO_SENT = "echo_sent"
VAD_DECISION = "vad_decision"
# The user's speech ended: VAD's speech_ended in hands-free mode, the ptt.end
# in push-to-talk, the turn's end if it was forced (max_utterance_ms).
SPEECH_END = "speech_end"
# The endpointer decided the user's turn is over.
TURN_ENDED = "turn_ended"
# Speech recognition: one inference handed to a worker thread, then the
# partial or final transcript it produced was sent to the browser.
ASR_START = "asr_start"
ASR_PARTIAL = "asr_partial"
ASR_FINAL = "asr_final"
# A turn's final transcript failed (ASR_FAILED was sent).
ASR_FAILED = "asr_failed"
# The reply's request went to the provider chain; its first text came back.
LLM_REQUEST = "llm_request"
LLM_FIRST_TOKEN = "llm_first_token"
# The reply's first chunk started synthesis; its first frame was sent.
TTS_START = "tts_start"
TTS_FIRST_AUDIO = "tts_first_audio"
PLAYBACK_START = "playback_start"
# Barge-in: the user's speech was judged an interruption (barge_in.py).
BARGE_IN = "barge_in"
# Flush round trip: server sent audio.flush -> server received flush.ack.
FLUSH_SENT = "flush_sent"
FLUSH_ACKED = "flush_acked"

# Below this many samples the rolling stats are not meaningful (see
# RollingStat.stats_ms), so we report nothing rather than a misleading number.
MIN_SAMPLES = 20

# How many recent durations each rolling window keeps.
WINDOW = 100


@dataclass(frozen=True)
class Span:
    """A single named point in time.

    `at` is perf_counter seconds (only comparable to other perf_counter
    readings, not to a calendar). `turn_id` is None until a turn exists.
    Frozen because a recorded measurement is a fact — nothing should mutate
    it after the event.
    """

    name: str
    at: float
    session_id: str
    turn_id: str | None = None


def _nearest_rank_p95(sorted_values: list[float]) -> float:
    """95th percentile by the nearest-rank method on already-sorted values.

    Nearest-rank: the p-th percentile is the value at position ceil(p/100 * N)
    (1-based) in the sorted list. For p95 that is index ceil(0.95 * N) - 1.

    Caveat: on a small window this collapses to (nearly) the maximum — e.g. with
    N < 20, ceil(0.95 * N) == N, so p95 IS the largest sample. That is exactly
    why RollingStat.stats_ms withholds numbers until MIN_SAMPLES have been seen.
    """
    rank = ceil(0.95 * len(sorted_values))  # 1-based position
    return sorted_values[rank - 1]


class RollingStat:
    """The last WINDOW durations, summarised as (median, p95) in milliseconds.

    Used twice: for the echo gap (frame_received -> echo_sent) and for the
    per-frame VAD cost. One class so both numbers are computed identically.
    """

    def __init__(self) -> None:
        # Durations in seconds; deque(maxlen=...) drops the oldest automatically,
        # giving a fixed-size sliding window for free.
        self._values: deque[float] = deque(maxlen=WINDOW)

    def add(self, seconds: float) -> None:
        self._values.append(seconds)

    def stats_ms(self) -> tuple[float, float] | None:
        """(median, p95) in milliseconds, or None below MIN_SAMPLES.

        On a small window the nearest-rank p95 is just the maximum (see
        _nearest_rank_p95), so an early number would overstate the tail; None
        says "not yet meaningful".
        """
        if len(self._values) < MIN_SAMPLES:
            return None
        ordered = sorted(self._values)
        p50 = median(ordered) * 1000.0
        p95 = _nearest_rank_p95(ordered) * 1000.0
        return (p50, p95)


class Telemetry:
    """Per-session span recorder and rolling latency statistics.

    One instance lives per WebSocket connection, owned by that connection's
    coroutine, so like Session it needs no locking. It keeps two rolling
    windows: the echo gap and the per-frame VAD cost.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._echo = RollingStat()
        self._vad = RollingStat()
        # Timestamp of the most recent frame_received still awaiting its
        # echo_sent. None between a completed pair and the next frame.
        self._pending_frame_at: float | None = None
        # turn_id -> {span name: its latest `at`}, until pop_turn takes it.
        self._turns: dict[str, dict[str, float]] = {}

    def record(
        self, name: str, turn_id: str | None = None, at: float | None = None
    ) -> Span:
        """Stamp a span at 'now' (or at `at`, a perf_counter reading taken
        earlier) and, for the echo pair, update the window.

        frame_received remembers its timestamp; the next echo_sent closes the
        pair and appends (echo_sent.at - frame_received.at) to the window. Any
        other span name is just stamped and returned (used by later stages).
        A span with a turn_id is also kept for that turn's database row.
        """
        span = Span(
            name=name,
            at=perf_counter() if at is None else at,
            session_id=self.session_id,
            turn_id=turn_id,
        )
        if turn_id is not None:
            self._turns.setdefault(turn_id, {})[name] = span.at
        if name == FRAME_RECEIVED:
            self._pending_frame_at = span.at
        elif name == ECHO_SENT and self._pending_frame_at is not None:
            self._echo.add(span.at - self._pending_frame_at)
            self._pending_frame_at = None
        return span

    def pop_turn(self, turn_id: str) -> dict[str, float]:
        """Hand over (and forget) every span kept for `turn_id`, by name."""
        return self._turns.pop(turn_id, {})

    def record_vad_decision(self, started_at: float) -> Span:
        """Stamp vad_decision now and add its cost (now - started_at) to the window.

        `started_at` is a perf_counter reading taken just before the VAD call,
        so the recorded cost is exactly the time VAD held the event loop.
        """
        span = self.record(VAD_DECISION)
        self._vad.add(span.at - started_at)
        return span

    def echo_stats_ms(self) -> tuple[float, float] | None:
        """(median, p95) of frame_received -> echo_sent, in milliseconds."""
        return self._echo.stats_ms()

    def vad_stats_ms(self) -> tuple[float, float] | None:
        """(median, p95) of the per-frame VAD cost, in milliseconds."""
        return self._vad.stats_ms()
