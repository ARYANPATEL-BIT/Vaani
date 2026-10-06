"""Flush round trip, driven through the real /ws/session socket.

Since day 13 the only thing that flushes is a barge-in (dev.flush, the day-4
stand-in, is gone), so every flush here comes from one: the scripted VAD and
fakes of tests/test_barge_in.py, a reply playing, then 200 ms of speech.

Many tests end with `reacks`: sending a second session.start and checking
that the very next server message is the re-ack. Because the server handles
messages in order, that proves nothing else (an error, a second audio.flush)
was sent before it.
"""

import logging

from tests.fake_tts import FakeSynthesizer
from tests.test_barge_in import (  # noqa: F401 (autouse fixture, used by name)
    Recognizer,
    barge,
    make_client,
    say,
    scripted_vad,
)
from tests.test_turn_llm import ScriptedLLM, reacks, start
from tests.test_turn_tts import is_, until


def _client():
    return make_client(
        ScriptedLLM(("Theek hai, ", "sab theek hai.")),
        FakeSynthesizer(audio_ms_per_char=50),  # 1.2 s: still playing at the cut
        Recognizer("kya haal hai", "ruko"),
    )


def _barge_in(ws) -> tuple[str, str]:
    """Start a session, cut the agent's reply; return (flushed, new) turn ids."""
    start(ws)
    say(ws)
    until(ws, is_("frame"))
    barge(ws)
    cut = until(ws, is_("listening"))
    flush = next(m for m in cut if is_("audio.flush")(m))
    return flush["turn_id"], cut[-1]["turn_id"]


def _ack(turn_id: str) -> dict:
    return {"type": "flush.ack", "turn_id": turn_id, "client_ts": 1.5}


def test_ack_for_the_flushed_turn_is_recorded_while_a_newer_turn_is_open(
    caplog,
) -> None:
    with caplog.at_level(logging.INFO, logger="vaani.session"):
        with _client().websocket_connect("/ws/session") as ws:
            flushed, new = _barge_in(ws)
            ws.send_json(_ack(flushed))
            assert reacks(ws)  # the ack drew no reply; socket alive

    assert flushed != new  # the ack is for a turn that is no longer current
    acked = [r.getMessage() for r in caplog.records if "flush acked" in r.msg]
    assert len(acked) == 1
    assert flushed in acked[0] and "round trip" in acked[0]


def test_duplicate_flush_ack_is_ignored(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="vaani.session"):
        with _client().websocket_connect("/ws/session") as ws:
            flushed, _ = _barge_in(ws)
            ws.send_json(_ack(flushed))
            ws.send_json(_ack(flushed))  # second copy
            assert reacks(ws)

    messages = [r.msg for r in caplog.records]
    assert sum("flush acked" in m for m in messages) == 1
    assert sum("ignoring flush.ack" in m for m in messages) == 1


def test_ack_for_a_turn_never_flushed_is_ignored(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.session"):
        with _client().websocket_connect("/ws/session") as ws:
            _, new = _barge_in(ws)
            ws.send_json(_ack(new))  # open, never flushed
            ws.send_json(_ack("never-existed"))
            assert reacks(ws)  # no error sent back

    assert sum("ignoring flush.ack" in r.msg for r in caplog.records) == 2


def test_malformed_flush_ack_returns_bad_message() -> None:
    with _client().websocket_connect("/ws/session") as ws:
        start(ws)
        ws.send_json({"type": "flush.ack"})  # missing turn_id and client_ts
        reply = ws.receive_json()

    assert reply["code"] == "BAD_MESSAGE"


def test_dev_flush_is_gone() -> None:
    """Removed in protocol v0.7: it is an unknown type now."""
    with _client().websocket_connect("/ws/session") as ws:
        start(ws)
        ws.send_json({"type": "dev.flush"})
        reply = ws.receive_json()

    assert reply["code"] == "UNKNOWN_MESSAGE_TYPE"
