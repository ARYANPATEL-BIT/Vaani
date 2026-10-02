"""Time to first token for each provider ALONE, on real assembled prompts.

Each provider in config.toml's provider_order gets its own one-provider chain
(so no failover blurs the number), built by the same build_chain the server
uses. Every request is a real assembled prompt: the default persona's system
prompt + a two-exchange Hinglish history + a Hinglish question, through
persona.assemble, exactly what reply.py sends.

Timed: request start -> first text chunk. The stream is then cancelled, so
each measured call costs one short request. One untimed warm-up call per
provider opens its connection first: the server keeps its HTTP clients open
between turns, so the warm number is what a user's turn sees. The cold call
is printed too.

Rounds alternate which provider goes first, so neither is always measured
right after the other (a slow network minute then hits both alike).

Costs (rounds + 1) x providers paid requests, counted against the cap.

    uv run python scripts/measure_llm.py            # 10 rounds
    uv run python scripts/measure_llm.py --rounds 20
"""

import argparse
import asyncio
import math
from contextlib import aclosing
from statistics import median
from time import perf_counter

from vaani.config import get_settings
from vaani.persona import assemble
from vaani.providers.base import LLMProvider, Message
from vaani.providers.chain import build_chain
from vaani.spend import RequestCap

HISTORY = [
    Message("user", "namaste, main Pune se bol raha hoon"),
    Message("assistant", "Namaste! Pune mein aaj mausam kaisa hai?"),
    Message("user", "thoda garam hai, aur traffic bhi bahut hai"),
    Message("assistant", "Haan, garmi aur traffic dono thakaa dete hain."),
]
QUESTIONS = [
    "kal subah 8 baje ki meeting ke liye mujhe kab nikalna chahiye?",
    "ek simple dal recipe batao jo 20 minute mein ban jaaye",
    "mujhe neend nahi aati, koi tip do",
    "Python seekhna shuru karun toh kahan se karun?",
    "weekend pe Lonavala jaana theek rahega kya?",
    "mere laptop ki battery jaldi khatam ho jaati hai, kya karun?",
    "ek achhi book suggest karo jo ek din mein padh sakun",
    "interview ke liye confidence kaise badhaun?",
    "chai zyada peena theek hai ya nahi?",
    "bachchon ko maths mein interest kaise dilayein?",
]


def p95(values: list[float]) -> float:
    """Nearest-rank p95, as telemetry.py computes it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


async def first_token_ms(
    chain: LLMProvider, messages: list[Message]
) -> tuple[float, str]:
    """Request -> first chunk in ms, and the model that answered."""
    cancel = asyncio.Event()
    started = perf_counter()
    async with aclosing(chain.stream(messages, cancel)) as chunks:
        async for chunk in chunks:
            elapsed = (perf_counter() - started) * 1000
            cancel.set()  # one token is all we time; close the stream
            return elapsed, chunk.model or "?"
    raise RuntimeError("stream ended without any text")


async def main(rounds: int) -> None:
    settings = get_settings()
    cap = RequestCap(settings.llm.max_requests_per_process)
    system = settings.personas["default"]
    names = settings.llm.provider_order
    chains = {
        name: build_chain(
            settings.model_copy(
                update={
                    "llm": settings.llm.model_copy(update={"provider_order": [name]})
                }
            ),
            cap,
        )
        for name in names
    }
    warm_up = assemble(system, HISTORY, "namaste")
    for name, chain in chains.items():
        cold, model = await first_token_ms(chain, warm_up)
        print(f"{name}: cold first call {cold:.0f} ms (model {model})")

    times: dict[str, list[float]] = {name: [] for name in names}
    for i in range(rounds):
        messages = assemble(system, HISTORY, QUESTIONS[i % len(QUESTIONS)])
        order = names if i % 2 == 0 else list(reversed(names))
        for name in order:
            ms, _ = await first_token_ms(chains[name], messages)
            times[name].append(ms)
            print(f"round {i + 1:2d} {name:7s} {ms:6.0f} ms")

    print(f"\nwarm first token over {rounds} real prompts:")
    for name, values in times.items():
        print(
            f"  {name:7s} p50 {median(values):6.0f} ms   p95 {p95(values):6.0f} ms"
            f"   min {min(values):.0f}  max {max(values):.0f}"
        )
    print(f"paid requests used: {cap.used}/{cap.limit}")
    for chain in chains.values():
        await chain.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=10)
    asyncio.run(main(parser.parse_args().rounds))
