"""Unit tests for Session's flush state, without any network.

`send_json` is replaced by a small recorder so we can inspect exactly what
would have gone over the wire, and what the session looked like at that moment.
"""

import asyncio

import pytest

import vaani.telemetry as telemetry_mod
from vaani.protocol import FlushAck
from vaani.session import Session
from vaani.telemetry import Telemetry


class RecordingSend:
    """Stand-in for websocket.send_json. It also notes whether the turn was
    already marked flushed at the moment the send started."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sent: list[dict] = []
        self.flushed_during_send: list[bool] = []

    async def __call__(self, payload: dict) -> None:
        self.flushed_during_send.append(self.session.is_flushed(payload["turn_id"]))
        self.sent.append(payload)


def _session_with_turn() -> tuple[Session, str]:
    session = Session(session_id="s1", persona="default")
    return session, session.open_turn()


def test_flush_marks_turn_before_sending() -> None:
    """The mark must already be set while the send is in flight."""
    session, turn_id = _session_with_turn()
    send = RecordingSend(session)

    result = asyncio.run(session.flush(send, Telemetry("s1")))

    assert result == turn_id
    assert send.sent == [{"type": "audio.flush", "turn_id": turn_id}]
    assert send.flushed_during_send == [True]


def test_flush_without_turn_sends_nothing() -> None:
    session = Session(session_id="s1", persona="default")
    send = RecordingSend(session)

    assert asyncio.run(session.flush(send, Telemetry("s1"))) is None
    assert send.sent == []


def test_round_trip_measured_on_server_clock(monkeypatch) -> None:
    """flush_sent at t=10.000 s, flush_acked at t=10.004 s -> 4 ms. client_ts
    is a wildly different number and must not affect the result."""
    now = {"t": 10.0}
    monkeypatch.setattr(telemetry_mod, "perf_counter", lambda: now["t"])
    session, turn_id = _session_with_turn()
    tele = Telemetry("s1")

    asyncio.run(session.flush(RecordingSend(session), tele))
    now["t"] = 10.004
    ack = FlushAck(type="flush.ack", turn_id=turn_id, client_ts=987654.0)

    assert session.handle_flush_ack(ack, tele) == pytest.approx(4.0)


def test_ack_for_an_older_flushed_turn_is_recorded() -> None:
    """Day 13: a barge-in flushes the agent's turn and opens the user's next
    one at once, so the ack always arrives when a newer turn is current."""
    session, old_turn = _session_with_turn()
    tele = Telemetry("s1")
    asyncio.run(session.flush(RecordingSend(session), tele))
    session.open_turn()  # a newer turn is now current
    ack = FlushAck(type="flush.ack", turn_id=old_turn, client_ts=1.0)

    assert session.handle_flush_ack(ack, tele) is not None
    assert session.handle_flush_ack(ack, tele) is None  # a second copy is not
