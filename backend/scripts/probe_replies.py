"""Ask every persona a fixed set of probe questions and save the replies for a
person to judge.

Each probe is one question to one persona, asked through ask.py's own ask():
the persona's system prompt and the question, no history. So one probe is
exactly one paid request. The probe set is a UTF-8 TSV with the columns
id, persona, problem, lang, gemini, question (the first set:
docs/findings/guardrails/probes_20261014.tsv).

    uv run python scripts/probe_replies.py --provider groq --round before
    uv run python scripts/probe_replies.py --provider gemini --round before \\
        --interval-s 15

--provider    groq or gemini. The OTHER provider is ask.py's local 429 mock
              (--simulate-429), so a failure can never fail over into a
              request nobody planned. gemini runs only the rows marked "y".
--round       a label for the file name, e.g. before or after.
--interval-s  seconds from one request's start to the next (default 12):
              keeps a run under Groq's 8000 tokens a minute. If Groq says
              fewer than 2000 tokens are left, the run waits another 60 s.

The run stops at the first failed request (a 429 included) and keeps what it
has. It writes probe_<round>_<provider>_<time>.txt next to the probe set:
each reply in full (UTF-8), ask.py's checks, the counts below and an empty
"mark:" line, then a summary. ask.py's --save adds a .tsv of the same name.
The console gets ASCII only: progress lines and the file's path.

The counts are code checks that point at replies to read, not verdicts.
"""

import argparse
import asyncio
import io
import logging
import re
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from statistics import median

from ask import ask  # this script's folder is on sys.path, so ask.py imports

from vaani.config import get_settings
from vaani.language import latin_words, reply_language
from vaani.telemetry import _nearest_rank_p95  # the project's one p95 rule

ROOT = Path(__file__).resolve().parents[2]  # the repository
DEFAULT_PROBES = ROOT / "docs/findings/guardrails/probes_20261014.tsv"

# The word ends here: no Devanagari letter or vowel sign follows (as ask.py).
_END = r"(?![ऀ-ॣॱ-ॿ])"
# Pronouns only, not verb forms: the आप register against तुम / तू.
AAP = re.compile(rf"आप(?:का|की|के|को|से|ने)?{_END}")
TUM = re.compile(rf"(?:तुम(?:्हारा|्हारी|्हारे|्हें|से|को|ने)?|तू|तेरा|तेरी|तेरे|तुझे){_END}")
# "I can't": नहीं (कर) सकती, असमर्थ, and the English phrasings.
CANT = re.compile(
    r"नहीं\s+(?:\S+\s+)?सक|असमर्थ|can't|cannot|unable|not able|don't have access",
    re.IGNORECASE,
)
# A first-person promise: the -ऊँगा / -ऊँगी future, "I will", "I've set".
PROMISE = re.compile(
    rf"[ूऊ][ँं]ग[ाी]{_END}"
    r"|\bI(?:'ll| will)\b|\bI(?:'ve| have) (?:set|sent|booked|added|noted)",
    re.IGNORECASE,
)
WORD = re.compile(r"[^\s,।.?!;:\"']+")
COPY_RUN = 6  # this many of the example's words in a row count as a copy
TTFT = re.compile(r"time to first token: (\d+) ms")
# From httpcore's response-header log line: (b'x-ratelimit-...', b'7324').
RATE = re.compile(r"x-ratelimit-(remaining-tokens|remaining-requests)', b'(\d+)", re.I)
REPORT = ("model:", "time to", "script:", "language:", "first person:", "self-name:")


def longest_run(a: list[str], b: list[str]) -> int:
    """The most words in a row that `a` and `b` share, in the same order."""
    best, prev = 0, [0] * (len(b) + 1)
    for x in a:
        cur = [0] + [prev[j] + 1 if x == y else 0 for j, y in enumerate(b)]
        best, prev = max(best, *cur), cur
    return best


def example_words(prompt: str) -> list[str]:
    """The words of the prompt's "Example: ..." sentence, up to its danda."""
    found = re.search(r"Example: (.+?।)", prompt)
    return WORD.findall(found.group(1)) if found else []


def counts(reply: str, report: list[str], example: list[str]) -> dict:
    """The code counts for one reply (report: ask.py's check lines)."""
    hindi = reply_language(reply) == "hi"
    return {
        "hindi": hindi,
        "named": not any("not a role: none" in ln for ln in report),
        "latin": latin_words(reply) if hindi else [],
        "aap": len(AAP.findall(reply)),
        "tum": len(TUM.findall(reply)),
        "cant": len(CANT.findall(reply)),
        "promise": len(PROMISE.findall(reply)),
        "run": longest_run(WORD.findall(reply), example),
    }


def run_one(question: str, persona: str, other: str, tsv: Path, logs) -> tuple:
    """(exit code, ask.py's report lines, log text) for one probe."""
    out, log = io.StringIO(), io.StringIO()
    logs.setStream(log)
    with redirect_stdout(out), redirect_stderr(out):
        code = asyncio.run(ask(question, False, other, None, persona, tsv))
    keep = (*REPORT, "error:")
    report = [ln for ln in out.getvalue().splitlines() if ln.startswith(keep)]
    return code, report, log.getvalue()


def block(pid, persona, problem, lang, question, reply, notes, c, rate, size):
    """One probe's entry in the run file."""
    return (
        f"[{pid}] {persona} | {problem} | {lang}\nQ: {question}\nA: {reply}\n"
        + "".join(f"  {ln}\n" for ln in notes)
        + f"  latin words in a Devanagari reply: {' '.join(c['latin']) or '-'}\n"
        f"  aap-family words {c['aap']}, tum/tu-family words {c['tum']}\n"
        f"  can't markers {c['cant']}, promise markers {c['promise']}\n"
        f"  example sentence: {c['run']} of its {size} words in a row"
        f"{' (COPY)' if c['run'] >= COPY_RUN else ''}\n"
        f"  tokens left {rate.get('remaining-tokens', '-')}, "
        f"requests left {rate.get('remaining-requests', '-')}\n  mark:\n\n"
    )


