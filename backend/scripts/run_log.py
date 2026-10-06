"""A measurement run's output, printed AND kept as a plain-text file.

Every number quoted in a learning doc or a finding must point to a file, so
measure_tts.py and measure_turn.py write everything they print to
docs/findings/tts-day12/<script>_<YYYYMMDD-HHMMSS>.txt. One file per run,
never overwritten: a number quoted from a run keeps pointing at that run.

Each line is appended as it is printed, so a run that crashes half-way still
leaves what it measured up to that point.
"""

import platform
import subprocess
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "findings" / "tts-day12"


def _commit() -> str:
    """The short git commit the code was measured at ("unknown" outside git)."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class RunLog:
    """Call it like print(): the line goes to the terminal and to the file."""

    def __init__(self, script: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        started = datetime.now()
        self.path = OUT / f"{script}_{started:%Y%m%d-%H%M%S}.txt"
        self(f"{script} run at {started:%Y-%m-%d %H:%M:%S}")
        self(f"commit {_commit()}, {platform.platform()}, {platform.processor()}")

    def __call__(self, line: str = "") -> None:
        print(line)
        # utf-8, "\n" line endings, no BOM: the same bytes on every OS.
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
