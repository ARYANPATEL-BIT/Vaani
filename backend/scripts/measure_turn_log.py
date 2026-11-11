"""Cost of recording a turn: what the event loop pays, and what the disk pays.

A turn's row is built on the event loop, inside TurnStateMachine.move_to
(turn_log.TurnLog.state_changed): read the reply record and the turn's
spans, build the row, put it on the writer's queue. This times exactly that
call, for a realistic finished turn (a 10-delta reply, all spans present),
2,000 turns x 3 runs, against a real DbWriter on a temporary file, so the
writer thread is draining the queue while the loop is being timed.

It also times the other side: from the first row queued to the last row
committed by the writer thread, divided by the number of rows. That cost is
paid on the writer thread, never on the event loop.

Run from backend/ (output also goes to docs/findings/database/):
    uv run python scripts/measure_turn_log.py
"""

import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

from run_log import REPO, RunLog  # scripts/ is on sys.path when run as a file

from vaani.db import DbWriter, open_db
from vaani.protocol import TurnState
from vaani.session import Session
from vaani.telemetry import (
    ASR_FINAL,
    ASR_START,
    LLM_FIRST_TOKEN,
    LLM_REQUEST,
    SPEECH_END,
    TTS_FIRST_AUDIO,
    TTS_START,
    Telemetry,
)
from vaani.turn_log import ReplyRecord, TurnLog

TURNS = 2000
RUNS = 3
SPANS = (SPEECH_END, ASR_START, ASR_FINAL, LLM_REQUEST, LLM_FIRST_TOKEN, TTS_START)
PARTS = ["Theek hai, ", "main kal ", "aapko ", "yaad ", "dila ", "doongi. "] + [
    "Aur kuch? "
] * 4


class FakeSpeaker:
    first_script = "en"  # what TurnLog reads for reply_script


class FakeResponder:
    """Only what TurnLog reads: the latest reply's record and speaker."""

    record: ReplyRecord | None = None
    speaker = FakeSpeaker()


def one_run(db: DbWriter, run: int) -> list[float]:
    session = Session(session_id=f"run{run}", persona="default")
    telemetry = Telemetry(session.session_id)
    responder = FakeResponder()
    log = TurnLog(db, session, telemetry, responder)
    costs = []
    for i in range(TURNS):
        turn_id = session.open_turn()
        for name in (*SPANS, TTS_FIRST_AUDIO):
            telemetry.record(name, turn_id)
        reply = ReplyRecord(turn_id, f"sawaal number {i}", parts=list(PARTS))
        reply.provider, reply.model = "groq", "openai/gpt-oss-20b"
        reply.heard = "".join(PARTS)
        responder.record = reply
        began = perf_counter()
        log.state_changed(TurnState.SPEAKING, TurnState.IDLE)  # the timed call
        costs.append((perf_counter() - began) * 1e6)
    return costs


def main() -> None:
    out = RunLog("measure_turn_log", REPO / "docs" / "findings" / "database")
    out(f"{TURNS} turns x {RUNS} runs; state_changed (row built + queued) on the loop")
    with tempfile.TemporaryDirectory() as folder:
        db = DbWriter(open_db(str(Path(folder) / "m.db")), close_timeout_s=60.0)
        began = perf_counter()
        for run in range(RUNS):
            costs = sorted(one_run(db, run))
            p95 = costs[int(0.95 * len(costs)) - 1]
            out(f"  run {run + 1}: p50 {median(costs):.1f} us, p95 {p95:.1f} us")
        db.close()  # waits for every queued row to be committed
        rows = RUNS * (TURNS + 1)  # + one session row per run
        per_row = (perf_counter() - began) * 1000 / rows
    out(f"writer thread: {rows} rows committed, {per_row:.3f} ms per row on average")
    out(f"wrote {out.path.name}")


if __name__ == "__main__":
    main()
