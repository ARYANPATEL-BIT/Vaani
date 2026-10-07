"""Replay logged replies through today's chunker: where would the first cut be?

reply.py's debug line (`_log_first_cut`) records, for each turn, the first
chunk the server actually cut, when, by which rule, and every model delta that
had arrived by then, with its arrival time (ms after turn_ended). This script
feeds those same deltas, in order, through the CURRENT ClauseChunker and
config, so the comparison uses the model's real timing, not a guess:

    before  what the log says was cut, and when
    after   what today's chunker cuts from the same deltas, and when (the
            arrival time of the delta that completed the cut)

Only text timing: synthesis time for the new chunk lengths is measured
separately by measure_tts.py. No model, no network.

Run from backend/ (output also goes to docs/findings/tuning/):
    uv run python scripts/replay_first_chunk.py <server log with debug lines>
"""

import argparse
import ast
import re
from pathlib import Path
from statistics import median

from run_log import TUNING, RunLog  # scripts/ is on sys.path when run as a file

from vaani.chunker import ClauseChunker
from vaani.config import get_settings

# The fields of reply.py's first-cut debug line. %a and %r wrote them as
# Python literals, so ast.literal_eval reads them back exactly.
LINE = re.compile(
    r"first chunk (?P<chunk>'.*?') cut (?P<cut>\d+) ms after turn_ended "
    r"by rule '(?P<rule>[^']+)'; deltas \(ms, chars, text\): (?P<deltas>\[.*\])"
)


def replay(deltas: list, logged_cut: int) -> tuple[str, float, str]:
    """(first chunk, ms its last delta arrived, rule) with today's chunker."""
    chunker = ClauseChunker(get_settings().chunker)
    for at, _, text in deltas:
        if pieces := chunker.push(text):
            return pieces[0], at, chunker.first_rule or ""
    # No cut while streaming: the reply's end cuts it. That happens when the
    # stream CLOSES, a little after the last delta, which only the log knows.
    return chunker.flush() or "", logged_cut, chunker.first_rule or ""


def main(path: Path) -> None:
    log = RunLog("replay_first_chunk", out=TUNING)
    log(f"source {path.name}")
    log("turn  before: ms  chars rule          after: ms  chars rule          saved ms")
    saved = []
    lines = path.read_text(encoding="utf-8").splitlines()
    turns = [m for line in lines if (m := LINE.search(line))]
    for n, m in enumerate(turns, 1):
        before = ast.literal_eval(m["chunk"])
        cut = int(m["cut"])
        after, at, rule = replay(ast.literal_eval(m["deltas"]), cut)
        saved.append(cut - at)
        log(
            f"{n:>4}  {cut:>10}  {len(before):>5} {m['rule']:<13} "
            f"{at:>9.0f}  {len(after):>5} {rule:<13} {cut - at:>8.0f}"
        )
        log(f"      before {before!r}")
        log(f"      after  {after!r}")
    if saved:
        log(
            f"\n{len(saved)} turns; text-side ms saved: p50 {median(saved):.0f}, "
            f"max {max(saved):.0f}, min {min(saved):.0f}"
        )
    log(f"\nwrote {log.path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, help="server log with first-cut lines")
    main(parser.parse_args().log)
