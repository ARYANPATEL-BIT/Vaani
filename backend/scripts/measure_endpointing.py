"""Measure endpointing dead air: last audible word -> turn_ended.

For each WAV (16 kHz mono 16-bit): 0.5 s silence, the clip with its all-zero
lead-in and tail stripped, then 3 s silence. The frames go through the real
VadStream and Endpointer, exactly as the gateway calls them.

Ground truth: the "last audible frame" is the last frame of the clip whose
loudness is above AUDIBLE_DBFS. We know it because we made the audio. The
delay is then counted in frames (x 20 ms), which is exact and does not depend
on how fast this script runs. In the live gateway frames arrive in real time,
so frame time IS wall time, plus the few microseconds of compute measured
separately below.

The delay splits into two parts:
  vad   last audible frame -> speech_ended  (VAD's end_frames + model fall-off)
  wait  speech_ended -> turn_ended          (end_of_turn_silence_ms)

Run from backend/:
    uv run python scripts/measure_endpointing.py tests/fixtures/speech_16k_mono.wav
    uv run python scripts/measure_endpointing.py path/to/clips/*.wav
"""

import argparse
import math
import wave
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np

from vaani.config import get_settings
from vaani.endpoint import Endpointer
from vaani.gateway import expected_frame_bytes
from vaani.vad import SPEECH_ENDED, VadStream, load_model

# A frame quieter than this (RMS, relative to full scale) counts as inaudible.
# -50 dBFS is below normal room noise, so "last audible" errs late, which
# makes the reported delay err SHORT. Measurement choice, not a product value.
AUDIBLE_DBFS = -50.0


def load_frames(path: Path, frame_bytes: int) -> list[bytes]:
    with wave.open(str(path), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    frames = [
        pcm[i : i + frame_bytes]
        for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes)
    ]
    voiced = [i for i, f in enumerate(frames) if any(f)]
    return frames[voiced[0] : voiced[-1] + 1]


def dbfs(frame: bytes) -> float:
    samples = np.frombuffer(frame, dtype="<i2").astype(np.float64) / 32768.0
    rms = math.sqrt(float(np.mean(samples**2)))
    return 20 * math.log10(rms) if rms > 0 else -math.inf


def p95(values: list[float]) -> float:
    """Nearest-rank p95, as telemetry.py computes it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def measure(path: Path) -> tuple[int, int, int, list[float]] | None:
    """(delay_ms, vad_ms, wait_ms, per-push compute seconds) or None if no turn."""
    settings = get_settings()
    frame_ms = settings.audio.frame_ms
    frame_bytes = expected_frame_bytes(settings.audio)
    silence = b"\x00" * frame_bytes
    lead = round(500 / frame_ms)
    clip = load_frames(path, frame_bytes)
    frames = [silence] * lead + clip + [silence] * round(3000 / frame_ms)
    last_audible = lead + max(i for i, f in enumerate(clip) if dbfs(f) > AUDIBLE_DBFS)

    model = load_model(settings.vad.model_path, settings.vad.model_sha256)
    vad = VadStream(model, settings.vad, settings.audio)
    endpointer = Endpointer(settings.endpoint, frame_ms, settings.vad.threshold)
    costs: list[float] = []
    last_ended = None
    for i, frame in enumerate(frames):
        event = vad.push(frame)
        if event is not None and event.kind == SPEECH_ENDED:
            last_ended = event.frame_index
        started = perf_counter()
        turn = endpointer.push(frame, event, vad.probability)
        costs.append(perf_counter() - started)
        if turn is not None:
            assert last_ended is not None
            return (
                (i - last_audible) * frame_ms,
                (last_ended - last_audible) * frame_ms,
                (i - last_ended) * frame_ms,
                costs,
            )
    return None


def main(paths: list[Path]) -> None:
    delays, vad_parts, costs = [], [], []
    for path in paths:
        result = measure(path)
        if result is None:
            print(f"{path.name}: no turn_ended")
            continue
        delay, vad_part, wait, push_costs = result
        delays.append(delay)
        vad_parts.append(vad_part)
        costs.extend(push_costs)
        print(f"{path.name}: {delay} ms (vad {vad_part} + wait {wait})")
    if not delays:
        return
    budget = 1000
    print(f"\n{len(delays)} utterances, last audible frame -> turn_ended:")
    print(f"  p50 {median(delays):.0f} ms, p95 {p95(delays):.0f} ms")
    print(f"  of which VAD p50 {median(vad_parts):.0f} ms, p95 {p95(vad_parts):.0f} ms")
    print(f"  = {median(delays) / budget:.0%} of the {budget} ms budget at p50")
    print(
        f"  Endpointer.push compute: p50 {median(costs) * 1e6:.1f} us, "
        f"p95 {p95(costs) * 1e6:.1f} us over {len(costs)} frames"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wavs", nargs="+", type=Path, help="16 kHz mono 16-bit WAVs")
    main(parser.parse_args().wavs)
