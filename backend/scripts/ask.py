"""Ask the configured language model one question and print the answer as it
streams in, so streaming is visible rather than assumed.

Uses the first provider in config.toml's [llm] provider_order (only "gemini"
exists today). The API key must be in the environment as VAANI_GEMINI_API_KEY
or in backend/.env.

    uv run python scripts/ask.py "Explain how a bicycle stays upright."
    uv run python scripts/ask.py --timings "Explain how a bicycle stays upright."

--timings prefixes every chunk with its arrival time, e.g. [+412ms], so you can
see the chunks arriving spread out over time rather than all at once. After the
answer, the script prints the model that ACTUALLY answered (Gemini reports it
per chunk) next to the one we asked for, plus time-to-first-token.
"""

import argparse
import asyncio
import sys
from time import perf_counter

from vaani.config import get_settings
from vaani.providers.base import Message, ProviderError
from vaani.providers.gemini import GeminiProvider
from vaani.spend import RequestCap, SpendCapExceededError


async def ask(question: str, timings: bool) -> int:
    settings = get_settings()
    name = settings.llm.provider_order[0]
    if name != "gemini":
        print(f"ask.py only knows 'gemini'; config asks for '{name}'", file=sys.stderr)
        return 2
    if settings.gemini_api_key is None:
        print("VAANI_GEMINI_API_KEY is not set (env or backend/.env)", file=sys.stderr)
        return 2

    cap = RequestCap(settings.llm.max_requests_per_process)
    try:
        provider = GeminiProvider(settings.llm.gemini, settings.gemini_api_key, cap)
    except ProviderError as exc:  # e.g. an empty key
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    # Never set here; the provider still takes it, as every caller must.
    cancel = asyncio.Event()

    start = perf_counter()
    first_at: float | None = None
    answered_by: str | None = None
    try:
        async for chunk in provider.stream([Message("user", question)], cancel):
            now = perf_counter()
            if first_at is None:
                first_at, answered_by = now, chunk.model
            if timings:
                print(f"[+{(now - start) * 1000:.0f}ms]", end="")
            # flush=True: without it Python buffers stdout and the text would
            # appear in bursts, hiding the very streaming we want to see.
            print(chunk.text, end="", flush=True)
    except (ProviderError, SpendCapExceededError) as exc:
        print(f"\nerror: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await provider.aclose()

    total_ms = (perf_counter() - start) * 1000
    print()
    if first_at is None:
        print("(no text returned)", file=sys.stderr)
        return 1
    print(
        f"\nmodel: {answered_by or 'not reported'} "
        f"(asked for {settings.llm.gemini.model})\n"
        f"time to first token: {(first_at - start) * 1000:.0f} ms, "
        f"total: {total_ms:.0f} ms",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="+", help="the question to ask")
    parser.add_argument(
        "--timings", action="store_true", help="show each chunk's arrival time"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(ask(" ".join(args.question), args.timings)))
