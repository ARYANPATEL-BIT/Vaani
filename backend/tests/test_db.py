"""feat/database: the database file, its writer thread, and turn_stats.py.

Every test uses a temporary file (pytest's tmp_path), never
backend/data/vaani.db. The gateway-level tests, rows written by real
turns, are in tests/test_turn_log.py.
"""

import importlib.util
import logging
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from vaani.app import create_app
from vaani.config import DbSettings, Settings
from vaani.db import (
    INSERT_SESSION,
    INSERT_TURN,
    SCHEMA_VERSION,
    DbOpenError,
    DbWriter,
    open_db,
)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "turn_stats.py"


def session_row(
    sid: str = "s1", mode: str = "vad", started: str = "2026-10-13 10:00:00.000"
):
    return {"id": sid, "started_at": started, "persona": "default", "mode": mode}


def turn_row(tid: str, sid: str = "s1", index: int = 1, outcome="replied", ms=None):
    """A turn row; every stage timing is `ms` (None: not measured)."""
    row = dict.fromkeys(
        (
            "user_text user_script reply_script reply_generated reply_heard "
            "llm_provider llm_model error_code end_to_asr_ms asr_ms "
            "llm_first_token_ms tts_first_chunk_ms end_to_first_audio_ms"
        ).split()
    )
    row.update(id=tid, session_id=sid, turn_index=index, outcome=outcome)
    for column in row:
        if column.endswith("_ms"):
            row[column] = ms
    return row


# --- Opening the file -----------------------------------------------------------


def test_open_creates_the_schema_in_wal_mode(tmp_path) -> None:
    conn = open_db(str(tmp_path / "sub" / "v.db"))  # the folder is created too
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 1
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"sessions", "turns", "turns_by_session"} <= tables
    conn.close()


def test_a_second_open_keeps_the_rows(tmp_path) -> None:
    path = str(tmp_path / "v.db")
    conn = open_db(path)
    conn.execute(INSERT_SESSION, session_row())
    conn.close()
    conn = open_db(path)  # CREATE ... IF NOT EXISTS: a no-op
    assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    conn.close()


def test_another_schema_version_refuses_to_open(tmp_path) -> None:
    path = tmp_path / "v.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 7")
    conn.close()
    with pytest.raises(DbOpenError, match="schema version 7"):
        open_db(str(path))


def test_the_server_refuses_to_start_naming_the_way_out(tmp_path) -> None:
    # A directory where the file should be: SQLite cannot open it.
    settings = Settings(db=DbSettings(enabled=True, path=str(tmp_path)))
    with pytest.raises(DbOpenError, match=r"\[db\]\.enabled = false"):
        create_app(settings)


# --- The writer -----------------------------------------------------------------


def test_a_failed_write_warns_without_the_row_and_the_writer_goes_on(
    tmp_path, caplog
) -> None:
    path = str(tmp_path / "v.db")
    writer = DbWriter(open_db(path), close_timeout_s=2.0)
    secret = turn_row("t1", sid="no-such-session")
    secret["user_text"] = "mera password kela123 hai"
    with caplog.at_level(logging.WARNING, logger="vaani.db"):
        writer.insert_turn(secret)  # no session row: the foreign key fails
        writer.insert_session(session_row())
        writer.insert_turn(turn_row("t2"))
        writer.close()

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "insert_turn failed: IntegrityError" in warnings[0]
    assert "kela123" not in caplog.text
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT id FROM turns").fetchall() == [("t2",)]
    conn.close()


class StuckConnection:
    """A connection whose first write never finishes, like a hung disk."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def execute(self, sql, params) -> None:
        self.release.wait(10)

    def close(self) -> None:
        pass


def test_close_gives_up_after_the_timeout_and_counts_what_is_left(caplog) -> None:
    conn = StuckConnection()
    writer = DbWriter(conn, close_timeout_s=0.2)
    for i in range(3):  # the first one sticks; two stay queued
        writer.insert_turn(turn_row(f"t{i}"))
    time.sleep(0.05)  # let the thread take the first one
    began = time.perf_counter()
    writer.close()
    waited = time.perf_counter() - began
    conn.release.set()

    assert waited < 1.0  # shutdown did not hang on the disk
    assert "did not finish within 0.2 s: 2 items still queued" in caplog.text


# --- scripts/turn_stats.py ------------------------------------------------------


def load_stats():
    spec = importlib.util.spec_from_file_location("turn_stats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lines(out: str) -> list[list[str]]:
    return [line.split() for line in out.splitlines()]


def seed(path: str) -> None:
    conn = open_db(path)
    sql = conn.execute
    sql(INSERT_SESSION, session_row("s1", "vad"))
    sql(INSERT_SESSION, session_row("s2", "ptt", started="2026-09-01 10:00:00.000"))
    for i, ms in enumerate((100.0, 200.0, 300.0, 400.0), start=1):
        sql(INSERT_TURN, turn_row(f"a{i}", "s1", i, ms=ms))
    sql(INSERT_TURN, turn_row("a5", "s1", 5, outcome="cut", ms=None))
    sql(INSERT_TURN, turn_row("b1", "s2", 1, outcome="empty", ms=None))
    conn.close()


def test_turn_stats_prints_counts_percentiles_and_outcomes(tmp_path, capsys) -> None:
    path = str(tmp_path / "v.db")
    seed(path)
    assert load_stats().main(["--db", path, "--mode", "vad"]) == 0
    out = capsys.readouterr().out
    assert out.isascii()
    assert "5 turns (date any, session any, mode vad)" in out
    # 4 measured values: p50 is their median, p95 the largest (nearest rank).
    assert ["end_to_first_audio_ms", "4", "250.0", "400.0"] in lines(out)
    assert ["replied", "4"] in lines(out)
    assert ["cut", "1"] in lines(out)
    assert ["empty", "0"] in lines(out)


def test_turn_stats_filters_by_session_and_date(tmp_path, capsys) -> None:
    path = str(tmp_path / "v.db")
    seed(path)
    stats = load_stats()
    stats.main(["--db", path, "--session", "s2"])
    out = capsys.readouterr().out
    assert "1 turns" in out
    assert ["asr_ms", "0", "-", "-"] in lines(out)
    assert ["empty", "1"] in lines(out)
    stats.main(["--db", path, "--date", "2026-09-01"])
    assert "1 turns" in capsys.readouterr().out


def test_turn_stats_reports_a_missing_file(tmp_path, capsys) -> None:
    assert load_stats().main(["--db", str(tmp_path / "none.db")]) == 1
    assert "cannot read" in capsys.readouterr().out
