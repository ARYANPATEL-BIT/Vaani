"""AsrRunner scheduling, with a fake recogniser (no model).

Covers: a final is sent in protocol shape; an abandoned inference emits
nothing; close() mid-inference emits nothing; partials do not queue (latest
wins); a final supersedes its turn's running partial; the timeout reports a
failure without freeing the thread early; abandoning many inferences in a row
does not starve the pool for other sessions.
"""

import asyncio
from time import perf_counter

from tests.fake_asr import FakeRecognizer
from vaani.asr.runner import AsrRunner
from vaani.config import Settings
from vaani.telemetry import Telemetry

PCM = b"\x00\x00" * 1600  # 100 ms of silence; the fake ignores content


def asr_cfg(**update):
    return Settings().asr.model_copy(update={"enabled": True, **update})


def new_runner(rec: FakeRecognizer, sent: list, session: str = "s1", **cfg):
    async def send(msg: dict) -> None:
        sent.append((perf_counter(), msg))

    return AsrRunner(rec, asr_cfg(**cfg), send, Telemetry(session))


async def settle(runner: AsrRunner, seconds: float = 0.0) -> None:
    """Let the drain task run, then wait for it to finish."""
    await asyncio.sleep(seconds)
    if runner._task is not None:
        await runner._task


def test_final_is_sent_in_protocol_shape() -> None:
    async def go():
        sent: list = []
        runner = new_runner(FakeRecognizer(), sent)
        runner.request_final("t1", PCM, duration_ms=1200, ended_at=perf_counter())
        await settle(runner)
        return [m for _, m in sent]

    assert asyncio.run(go()) == [
        {
            "type": "transcript.final",
            "turn_id": "t1",
            "text": "namaste duniya",
            "duration_ms": 1200,
            "language": "hi",
        }
    ]


def test_abandon_mid_inference_emits_nothing() -> None:
    async def go():
        sent: list = []
        rec = FakeRecognizer(gated=True)
        runner = new_runner(rec, sent)
        runner.request_final("t1", PCM, 500, perf_counter())
        while not rec.started.is_set():  # inference is now running
            await asyncio.sleep(0.005)
        runner.abandon_turn("t1")
        rec.gate.set()  # let the "uninterruptible" decode finish
        await settle(runner)
        return sent, rec.windows

    sent, windows = asyncio.run(go())
    assert sent == []  # it finished, but its result was discarded
    assert len(windows) == 1  # and it really did run to the end


def test_close_mid_inference_emits_nothing_and_returns_at_once() -> None:
    async def go():
        sent: list = []
        rec = FakeRecognizer(gated=True)
        runner = new_runner(rec, sent)
        runner.request_final("t1", PCM, 500, perf_counter())
        while not rec.started.is_set():
            await asyncio.sleep(0.005)
        started = perf_counter()
        await runner.close()  # disconnect: must not wait for the decode
        took = perf_counter() - started
        rec.gate.set()
        await asyncio.sleep(0.1)  # give a (wrong) late emit a chance to happen
        return sent, took

    sent, took = asyncio.run(go())
    assert sent == []
    assert took < 0.5


def test_partials_do_not_queue_latest_wins() -> None:
    async def go():
        sent: list = []
        rec = FakeRecognizer(gated=True)
        runner = new_runner(rec, sent)
        runner.request_partial("t1", b"a" * 2)
        while not rec.started.is_set():
            await asyncio.sleep(0.005)
        # Three more arrive while the first is still decoding.
        for text in (b"b", b"c", b"d"):
            runner.request_partial("t1", text * 2)
        rec.gate.set()
        await settle(runner)
        return sent, rec.windows

    sent, windows = asyncio.run(go())
    assert len(windows) == 2  # the running one + only the LATEST waiting one
    assert [m["type"] for _, m in sent] == ["transcript.partial"] * 2


def test_final_discards_its_turns_running_partial() -> None:
    async def go():
        sent: list = []
        rec = FakeRecognizer(gated=True)
        runner = new_runner(rec, sent)
        runner.request_partial("t1", PCM)
        while not rec.started.is_set():
            await asyncio.sleep(0.005)
        runner.request_final("t1", PCM, 900, perf_counter())
        rec.gate.set()
        await settle(runner)
        return [m["type"] for _, m in sent]

    assert asyncio.run(go()) == ["transcript.final"]


def test_timeout_reports_failure_but_keeps_the_slot_until_the_thread_is_free() -> None:
    async def go():
        sent: list = []
        rec = FakeRecognizer(decode_s=0.6)
        runner = new_runner(rec, sent, timeout_s=0.1)
        t0 = perf_counter()
        runner.request_final("t1", PCM, 500, t0)
        runner.request_final("t2", PCM, 500, t0)
        await settle(runner)
        return [(at - t0, m) for at, m in sent], rec

    sent, rec = asyncio.run(go())
    (fail_at, fail), (ok_at, ok) = sent
    assert fail["type"] == "error" and fail["code"] == "ASR_FAILED"
    assert fail_at < 0.4  # reported at the timeout, not when the decode ended
    # t2 did not start until t1's thread was free: one thread per session.
    assert ok["type"] == "error" and ok_at > 0.6  # t2 times out too...
    assert rec.max_active == 1  # ...but never ran alongside t1


def test_abandoning_many_inferences_does_not_starve_other_sessions() -> None:
    """Rapid turns from one user, each abandoned, must not use up the pool.

    Pool of 2. Session A starts and abandons 5 finals in a row, then asks for
    a 6th. Session B asks for one final at the same moment. If abandoned
    decodes each held a thread, B would queue behind them.
    """
    decode = 0.3

    async def go():
        rec = FakeRecognizer(decode_s=decode, workers=2)
        sent_a: list = []
        sent_b: list = []
        a = new_runner(rec, sent_a, "A")
        b = new_runner(rec, sent_b, "B")
        t0 = perf_counter()
        for i in range(5):
            a.request_final(f"a{i}", PCM, 500, t0)
            await asyncio.sleep(0.01)
            a.abandon_turn(f"a{i}")
        a.request_final("a-last", PCM, 500, t0)
        b.request_final("b1", PCM, 500, t0)
        await asyncio.gather(settle(a), settle(b))
        return t0, sent_a, sent_b, rec

    t0, sent_a, sent_b, rec = asyncio.run(go())
    assert [m["turn_id"] for _, m in sent_a] == ["a-last"]
    assert [m["turn_id"] for _, m in sent_b] == ["b1"]
    # B got a free thread straight away: one decode, not six.
    assert sent_b[0][0] - t0 < decode * 1.8
    # A waited for at most its ONE abandoned decode, then ran its last.
    assert sent_a[0][0] - t0 < decode * 2.8
    assert rec.max_active <= 2
