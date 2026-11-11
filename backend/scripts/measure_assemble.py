"""Cost of persona.assemble: building one reply's request, on the event loop.

reply.py calls assemble once per reply, between the transcript arriving and
the model request going out, so it sits on the conversation path. This times
it with each persona's real prompt and a full history (history_turns
exchanges), no network. protocol v0.10 added the reply-language line; for a
"before", run this on code without it: the script sees that assemble has no
reply_language parameter and calls it the old way.

Run from backend/ (ASCII output, also written to docs/findings/reply-language/):
    uv run python scripts/measure_assemble.py --label before
    uv run python scripts/measure_assemble.py --label after
"""

import argparse
import inspect
import subprocess
from datetime import datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from zoneinfo import ZoneInfo

from vaani.config import get_settings
from vaani.persona import assemble
from vaani.providers.base import Message

OUT = Path(__file__).resolve().parents[2] / "docs/findings/reply-language"
CALLS, RUNS = 100_000, 3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="before or after")
    label = parser.parse_args().label
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.llm.timezone))
    history = [
        Message(role, f"message {i}")
        for i in range(settings.llm.history_turns)
        for role in ("user", "assistant")
    ]
    has_param = "reply_language" in inspect.signature(assemble).parameters
    choices = ("any", "en", "hi") if has_param else (None,)
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    lines = [
        f"measure_assemble.py --label {label}, commit {commit}, "
        f"{CALLS} calls x {RUNS} runs, history {len(history)} messages",
        f"assemble has reply_language: {has_param}",
    ]
    for persona, prompt in settings.personas.items():
        for choice in choices:
            extra = () if choice is None else (choice,)
            per_call = []
            for _ in range(RUNS):
                began = perf_counter()
                for _ in range(CALLS):
                    messages = assemble(prompt, history, "kya haal hai", now, *extra)
                per_call.append((perf_counter() - began) / CALLS * 1e6)
            chars = len(messages[0].content)
            lines.append(
                f"{persona:8s} {choice or '-':4s} system {chars} chars, "
                f"median {median(per_call):.2f} us per call "
                f"(runs: {', '.join(f'{t:.2f}' for t in per_call)})"
            )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"assemble_cost_{label}_{stamp}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print(f"wrote {path.as_posix()}")


if __name__ == "__main__":
    main()
