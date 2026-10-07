"""A measurement run's output, printed AND kept as a plain-text file.

Every number quoted in a learning doc or a finding must point to a file, so
measure_tts.py and measure_turn.py write everything they print to
docs/findings/reply-script/<script>_<YYYYMMDD-HHMMSS>.txt. One file per run,
never overwritten: a number quoted from a run keeps pointing at that run.
Day 14's tuning scripts pass `out=TUNING` to write to docs/findings/tuning/.
docs/findings/tts-day12/ is frozen: it is the evidence for the day 12
listening verdict, so nothing writes there any more.

The file gets the text as it is (UTF-8). The console gets it with every
non-ASCII character escaped as a backslash code: the Windows console's code
page cannot be trusted to print Devanagari, and a print that raises would
end the run.

Each line is appended as it is printed, so a run that crashes half-way still
leaves what it measured up to that point.
"""

import platform
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "docs" / "findings" / "reply-script"
TUNING = REPO / "docs" / "findings" / "tuning"


def _commit() -> str:
    """The short git commit the code was measured at ("unknown" outside git).

    Marked "+ uncommitted changes" when the working tree differs from it, so
    a run file never claims a commit that is not exactly what ran.
    """
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        suffix = " + uncommitted changes" if dirty.stdout.strip() else ""
        return done.stdout.strip() + suffix
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _power_scheme() -> str:
    """The active Windows power scheme's name, e.g. "Performance" or "Silent".

    Day 14 found Piper 10-20x slower under the laptop's "Silent" scheme, so
    no timing exists without its power mode. "unknown" off Windows or if
    powercfg fails. Read from powercfg's last "(...)", which is the name.
    """
    try:
        done = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True,
            check=True,
        )
        line = done.stdout.strip()
        return line[line.rindex("(") + 1 : line.rindex(")")]
    except (OSError, subprocess.CalledProcessError, ValueError):
        return "unknown"


class RunLog:
    """Call it like print(): the line goes to the terminal and to the file."""

    def __init__(self, script: str, out: Path = OUT) -> None:
        out.mkdir(parents=True, exist_ok=True)
        started = datetime.now()
        # Also used by a script for the other files it writes (WAVs), so one
        # run's files share a name and a new run never overwrites an old one.
        self.stamp = f"{started:%Y%m%d-%H%M%S}"
        self.path = out / f"{script}_{self.stamp}.txt"
        self(f"{script} run at {started:%Y-%m-%d %H:%M:%S}")
        self(f"commit {_commit()}, {platform.platform()}, {platform.processor()}")
        self(f"power scheme {_power_scheme()}")

    def __call__(self, line: str = "") -> None:
        print(line.encode("ascii", "backslashreplace").decode("ascii"))
        # utf-8, "\n" line endings, no BOM: the same bytes on every OS.
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
