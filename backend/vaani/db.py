"""The session and turn database: open it, and write to it off the event loop.

SQLite keeps the whole database in ONE FILE (backend/data/vaani.db by
default) and runs inside our own process: there is no database server. The
standard library's sqlite3 module talks to it with plain SQL.

Two jobs here:

1. `open_db`, once at startup (app.py): creates the file if needed, switches
   it to WAL mode, applies schema.sql and checks the schema version. Any
   problem raises DbOpenError and the server refuses to start.

   WAL ("write-ahead log"): a write is appended to a side file (vaani.db-wal)
   instead of rewriting the main file in place, so a reader such as
   scripts/turn_stats.py can read while the server writes, and a crash
   mid-write leaves the database as it was before that write.

2. `DbWriter`: the process's ONE writer. A thread that owns the connection
   and runs queued statements one at a time, in the order they were queued.
   The event loop only puts a statement on the queue (`queue.Queue.put_nowait`
   never waits), so a slow disk can never delay a frame, a transcript or a
   reply. One writer also means rows land in order (a session's row before
   its turns') and never compete for SQLite's single write lock.

A failed write logs a warning naming the statement and the error, never the
row's values (they hold what the user said), and the writer moves on.
"""

import logging
import queue
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("vaani.db")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
# The PRAGMA user_version schema.sql sets. Bump both together.
SCHEMA_VERSION = 1
# Relative [db].path values are resolved against backend/, like model paths.
_BACKEND = Path(__file__).resolve().parent.parent

INSERT_SESSION = (
    "INSERT INTO sessions (id, started_at, persona, mode) "
    "VALUES (:id, :started_at, :persona, :mode)"
)
END_SESSION = (
    "UPDATE sessions SET ended_at = :ended_at, end_reason = :end_reason WHERE id = :id"
)
TURN_COLUMNS = (
    "id, session_id, turn_index, outcome, user_text, user_script, reply_script, "
    "reply_generated, reply_heard, llm_provider, llm_model, error_code, "
    "end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, "
    "end_to_first_audio_ms"
)
# ":id, :session_id, ..." built from the column list, so the two cannot drift.
INSERT_TURN = (
    f"INSERT INTO turns ({TURN_COLUMNS}) VALUES "
    f"({', '.join(':' + c.strip() for c in TURN_COLUMNS.split(','))})"
)

# One queued statement: (name for the log, SQL, its named parameters).
Item = tuple[str, str, dict]


class DbOpenError(Exception):
    """The database could not be opened at startup."""


def resolve(path: str) -> Path:
    """[db].path as a file path: relative paths are under backend/."""
    return _BACKEND / path  # an absolute `path` replaces _BACKEND entirely


def open_db(path: str) -> sqlite3.Connection:
    """Open (or create) the database, in WAL mode, with the schema applied."""
    file = resolve(path)
    conn = None
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit, every statement is its own
        # transaction, committed when it returns. check_same_thread=False:
        # opened here, at startup, so a failure stops the server, but used
        # only by the writer thread from then on.
        conn = sqlite3.connect(file, isolation_level=None, check_same_thread=False)
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if mode != "wal":  # e.g. a filesystem without the shared memory WAL needs
            raise DbOpenError(f"WAL mode refused (journal_mode is {mode!r})")
        # Off by default in SQLite, and set per connection: makes the
        # turns.session_id REFERENCES clause actually checked.
        conn.execute("PRAGMA foreign_keys = ON")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise DbOpenError(
                f"schema version {version}, this code knows {SCHEMA_VERSION} "
                "and has no migrations"
            )
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise DbOpenError(
                f"schema.sql set version {version}, db.py expects {SCHEMA_VERSION}"
            )
    except (sqlite3.Error, OSError, DbOpenError) as exc:
        if conn is not None:
            conn.close()
        raise DbOpenError(
            f"cannot open the database {file}: {exc}. To run without it, set "
            "[db].enabled = false in config.toml (or VAANI_DB__ENABLED=false)"
        ) from exc
    log.info("database %s open (WAL, schema v%d)", file, SCHEMA_VERSION)
    return conn


class DbWriter:
    """Runs every database write, in order, on one thread of its own."""

    def __init__(self, conn: sqlite3.Connection, close_timeout_s: float) -> None:
        self._conn = conn
        self._close_timeout_s = close_timeout_s
        # Thread-safe and unbounded: put_nowait never waits and never fails.
        self._queue: queue.Queue[Item | None] = queue.Queue()
        # daemon=True: if close() gives up on a stuck disk, this thread does
        # not keep the process alive. WAL keeps the file consistent anyway.
        self._thread = threading.Thread(
            target=self._run, name="vaani-db-writer", daemon=True
        )
        self._thread.start()

    def insert_session(self, row: dict) -> None:
        self._queue.put_nowait(("insert_session", INSERT_SESSION, row))

    def end_session(self, row: dict) -> None:
        self._queue.put_nowait(("end_session", END_SESSION, row))

    def insert_turn(self, row: dict) -> None:
        self._queue.put_nowait(("insert_turn", INSERT_TURN, row))

    def close(self) -> None:
        """Finish the queue, waiting at most close_timeout_s; never hang."""
        self._queue.put_nowait(None)  # the stop marker, behind every row
        self._thread.join(self._close_timeout_s)
        if self._thread.is_alive():
            # Still inside a write: leave the connection to it, do not wait.
            # The stop marker is still queued too; it is not a row.
            left = self._queue.qsize() - 1
            log.warning(
                "database writer did not finish within %.1f s: %d items still "
                "queued, not written",
                self._close_timeout_s,
                left,
            )
            return
        self._conn.close()
        log.info("database writer stopped: 0 items still queued")

    def _run(self) -> None:
        """The writer thread: one statement at a time until the stop marker."""
        while (item := self._queue.get()) is not None:
            name, sql, params = item
            try:
                # sqlite3 releases the GIL while SQLite works, so this does
                # not hold up the event loop's thread.
                self._conn.execute(sql, params)
            except Exception as exc:
                # The error only, never `params`: they hold what users said.
                # SQLite's messages name columns, not values.
                log.warning("database %s failed: %s: %s", name, type(exc).__name__, exc)
