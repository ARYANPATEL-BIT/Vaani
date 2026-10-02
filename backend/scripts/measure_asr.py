"""Measure speech recognition latency: turn_ended -> transcript.final, and partials.

For each WAV (16 kHz mono 16-bit, one utterance each), the clip is run through
the real VadStream and Endpointer exactly as the gateway does, so the audio
transcribed is the endpointer's utterance including its pre-roll. The final is
then requested through the real AsrRunner, timed from turn_ended to the moment
transcript.final is handed to the (stub) socket.

Partial cost: the longest clip is re-decoded at growing lengths (what a
sliding re-decode does), giving the cost of ONE re-decode at each length, and
the total decode work per utterance at each candidate partial interval.

The model comes from config.toml, overridable from the environment, e.g.
  VAANI_ASR__WHISPER__MODEL=large-v3 VAANI_ASR__WHISPER__DEVICE=cuda \
  VAANI_ASR__WHISPER__COMPUTE_TYPE=float16 uv run python scripts/measure_asr.py *.wav
"""

import argparse
import asyncio
import math
import wave
from pathlib import Path
from statistics import median
from time import perf_counter

from vaani.asr import build_recognizer
from vaani.asr.runner import AsrRunner
from vaani.config import get_settings
from vaani.endpoint import Endpointer, TurnEnded
from vaani.gateway import expected_frame_bytes
from vaani.telemetry import Telemetry
from vaani.vad import VadStream, load_model

# Day 9's measured dead air, last audible word -> turn_ended (09-endpointing.md).
ENDPOINTING_P50_MS = 980
BUDGET_MS = 1000
PARTIAL_INTERVALS_MS = (500, 1000, 1500)


def p95(values: list[float]) -> float:
    """Nearest-rank p95, as telemetry.py computes it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def load_frames(path: Path, frame_bytes: int) -> list[bytes]:
    with wave.open(str(path), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    return [pcm[i : i + frame_bytes] for i in range(0, len(pcm), frame_bytes)][:-1]


def endpoint(path: Path) -> TurnEnded | None:
    """The clip as the gateway would see it: lead silence, clip, tail silence."""
    settings = get_settings()
    frame_bytes = expected_frame_bytes(settings.audio)
    silence = b"\x00" * frame_bytes
    frames = [silence] * 25 + load_frames(path, frame_bytes) + [silence] * 150
    model = load_model(settings.vad.model_path, settings.vad.model_sha256)
    vad = VadStream(model, settings.vad, settings.audio)
    endpointer = Endpointer(settings.endpoint, settings.audio.frame_ms)
    for frame in frames:
        turn = endpointer.push(frame, vad.push(frame))
        if turn is not None:
            return turn
    return None


async def time_final(runner_parts, turn: TurnEnded) -> tuple[float, dict]:
    """turn_ended -> transcript.final through the real AsrRunner, in ms."""
    recognizer, cfg = runner_parts
    sent: list[tuple[float, dict]] = []

    async def send(msg: dict) -> None:
        sent.append((perf_counter(), msg))

    runner = AsrRunner(recognizer, cfg, send, Telemetry("measure"))
    ended_at = perf_counter()
    runner.request_final("t", turn.audio, turn.duration_ms, ended_at)
    while not sent:
        await asyncio.sleep(0.001)
    await runner.close()
    at, msg = sent[0]
    return (at - ended_at) * 1000, msg


async def decode_ms(recognizer, pcm: bytes) -> float:
    started = perf_counter()
    await recognizer.transcribe(pcm, asyncio.Event())
    return (perf_counter() - started) * 1000


async def main(paths: list[Path], repeat: int) -> None:
    settings = get_settings()
    w = settings.asr.whisper
    print(f"model {w.model} on {w.device}/{w.compute_type}, language={w.language}")
    recognizer = build_recognizer(settings.asr, settings.audio.sample_rate)
    parts = (recognizer, settings.asr)

    finals: list[float] = []
    turns: list[TurnEnded] = []
    for path in paths:
        turn = endpoint(path)
        if turn is None:
            print(f"{path.name}: no turn_ended")
            continue
        turns.append(turn)
        for _ in range(repeat):
            ms, msg = await time_final(parts, turn)
            finals.append(ms)
        print(f"{path.name}: {turn.duration_ms} ms speech, {ms:.0f} ms -> {msg}")
    if not finals:
        return
    print(f"\nturn_ended -> transcript.final over {len(finals)} runs:")
    print(f"  p50 {median(finals):.0f} ms, p95 {p95(finals):.0f} ms")

    # Partials: one re-decode at each length of the longest utterance.
    longest = max(turns, key=lambda t: len(t.audio))
    bytes_per_s = settings.audio.sample_rate * 2
    seconds = len(longest.audio) / bytes_per_s
    print(f"\nre-decode cost on the longest utterance ({seconds:.1f} s):")
    cost: dict[float, float] = {}
    # Every half second of audio, median of 3 decodes each.
    for length in [s / 2 for s in range(2, int(seconds * 2) + 1)]:
        prefix = longest.audio[: int(length * bytes_per_s)]
        cost[length] = median([await decode_ms(recognizer, prefix) for _ in range(3)])
        print(f"  {length:.1f} s of audio: {cost[length]:.0f} ms")
    for interval in PARTIAL_INTERVALS_MS:
        points = [k for k in cost if (k * 1000) % interval == 0]
        work = sum(cost[k] for k in points)
        late = [k for k in points if cost[k] > interval]
        print(
            f"  every {interval} ms: {len(points)} re-decodes, {work:.0f} ms of decode "
            f"work per {seconds:.1f} s utterance"
            + (f"; cannot keep up from {min(late):.1f} s" if late else "")
        )

    asr_p50 = median(finals)
    total = ENDPOINTING_P50_MS + asr_p50
    print(
        f"\nbudget: endpointing {ENDPOINTING_P50_MS} ms (day 9 p50) + ASR {asr_p50:.0f}"
        f" ms = {total:.0f} ms of {BUDGET_MS} ms; left for LLM + TTS + playback: "
        f"{BUDGET_MS - total:.0f} ms"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wavs", nargs="+", type=Path, help="16 kHz mono 16-bit WAVs")
    parser.add_argument("--repeat", type=int, default=1, help="runs per clip")
    args = parser.parse_args()
    asyncio.run(main(args.wavs, args.repeat))