def summary(results: list[dict], personas) -> list[str]:
    """One line of counts per persona, for the end of the run file."""
    lines = []
    for p in personas:
        mine = [r for r in results if r["persona"] == p]

        # mine is bound as a default: each persona's n() counts its own replies.
        def n(test, mine=mine) -> int:
            return sum(1 for r in mine if test(r))

        lines.append(
            f"  {p}: {len(mine)} replies, {n(lambda r: r['hindi'])} in Devanagari"
            f"; Devanagari with Latin words {n(lambda r: r['latin'])}"
            f"; with tum/tu words {n(lambda r: r['tum'])}"
            f", with both aap and tum/tu {n(lambda r: r['tum'] and r['aap'])}"
            f"; English probes answered in Devanagari "
            f"{n(lambda r: r['lang'] == 'en' and r['hindi'])} of "
            f"{n(lambda r: r['lang'] == 'en')}"
            f"; example copies {n(lambda r: r['run'] >= COPY_RUN)}"
            f"; self-name not a role {n(lambda r: r['named'])}\n"
        )
    return lines


def git_state() -> str:
    def git(*cmd: str) -> str:
        return subprocess.run(["git", *cmd], capture_output=True, text=True).stdout

    dirty = " + uncommitted changes" if git("status", "--porcelain").strip() else ""
    return f"commit {git('rev-parse', '--short', 'HEAD').strip()}{dirty}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=("groq", "gemini"), required=True)
    parser.add_argument("--round", required=True, help="file name label")
    parser.add_argument("--interval-s", type=float, default=12.0)
    parser.add_argument("--probes", type=Path, default=DEFAULT_PROBES)
    args = parser.parse_args()

    settings = get_settings()
    other = "gemini" if args.provider == "groq" else "groq"
    lines = args.probes.read_text(encoding="utf-8").splitlines()[1:]
    rows = [ln.split("\t") for ln in lines if ln]
    rows = [r for r in rows if args.provider == "groq" or r[4] == "y"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = args.probes.parent / f"probe_{args.round}_{args.provider}_{stamp}.txt"
    tsv = path.with_suffix(".tsv")
    examples = {p: example_words(settings.personas[p]) for p in settings.personas}

    # Every log record goes to one handler whose stream is swapped per probe.
    # httpcore at DEBUG logs the response headers (never our request headers,
    # so never the key); only the x-ratelimit numbers are kept from it.
    logs = logging.StreamHandler(io.StringIO())
    logging.basicConfig(level=logging.WARNING, handlers=[logs])
    logging.getLogger("httpcore").setLevel(logging.DEBUG)

    f = path.open("w", encoding="utf-8", newline="\n")
    f.write(
        f"probe_replies.py --provider {args.provider} --round {args.round}, "
        f"run at {stamp}\n{git_state()}\n"
        f"model {getattr(settings.llm, args.provider).model}; {other} is the "
        f"local 429 mock, so 0 {other} requests\n"
        f"probes {args.probes.name}: {len(rows)} rows; one request each, "
        f"{args.interval_s:.0f} s apart; no history, persona prompt + question\n"
        f"counts are code checks, not verdicts; a copy is >= {COPY_RUN} words "
        f"in a row of the persona's example sentence\nexample sentences:\n"
    )
    f.writelines(f"  {p}: {' '.join(w)}\n" for p, w in examples.items())
    f.write("Mark each reply: clean or broken.\n\n")

    ttfts, results = [], []
    next_at = time.monotonic()
    for i, (pid, persona, problem, lang, _, question) in enumerate(rows, 1):
        time.sleep(max(0.0, next_at - time.monotonic()))
        next_at = time.monotonic() + args.interval_s
        sent = datetime.now().strftime("%H:%M:%S")  # time of day, for a timeout
        code, report, log = run_one(question, persona, other, tsv, logs)
        rate = dict(RATE.findall(log))
        reply = ""
        if code == 0:  # ask.py appended "question<TAB>reply" to the .tsv
            reply = tsv.read_text(encoding="utf-8").splitlines()[-1].split("\t")[1]
        c = counts(reply, report, examples[persona])
        warnings = [ln for ln in log.splitlines() if not ln.startswith("DEBUG:")]
        notes, size = [f"sent at {sent}", *report, *warnings], len(examples[persona])
        f.write(
            block(pid, persona, problem, lang, question, reply, notes, c, rate, size)
        )
        f.flush()  # a stopped run keeps every probe answered so far
        ttft = TTFT.search("\n".join(report))
        if ttft:
            ttfts.append(int(ttft.group(1)))
        ms = ttft.group(1) if ttft else "-"
        print(f"[{i}/{len(rows)}] {persona} {pid} exit {code} ttft {ms} ms")
        if code != 0:
            print("stopping: the request failed (see the file)")
            break
        results.append({"persona": persona, "lang": lang, **c})
        if int(rate.get("remaining-tokens", 8000)) < 2000:
            print("fewer than 2000 tokens left: waiting 60 s more")
            next_at += 60

    f.write(f"SUMMARY: {len(results)} of {len(rows)} probes answered\n")
    if ttfts:
        ttfts.sort()
        f.write(
            f"  time to first token n={len(ttfts)} p50 {median(ttfts):.0f} "
            f"p95 {_nearest_rank_p95(ttfts):.0f} max {ttfts[-1]} ms\n"
        )
    f.writelines(summary(results, examples))
    f.close()
    print(f"wrote {path.as_posix()}")
    return 0 if len(results) == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
