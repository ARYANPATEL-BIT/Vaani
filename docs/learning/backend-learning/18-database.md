# 18 - Database: every session and turn, recorded in SQLite

Branch `feat/database` (from `dev`, uncommitted). No protocol change.

## 1. What

Until now, everything the server knew about a conversation was lost when the socket
closed. This branch writes it down. A **database** is a file the program can add rows to
and search later. Each **table** holds one kind of row, and each **column** holds one
fact about that row. There are two tables. `sessions` has one row per connection: when
it started and ended, the persona, the mode (hands-free or push-to-talk) and why it
ended. `turns` has one row per user turn: what the model was asked, what it generated,
what the user actually heard, which provider answered, any error, the outcome (replied,
cut, empty, failed, closed) and five timings in milliseconds. Text and numbers only,
never audio. Nothing is ever read back into a conversation: the agent's memory is still
`Session.history` in RAM, exactly as before.

## 2. Why

Every latency number so far came from a measurement script run on purpose. Real use left
nothing behind but log lines. With the database, `backend/scripts/turn_stats.py` prints
the count, p50 and p95 of each stage for any day, session or mode, from turns people
actually had. That gives us the "P50 under 1,000 ms" check from real use.

What was measured, under the laptop's "Silent" power scheme:

| `on_frame` p50 / p95, microseconds (median of 3 runs) | before | after |
|---|---|---|
| idle, silent frames | 104.7 / 136.8 | 101.9 / 128.2 |
| idle, speech fixture | 106.2 / 157.8 | 103.7 / 133.5 |
| agent speaking, silent frames | 111.0 / 163.6 | 102.8 / 129.5 |

Sources: `docs/findings/database/measure_on_frame_20261013-003140.txt` (before) and
`..._004345.txt` (after). "After" being lower is noise between runs. The change itself
can only add one `if` per frame. Recording a finished turn costs the event loop
2.2 us at p50 and 3.5 us at p95. Writing it to disk then costs 0.77 ms per row, on
a separate thread (`docs/findings/database/measure_turn_log_20261013-004409.txt`).
**Not measured:** a full turn from mic-stop to audio (`measure_turn.py`). It needs Groq
and real Whisper, and was not run.

## 3. How

1. **SQLite.** The database is a single file, `backend/data/vaani.db`. That folder is
   gitignored, because the file holds what people said. SQLite is a library inside our
   own process, not a separate server; Python's standard `sqlite3` module speaks plain
   SQL to it. The tables are written once, in `backend/vaani/schema.sql`.
2. **Opening, at startup.** `open_db` in `backend/vaani/db.py`, called from `app.py`:
   - It switches the file to **WAL mode** (write-ahead log). A write is appended to a
     side file instead of rewriting the main file in place. So `turn_stats.py` can read
     while the server writes, and a crash in the middle of a write leaves the database
     as it was before that write.
   - It checks **`user_version`**, a number SQLite keeps in the file's header. Ours is
     the schema's version: 0 means a new file, so the schema is created; 1 is current;
     anything else means "this file was made by other code", and the server refuses to
     start.
   - If the file cannot be opened, the server refuses to start. The message says that
     `[db].enabled = false` runs without the database.
3. **The writer thread.** `DbWriter` in `db.py`. A **thread** is a second line of
   execution in the same program. Our event loop (the single thread that serves every
   WebSocket) must never wait on a disk. So only one thread ever writes, and it owns the
   database connection. Everyone else drops statements into its **queue** (a
   thread-safe waiting line). Putting an item in never waits. The writer runs the
   statements one at a time, in order, so a session's row always lands before its turns'
   rows.
4. **When a row is made.** `backend/vaani/turn_log.py`, class `TurnLog`, one per
   session, built in `turns.py`. Every turn ends with the turn state machine
   (`turn_state.py`) moving to `idle` (finished) or `cancelling` (a barge-in cut it).
   `move_to` now calls `TurnLog.state_changed` on every move, so that one hook sees
   every ending. The row is built there, at that instant, and queued. If anything in it
   raises, it logs a warning and gives up on the row; the turn goes on.
5. **Where the values come from.** `reply.py` fills in a small `ReplyRecord` while the
   reply runs: deltas, provider, model, error, and what went into history (the same
   "only what was heard" rule as `barge_in.py`). Timings come from telemetry **spans**
   (named instants on the `perf_counter` clock, `telemetry.py`), which now remember
   each turn's latest stamp per name. Three spans are new: `speech_end` (VAD's
   `speech_ended`, or the `ptt.end`), `llm_request` and `tts_start`.
6. **Closing.** The gateway decides the end reason (`client_end`, `disconnect` or
   `error`) and passes it to `TurnPipeline.close`. A turn still live at that moment is
   recorded as `closed`. At shutdown the writer gets `[db].close_timeout_s` (2 s) to
   finish its queue. After that it logs how many rows were not written and lets the
   server exit.

## 4. When

- **Server start:** the file is opened and checked, and the writer thread starts.
- **`session.start`:** one `sessions` row is queued.
- **A turn ends (idle or cancelling):** one `turns` row is queued. That is always after
  the reply's first audio, so nothing is written between the end of the user's speech
  and the first audio frame.
- **Socket closed:** a live turn's `closed` row is queued, then the session's end.
- **Any time:** `turn_stats.py` reads the file, read-only.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| SQLite (standard library) | PostgreSQL | A database server to install, run and secure, plus a new driver dependency, for one machine with a few rows a minute. |
| Raw SQL with `sqlite3` | An ORM such as SQLAlchemy (Python classes mapped to tables) | A new dependency and a layer that writes the SQL for you. With three statements, you can read the real SQL in `db.py` instead. |
| WAL mode | SQLite's default rollback journal | A reader blocks the writer, and the writer blocks readers, so running `turn_stats.py` while the server records turns could stall the writes. |
| `PRAGMA user_version` | A `schema_version` table | A table must itself be created and read with SQL. The header number exists in every SQLite file, at no cost. |
| One writer thread with a queue | `asyncio.to_thread` for every write | Two sessions' writes could run on two threads at once and compete for SQLite's single write lock. A turn row could even land before its session row and break the `REFERENCES` link. |
| One hook in `TurnStateMachine.move_to` | Write calls at each place a turn ends (about 8, in `turns.py`, `reply.py`, `barge_in.py`) | Easy to miss one, and a new ending path would silently record nothing. |
| An `outcome` column | A `barge_in` yes/no column | `outcome = 'cut'` already says it. Two columns that must agree will one day disagree. |
| Refuse to start if the file cannot open | Start without the database and log a warning | A typo in `[db].path` would quietly record nothing for days. |

## 6. Known issues

- Not measured end to end: no `measure_turn.py` run (needs Groq and real Whisper).
- "End of speech" in hands-free mode is VAD's `speech_ended`, which fires some time after
  the last sound (measured in `docs/findings/perf-1-latency-budget.md`). "First audio" is
  the first frame *sent*, not the first sample heard.
- The writer's queue has no size limit. If the disk stalls, rows pile up in memory. At a
  few rows a minute this was judged not worth a limit.
- `tts_first_chunk_ms` includes waiting for more text if the first chunk had nothing
  sayable (only punctuation). A row is lost (with a warning) if its write fails.
- `turns.py` is now 411 lines, `reply.py` 309 and `gateway.py` 319, all over the ~300
  limit. The `turns.py` split is still a planned follow-up.
  