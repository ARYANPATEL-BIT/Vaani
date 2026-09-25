"""Timing spans for the conversation path, plus one rolling latency statistic.

A "span" here is the simplest possible unit of measurement: a *named point in
time*, stamped with a high-resolution monotonic clock and tagged with the
session (and, once we have turns, the turn) it belongs to. It is not a
duration on its own — a duration is the gap between two spans, e.g.
frame_received -> echo_sent.

Today only two spans are actually emitted (frame_received, echo_sent), but the
names for the whole pipeline are defined now so that every later stage records
against a fixed, agreed vocabulary instead of inventing strings ad hoc. See the
learning doc for why the names are declared before the code that uses them.

A monotonic clock only ever moves forward and is unaffected by the wall clock
being changed (NTP steps, daylight saving, a manual clock set). That makes it
the correct kind of clock for measuring elapsed time; wall-clock time can jump
backwards and produce negative or absurd durations.

We use `time.perf_counter`, not `time.monotonic`. Both are monotonic, but on
Windows `time.monotonic` is backed by GetTickCount64 and only ticks every
15.6 ms, so any gap shorter than that reads as 0.0 ms. `perf_counter` uses
QueryPerformanceCounter (sub-microsecond) on Windows and is at least as fine
everywhere else.
"""

from collections import deque
from dataclasses import dataclass
from math import ceil
from statistics import median
from time import perf_counter

# --- Span names -------------------------------------------------------------
# Constants, not free strings, so every producer and reader spells them the
# same way. Most are unused today; they are the fixed vocabulary the later
# stages (VAD, ASR, LLM, TTS, playback) will record against.
FRAME_RECEIVED = "frame_received"
ECHO_SENT = "echo_sent"
VAD_DECISION = "vad_decision"
ASR_PARTIAL = "asr_partial"
ASR_FINAL = "asr_final"
LLM_FIRST_TOKEN = "llm_first_token"
TTS_FIRST_AUDIO = "tts_first_audio"
PLAYBACK_START = "playback_start"
# Flush round trip: server sent audio.flush -> server received flush.ack.
FLUSH_SENT = "flush_sent"
FLUSH_ACKED = "flush_acked"

# Below this many samples the rolling stats are not meaningful (see
# echo_stats_ms), so we report nothing rather than a misleading number.
MIN_SAMPLES = 20

# How many recent frame_received -> echo_sent deltas to keep.
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
    why echo_stats_ms withholds numbers until MIN_SAMPLES have been seen.
    """
    rank = ceil(0.95 * len(sorted_values))  # 1-based position
    return sorted_values[rank - 1]


class Telemetry:
    """Per-session span recorder and rolling echo-latency statistic.

    One instance lives per WebSocket connection, owned by that connection's
    coroutine, so like Session it needs no locking. It keeps the last WINDOW
    frame_received -> echo_sent deltas and can summarise them as (median, p95).
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        # Deltas in seconds; deque(maxlen=...) drops the oldest automatically,
        # giving a fixed-size sliding window for free.
        self._deltas: deque[float] = deque(maxlen=WINDOW)
        # Timestamp of the most recent frame_received still awaiting its
        # echo_sent. None between a completed pair and the next frame.
        self._pending_frame_at: float | None = None

    def record(self, name: str, turn_id: str | None = None) -> Span:
        """Stamp a span at 'now' and, for the echo pair, update the window.

        frame_received remembers its timestamp; the next echo_sent closes the
        pair and appends (echo_sent.at - frame_received.at) to the window. Any
        other span name is just stamped and returned (used by later stages).
        """
        span = Span(
            name=name, at=perf_counter(), session_id=self.session_id, turn_id=turn_id
        )
        if name == FRAME_RECEIVED:
            self._pending_frame_at = span.at
        elif name == ECHO_SENT and self._pending_frame_at is not None:
            self._deltas.append(span.at - self._pending_frame_at)
            self._pending_frame_at = None
        return span

    def echo_stats_ms(self) -> tuple[float, float] | None:
        """(median, p95) of frame_received -> echo_sent, in milliseconds.

        Returns None until at least MIN_SAMPLES deltas exist. On a small window
        the nearest-rank p95 is just the maximum (see _nearest_rank_p95), so an
        early number would overstate the tail; None says "not yet meaningful".
        """
        if len(self._deltas) < MIN_SAMPLES:
            return None
        ordered = sorted(self._deltas)
        p50 = median(ordered) * 1000.0
        p95 = _nearest_rank_p95(ordered) * 1000.0
        return (p50, p95)
