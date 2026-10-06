"""Ask the configured language model chain one question and print the answer as
it streams in, so streaming, failover and cancellation are visible rather than
assumed.

Goes through ProviderChain, in config.toml's [llm] provider_order. Every
provider listed there needs its key in the environment or backend/.env
(VAANI_GEMINI_API_KEY, VAANI_GROQ_API_KEY).

    uv run python scripts/ask.py "Explain how a bicycle stays upright."
    uv run python scripts/ask.py --timings "Explain how a bicycle stays upright."
    uv run python scripts/ask.py --simulate-429 gemini "Why is the sky blue?"
    uv run python scripts/ask.py --cancel-after-ms 800 "Tell me a long story."
    uv run python scripts/ask.py --persona default --save replies.tsv "kal ka mausam?"

--timings        prefix every chunk with its arrival time, e.g. [+412ms].
--simulate-429   make the named provider answer HTTP 429 without touching the
                 network, to watch the chain fail over to the next one.
--cancel-after-ms  set the cancellation token N ms after sending, and report
                 how quickly the stream stopped. httpcore's log is shown: a
                 read that "failed exception=CancelledError()" followed by
                 "response_closed" means the response was abandoned unfinished,
                 and httpcore closes the socket in that case (it cannot reuse a
                 half-read connection). tests/test_streaming.py proves the close
                 from the server's side of a real socket.
--persona        send config.toml's system prompt for that persona first, built
                 by the same persona.assemble() the server uses (no history).
                 Without it the question goes alone, with no system prompt.
--save           append "question<TAB>reply" to FILE as UTF-8, one line per run.

After the answer, a "script:" line counts the reply's characters IN CODE:
Devanagari, Latin letters, and anything else. Under the Devanagari reply
format any Latin letter is drift. The console only ever gets ASCII: the reply
is printed with non-ASCII escaped (the Windows console cannot be trusted with
Devanagari); --save keeps the real text.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from time import perf_counter

import httpx

from vaani.config import get_settings
from vaani.persona import assemble
from vaani.providers.base import Message, ProviderError
from vaani.providers.chain import build_chain
from vaani.spend import RequestCap, SpendCapExceededError

# Punctuation a Devanagari reply may use besides the danda (which is inside
# the Devanagari block). Anything else that is not a letter or digit is "other".
PUNCTUATION = set(",.?!;:'\"()-")


def ascii_only(text: str) -> str:
    """Non-ASCII escaped as backslash codes, safe for any console."""
    return text.encode("ascii", "backslashreplace").decode("ascii")


def script_counts(text: str) -> tuple[int, int, str]:
    """(Devanagari characters, Latin letters, every other unexpected one)."""
    devanagari = latin = 0
    other = ""
    for c in text:
        if 0x0900 <= ord(c) <= 0x097F:  # the Devanagari Unicode block
            devanagari += 1
        elif c.isascii() and c.isalpha():
            latin += 1
        elif not (c.isspace() or (c.isascii() and c.isdigit()) or c in PUNCTUATION):
            other += c
    return devanagari, latin, other


def _always_429(request: httpx.Request) -> httpx.Response:
    body = {"error": {"message": "simulated by ask.py", "type": "rate_limit"}}
    return httpx.Response(429, json=body)


async def ask(
    question: str,
    timings: bool,
    simulate_429: str | None,
    cancel_after_ms: int | None,
    persona: str | None,
    save: Path | None,
) -> int:
    settings = get_settings()
    messages = [Message("user", question)]
    if persona is not None:
        messages = assemble(settings.personas[persona], [], question)
    cap = RequestCap(settings.llm.max_requests_per_process)
    clients = {}
    if simulate_429:
        clients[simulate_429] = httpx.AsyncClient(
            transport=httpx.MockTransport(_always_429)
        )
    try:
        chain = build_chain(settings, cap, clients)
    except (ProviderError, ValueError) as exc:  # missing key, unknown provider
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    cancel = asyncio.Event()
    start = perf_counter()
    cancelled_at: float | None = None
    if cancel_after_ms is not None:

        def fire() -> None:
            nonlocal cancelled_at
            cancelled_at = perf_counter()
            cancel.set()

        asyncio.get_running_loop().call_later(cancel_after_ms / 1000, fire)

    first_at: float | None = None
    answered_by: str | None = None
    reply = ""
    try:
        async for chunk in chain.stream(messages, cancel):
            now = perf_counter()
            if first_at is None:
                first_at, answered_by = now, chunk.model
            if timings:
                print(f"[+{(now - start) * 1000:.0f}ms]", end="")
            # flush=True: without it Python buffers stdout and the text would
            # appear in bursts, hiding the very streaming we want to see.
            print(ascii_only(chunk.text), end="", flush=True)
            reply += chunk.text
    except (ProviderError, SpendCapExceededError) as exc:
        print(f"\nerror: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await chain.aclose()

    ended = perf_counter()
    print()
    if save is not None and reply:
        # One line per reply: newlines inside the reply become spaces.
        with save.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"{question}\t{' '.join(reply.split())}\n")
    if cancelled_at is not None:
        print(
            f"\n[cancelled at +{(cancelled_at - start) * 1000:.0f} ms; stream ended "
            f"{(ended - cancelled_at) * 1000:.1f} ms after the token was set]",
            file=sys.stderr,
        )
    if first_at is None:
        print("(no text returned)", file=sys.stderr)
        return 0 if cancelled_at is not None else 1
    print(
        f"\nmodel: {answered_by or 'not reported'} "
        f"(chain order: {', '.join(settings.llm.provider_order)})\n"
        f"time to first token: {(first_at - start) * 1000:.0f} ms, "
        f"total: {(ended - start) * 1000:.0f} ms",
        file=sys.stderr,
    )
    devanagari, latin, other = script_counts(reply)
    print(
        f"script: {devanagari} Devanagari, {latin} Latin letters, "
        f"other: {ascii_only(other) or 'none'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="+", help="the question to ask")
    parser.add_argument(
        "--timings", action="store_true", help="show each chunk's arrival time"
    )
    parser.add_argument(
        "--simulate-429", metavar="PROVIDER", help="make PROVIDER answer HTTP 429"
    )
    parser.add_argument(
        "--cancel-after-ms", type=int, metavar="N", help="cancel N ms after sending"
    )
    parser.add_argument("--persona", metavar="KEY", help="config.toml persona key")
    parser.add_argument("--save", type=Path, metavar="FILE", help="append the reply")
    args = parser.parse_args()
    # Failover warnings go to stderr, so they show between the answer's lines.
    logging.basicConfig(level=logging.WARNING, format="[%(name)s] %(message)s")
    if args.cancel_after_ms is not None:
        # httpcore logs each step of the request. Its lines name events and
        # response headers only; never OUR request headers (the API key).
        logging.getLogger("httpcore").setLevel(logging.DEBUG)
    sys.exit(
        asyncio.run(
            ask(
                " ".join(args.question),
                args.timings,
                args.simulate_429,
                args.cancel_after_ms,
                args.persona,
                args.save,
            )
        )
    )
