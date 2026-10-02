"""Day 4 flush tests, driven through the real /ws/session socket.

Many tests end with `_next_is_reack`: sending a second session.start and
checking that the very next server message is the re-ack. Because the server
handles messages in order, that proves nothing else (a late frame, an error, a
second audio.flush) was sent before it.
"""

import logging

from starlette.websockets import WebSocketDisconnect

from tests.test_gateway import (  # noqa: F401 (autouse fixture, used by name)
    START,
    distinct_frame,
    make_client,
    speech_on_first_frame,
)


def _start_echo_turn(ws) -> str:
    """Start a session, echo one frame, and return the open turn's id."""
    ws.send_json(START)
    ws.receive_json()  # session.started
    ws.send_bytes(distinct_frame())
    turn_id = ws.receive_json()["turn_id"]  # audio.start
    ws.receive_bytes()  # the echoed frame
    return turn_id


def _next_is_reack(ws) -> bool:
    """True if the next server message is the idempotent session.started."""
    ws.send_json(START)
    return ws.receive_json()["type"] == "session.started"


def _ack(turn_id: str) -> dict:
    return {"type": "flush.ack", "turn_id": turn_id, "client_ts": 1.5}


def test_dev_flush_sends_audio_flush_for_current_turn() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        turn_id = _start_echo_turn(ws)
        ws.send_json({"type": "dev.flush"})
        reply = ws.receive_json()

    assert reply == {"type": "audio.flush", "turn_id": turn_id}


def test_flush_stops_further_frames_for_that_turn() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        _start_echo_turn(ws)
        ws.send_json({"type": "dev.flush"})
        ws.receive_json()  # audio.flush

        for _ in range(3):
            ws.send_bytes(distinct_frame())  # late frames for the flushed turn
        assert _next_is_reack(ws)  # none of the three came back


def test_flush_ack_is_recorded_with_round_trip(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="vaani.session"):
        with make_client().websocket_connect("/ws/session") as ws:
            turn_id = _start_echo_turn(ws)
            ws.send_json({"type": "dev.flush"})
            ws.receive_json()  # audio.flush
            ws.send_json(_ack(turn_id))
            assert _next_is_reack(ws)  # the ack drew no reply; socket alive

    acked = [r.getMessage() for r in caplog.records if "flush acked" in r.msg]
    assert len(acked) == 1
    assert turn_id in acked[0] and "round trip" in acked[0]


def test_unknown_flush_ack_is_ignored_and_logged(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.session"):
        with make_client().websocket_connect("/ws/session") as ws:
            _start_echo_turn(ws)
            ws.send_json(_ack("never-existed"))
            assert _next_is_reack(ws)  # no error sent back

    assert any("ignoring flush.ack" in r.msg for r in caplog.records)


def test_ack_for_current_but_unflushed_turn_is_ignored(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.session"):
        with make_client().websocket_connect("/ws/session") as ws:
            turn_id = _start_echo_turn(ws)  # open, never flushed
            ws.send_json(_ack(turn_id))
            assert _next_is_reack(ws)

    assert any("ignoring flush.ack" in r.msg for r in caplog.records)


def test_duplicate_flush_ack_is_ignored(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="vaani.session"):
        with make_client().websocket_connect("/ws/session") as ws:
            turn_id = _start_echo_turn(ws)
            ws.send_json({"type": "dev.flush"})
            ws.receive_json()  # audio.flush
            ws.send_json(_ack(turn_id))
            ws.send_json(_ack(turn_id))  # second copy
            assert _next_is_reack(ws)

    messages = [r.msg for r in caplog.records]
    assert sum("flush acked" in m for m in messages) == 1
    assert sum("ignoring flush.ack" in m for m in messages) == 1


def test_second_dev_flush_is_idempotent() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        _start_echo_turn(ws)
        ws.send_json({"type": "dev.flush"})
        ws.receive_json()  # the one audio.flush
        ws.send_json({"type": "dev.flush"})
        assert _next_is_reack(ws)  # no second audio.flush


def test_dev_flush_with_no_turn_sends_nothing() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        ws.send_json(START)
        ws.receive_json()
        ws.send_json({"type": "dev.flush"})
        assert _next_is_reack(ws)


def test_malformed_flush_ack_returns_bad_message() -> None:
    with make_client().websocket_connect("/ws/session") as ws:
        _start_echo_turn(ws)
        ws.send_json({"type": "flush.ack"})  # missing turn_id and client_ts
        reply = ws.receive_json()

    assert reply["code"] == "BAD_MESSAGE"


def test_no_audio_end_for_flushed_turn() -> None:
    """A flush ends the turn, so session.end is followed directly by close."""
    with make_client().websocket_connect("/ws/session") as ws:
        _start_echo_turn(ws)
        ws.send_json({"type": "dev.flush"})
        ws.receive_json()  # audio.flush
        ws.send_json({"type": "session.end"})
        try:
            ws.receive_json()
            raised = None
        except WebSocketDisconnect as exc:
            raised = exc

    assert raised is not None and raised.code == 1000
