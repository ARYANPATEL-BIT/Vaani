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

Rounds rotate which provider goes first, so none is always measured right
after another (a slow network minute then hits them all alike).

--groq-model ID:EFFORT (repeatable) replaces config.toml's one Groq model
with several, each measured as its own contestant against the same prompts,
so two candidate models can be compared before one goes into config. EFFORT
is sent as reasoning_effort; include_reasoning comes from config.toml.

Costs (rounds + 1) x contestants paid requests, counted against the cap.
Everything printed is also written to docs/findings/llm-latency/
measure_llm_<timestamp>.txt (run_log.py), with the commit and power scheme.

    uv run python scripts/measure_llm.py            # 10 rounds
    uv run python scripts/measure_llm.py --rounds 20
    uv run python scripts/measure_llm.py --groq-model openai/gpt-oss-20b:low \\
        --groq-model qwen/qwen3.8-27b:none
"""

import argparse
import asyncio
import math
from contextlib import aclosing
from statistics import median
from time import perf_counter

from run_log import REPO, RunLog  # scripts/ is on sys.path when run as a file

from vaani.config import Settings, get_settings
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


def alone(settings: Settings, name: str, groq: dict | None = None) -> Settings:
    """Settings whose chain is just `name`, with `groq` fields overridden."""
    llm = settings.llm.model_copy(update={"provider_order": [name]})
    if groq:
        llm = llm.model_copy(update={"groq": llm.groq.model_copy(update=groq)})
    return settings.model_copy(update={"llm": llm})


async def main(rounds: int, groq_models: list[str]) -> None:
    log = RunLog("measure_llm", REPO / "docs" / "findings" / "llm-latency")
    settings = get_settings()
    cap = RequestCap(settings.llm.max_requests_per_process)
    system = settings.personas["default"]
    # Contestant label -> its own one-provider chain.
    chains: dict[str, LLMProvider] = {}
    for name in settings.llm.provider_order:
        if name == "groq" and groq_models:
            for spec in groq_models:
                model, effort = spec.rsplit(":", 1)
                update = {"model": model, "reasoning_effort": effort}
                chains[model] = build_chain(alone(settings, name, update), cap)
        else:
            chains[name] = build_chain(alone(settings, name), cap)
    names = list(chains)
    log(f"contestants: {', '.join(names)}; {rounds} timed rounds + 1 warm-up each")
    log(f"groq include_reasoning (config.toml): {settings.llm.groq.include_reasoning}")
    for spec in groq_models:
        log(f"groq reasoning_effort: {spec}")

    warm_up = assemble(system, HISTORY, "namaste")
    for name, chain in chains.items():
        cold, model = await first_token_ms(chain, warm_up)
        log(f"{name}: cold first call {cold:.0f} ms (model {model})")

    times: dict[str, list[float]] = {name: [] for name in names}
    for i in range(rounds):
        messages = assemble(system, HISTORY, QUESTIONS[i % len(QUESTIONS)])
        # Rotate who goes first: round 0 a,b,c; round 1 b,c,a; round 2 c,a,b.
        shift = i % len(names)
        for name in names[shift:] + names[:shift]:
            ms, _ = await first_token_ms(chains[name], messages)
            times[name].append(ms)
            log(f"round {i + 1:2d} {name:20s} {ms:6.0f} ms")

    log(f"\nwarm first token over {rounds} real prompts:")
    for name, values in times.items():
        log(
            f"  {name:20s} p50 {median(values):6.0f} ms   p95 {p95(values):6.0f} ms"
            f"   min {min(values):.0f}  max {max(values):.0f}"
        )
    log(f"paid requests used: {cap.used}/{cap.limit}")
    for chain in chains.values():
        await chain.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument(
        "--groq-model", action="append", default=[], metavar="ID:EFFORT"
    )
    args = parser.parse_args()
    asyncio.run(main(args.rounds, args.groq_model))
