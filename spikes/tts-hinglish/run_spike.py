#!/usr/bin/env python3
"""
spikes/tts-hinglish/run_spike.py
----------------------------------
Week 1 Friday Spike — master runner.

Runs both Sarvam and Piper tests in sequence and prints a summary.

Usage:
    SARVAM_API_KEY=<key> python run_spike.py

Or with the key in backend/.env.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(script: str) -> int:
    """Run a spike sub-script and return its exit code."""
    print(f"\n{'=' * 60}")
    print(f"Running: {script}")
    print("=" * 60)
    result = subprocess.run([sys.executable, script], cwd=HERE)
    return result.returncode


def main() -> None:
    failures = []

    for script in ["generate_sarvam.py", "generate_piper.py"]:
        code = run(HERE / script)
        if code != 0:
            failures.append(script)

    print(f"\n{'=' * 60}")
    print("SPIKE SUMMARY")
    print("=" * 60)
    if failures:
        print(f"FAILED: {failures}")
        sys.exit(1)
    else:
        print("All scripts completed successfully.")
        print("Audio clips saved to: spikes/tts-hinglish/audio/")
        print("Run logs  saved to:   spikes/tts-hinglish/results/")


if __name__ == "__main__":
    main()
