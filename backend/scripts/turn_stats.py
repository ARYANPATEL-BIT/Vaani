"""Latency per stage, read from the session and turn database (vaani/db.py).

For the turns that match the filters, prints:
  * each of the five stage timings of turn_log.py: how many turns measured
    it (a NULL is "not measured": a cut turn may have no audio), its p50
    (median) and its p95 (nearest rank, as telemetry.py computes it: with
    fewer than 20 values that is simply the largest);
  * how many turns ended each way (outcome).

The database is opened READ-ONLY, so this can run while the server writes:
WAL mode lets a reader and the writer work at the same time.

Filters (all optional, combined with AND):
  --date YYYY-MM-DD   sessions that STARTED on that date, in this machine's
                      local time (the file stores UTC)
  --session ID        one session_id
  --mode vad|ptt      hands-free or push-to-talk sessions

Run from backend/:
    uv run python scripts/turn_stats.py --date 2026-10-13 --mode ptt
Output is ASCII only: no transcript text is printed, only numbers.
"""

import argparse
import sqlite3
import sys
from statistics import median

from vaani.config import Settings
from vaani.db import resolve
from vaani.telemetry import _nearest_rank_p95  # the project's one p95 rule
from vaani.turn_log import STAGES

# As schema.sql's CHECK on turns.outcome.
OUTCOMES = ("replied", "cut", "empty", "failed", "closed")


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", help="database file (default: [db].path)")
    parser.add_argument("--date", help="YYYY-MM-DD, local date the session started")
    parser.add_argument("--session", help="one session_id")
    parser.add_argument("--mode", choices=("vad", "ptt"))
    return parser.parse_args(argv)


def query(args: argparse.Namespace) -> tuple[str, dict]:
    """The SELECT for the filters given, with its named parameters."""
    stages = ", ".join(f"t.{column}" for column, _, _ in STAGES)
    where = []
    if args.date:
        # 'localtime' converts the stored UTC time to this machine's zone.
        where.append("date(s.started_at, 'localtime') = :date")
    if args.session:
        where.append("t.session_id = :session")
    if args.mode:
        where.append("s.mode = :mode")
    sql = (
        f"SELECT t.outcome, {stages} FROM turns t "
        "JOIN sessions s ON s.id = t.session_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    params = {"date": args.date, "session": args.session, "mode": args.mode}
    return sql, params


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    file = resolve(args.db or Settings().db.path)
    try:
        # mode=ro: read-only, and an error (not a new empty file) if missing.
        conn = sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)
        rows = conn.execute(*query(args)).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        print(f"cannot read {file}: {exc}")
        return 1

    filters = ", ".join(
        f"{name} {getattr(args, name) or 'any'}" for name in ("date", "session", "mode")
    )
    print(f"{file}")
    print(f"{len(rows)} turns ({filters})")
    print()
    print(f"{'stage':<24}{'count':>7}{'p50 ms':>11}{'p95 ms':>11}")
    for i, (column, _, _) in enumerate(STAGES, start=1):
        values = sorted(row[i] for row in rows if row[i] is not None)
        if values:
            p50, p95 = median(values), _nearest_rank_p95(values)
            print(f"{column:<24}{len(values):>7}{p50:>11.1f}{p95:>11.1f}")
        else:
            print(f"{column:<24}{0:>7}{'-':>11}{'-':>11}")
    print()
    print(f"{'outcome':<24}{'count':>7}")
    for outcome in OUTCOMES:
        count = sum(1 for row in rows if row[0] == outcome)
        print(f"{outcome:<24}{count:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
