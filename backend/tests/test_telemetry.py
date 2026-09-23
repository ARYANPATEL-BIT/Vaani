"""Tests for the telemetry span recorder and rolling echo statistic.

These do not touch the network. They drive the Telemetry object directly and,
where the timing gap must be a known number, monkeypatch the monotonic clock so
each frame_received -> echo_sent delta is exactly what we say it is.
"""

import pytest

import vaani.telemetry as telemetry_mod
from vaani.telemetry import (
    ECHO_SENT,
    FRAME_RECEIVED,
    MIN_SAMPLES,
    Telemetry,
    _nearest_rank_p95,
)


class FakeClock:
    """A monotonic() stand-in whose value we advance by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _feed(tele: Telemetry, deltas_ms: list[float], clock: FakeClock) -> None:
    """Record one frame_received/echo_sent pair per delta, gap = delta_ms."""
    for ms in deltas_ms:
        tele.record(FRAME_RECEIVED, "turn-1")
        clock.now += ms / 1000.0  # advance the fake clock by the gap
        tele.record(ECHO_SENT, "turn-1")


def test_record_returns_span_with_session_and_turn() -> None:
    tele = Telemetry("sess-1")
    span = tele.record(FRAME_RECEIVED, "turn-1")

    assert span.name == FRAME_RECEIVED
    assert span.session_id == "sess-1"
    assert span.turn_id == "turn-1"
    assert isinstance(span.at, float)


def test_stats_none_below_min_samples(monkeypatch) -> None:
    clock = FakeClock()
    monkeypatch.setattr(telemetry_mod, "monotonic", clock)
    tele = Telemetry("sess-1")

    _feed(tele, [5.0] * (MIN_SAMPLES - 1), clock)
    assert tele.echo_stats_ms() is None  # one short of the threshold

    _feed(tele, [5.0], clock)  # now exactly MIN_SAMPLES
    assert tele.echo_stats_ms() is not None


def test_rolling_stats_correct_on_known_sequence(monkeypatch) -> None:
    """Deltas 1..100 ms: median = 50.5 ms, nearest-rank p95 = 95 ms."""
    clock = FakeClock()
    monkeypatch.setattr(telemetry_mod, "monotonic", clock)
    tele = Telemetry("sess-1")

    _feed(tele, [float(n) for n in range(1, 101)], clock)

    # approx() absorbs the tiny float error from summing gaps on the fake clock;
    # the intended values are exact (median of 1..100 = 50.5, p95 rank 95 = 95).
    p50, p95 = tele.echo_stats_ms()
    assert p50 == pytest.approx(50.5)
    assert p95 == pytest.approx(95.0)


def test_window_keeps_only_last_100(monkeypatch) -> None:
    """After 150 frames of 1..150 ms, the window holds 51..150; p95 tracks it."""
    clock = FakeClock()
    monkeypatch.setattr(telemetry_mod, "monotonic", clock)
    tele = Telemetry("sess-1")

    _feed(tele, [float(n) for n in range(1, 151)], clock)

    p50, p95 = tele.echo_stats_ms()
    # Window is 51..150: median of those 100 values is (100+101)/2 = 100.5.
    assert p50 == pytest.approx(100.5)
    # nearest-rank p95 of 51..150 is the 95th of 100 sorted -> value 145.
    assert p95 == pytest.approx(145.0)


def test_nearest_rank_p95_small_window_is_max() -> None:
    """The documented caveat: on a tiny window p95 collapses to the maximum."""
    assert _nearest_rank_p95([1.0, 2.0, 3.0, 4.0, 5.0]) == 5.0
