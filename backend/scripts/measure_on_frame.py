"""Cost of TurnPipeline.on_frame: the per-frame work on the event loop.

Every mic frame (one per 20 ms) runs VAD, then endpointing or barge-in
judging, on the event loop. While it runs, every session on that loop waits,
so a change to this path needs a before/after (CLAUDE.md). Day 13 measured it
the same way: real Silero VAD, no recogniser, model or synthesiser (those run
as background tasks, not in on_frame), 2,800 frames, 3 runs per path.

Paths:
  idle silent  agent idle, all-zero frames (day 13's "idle path")
  idle speech  agent idle, the speech fixture then 1 s of silence, repeated:
               opens and ends turns, so endpointing does its real work
  busy silent  agent speaking, all-zero frames (day 13's "busy path")

For a "before", run it against another checkout of the code by putting that
checkout's backend/ first on PYTHONPATH; the first line printed names the
vaani package actually imported.

Run from backend/ (output also goes to docs/findings/tuning/):
    uv run python scripts/measure_on_frame.py
"""

import asyncio
import math
import wave
from pathlib import Path
from statistics import median
from time import perf_counter

from run_log import TUNING, RunLog  # scripts/ is on sys.path when run as a file

import vaani
from vaani.config import get_settings
from vaani.gateway import expected_frame_bytes
from vaani.protocol import TurnState
from vaani.session import Session
from vaani.telemetry import Telemetry
from vaani.turns import TurnPipeline
from vaani.vad import load_model

FRAMES = 2800
RUNS = 3
SPEECH_WAV = (
    Path(__file__).resolve().parent.parent / "tests/fixtures/speech_16k_mono.wav"
)


async def discard(_message) -> None:
    """Stands in for the socket's send: nothing is sent anywhere."""


def p95(values: list[float]) -> float:
    """Nearest-rank p95, as telemetry.py computes it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def frames_for(path_name: str) -> list[bytes]:
    settings = get_settings()
    frame_bytes = expected_frame_bytes(settings.audio)
    silence = b"\x00" * frame_bytes
    if path_name != "idle speech":
        return [silence] * FRAMES
    with wave.open(str(SPEECH_WAV), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    speech = [pcm[i : i + frame_bytes] for i in range(0, len(pcm), frame_bytes)][:-1]
    cycle = speech + [silence] * (1000 // settings.audio.frame_ms)
    return (cycle * (FRAMES // len(cycle) + 1))[:FRAMES]


async def one_run(path_name: str, frames: list[bytes]) -> list[float]:
    settings = get_settings()
    model = load_model(settings.vad.model_path, settings.vad.model_sha256)
    session = Session(session_id="bench", persona="default")
    pipeline = TurnPipeline(
        settings, session, Telemetry("bench"), discard, discard, model, None, None, None
    )
    if path_name == "busy silent":
        # Speaking with no reply behind it: fine for silent frames, which
        # never get as far as a barge-in.
        pipeline._machine.state = TurnState.SPEAKING
    costs = []
    for frame in frames:
        started = perf_counter()
        await pipeline.on_frame(frame)
        costs.append(perf_counter() - started)
    return costs


async def main() -> None:
    log = RunLog("measure_on_frame", out=TUNING)
    log(f"vaani imported from {Path(vaani.__file__).parent}")
    log(f"{FRAMES} frames x {RUNS} runs per path; on_frame p50 / p95 in us")
    for path_name in ("idle silent", "idle speech", "busy silent"):
        frames = frames_for(path_name)
        runs = [await one_run(path_name, frames) for _ in range(RUNS)]
        cells = ", ".join(f"{median(c) * 1e6:.1f} / {p95(c) * 1e6:.1f}" for c in runs)
        log(f"  {path_name:<12} {cells}")
    log(f"\nwrote {log.path.name}")


if __name__ == "__main__":
    asyncio.run(main())
