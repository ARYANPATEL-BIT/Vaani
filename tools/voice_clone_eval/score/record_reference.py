"""Record one reference take from the default microphone and report its level.

Usage (from tools/voice_clone_eval/score):
    uv run python record_reference.py a 12     # clip A, 12 seconds
    uv run python record_reference.py b 18     # clip B, 18 seconds

Reads the text from ../reference_script.txt (open it in an editor; the Hindi is
not printed here). Writes audio/reference/clip_<name>_take<N>.wav, never
overwriting an earlier take. Output is ASCII only.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

# 24 kHz mono 16-bit: the native output rate of all three candidate models, so
# no model has to upsample a lower-rate reference. Each resamples if it needs to.
SAMPLE_RATE = 24_000
AUDIO_DIR = Path(__file__).resolve().parents[1] / "audio" / "reference"

# Level guide in dBFS (decibels below digital full scale; 0 dBFS is the loudest
# value a 16-bit sample can hold). Peaks near 0 mean clipping, i.e. the wave's
# tops were cut off; peaks far below mean the voice is buried near the noise.
CLIP_DBFS = -1.0
QUIET_DBFS = -20.0


def next_take_path(name: str) -> Path:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    n = 1
    while (AUDIO_DIR / f"clip_{name}_take{n}.wav").exists():
        n += 1
    return AUDIO_DIR / f"clip_{name}_take{n}.wav"


def dbfs(x: float) -> float:
    return 20 * np.log10(max(x, 1e-9))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=["a", "b"])
    parser.add_argument("seconds", type=float)
    args = parser.parse_args()

    device = sd.query_devices(kind="input")["name"]
    print("Input device:", device.encode("ascii", "replace").decode())
    print(
        f"Recording clip {args.name.upper()} for {args.seconds:.0f} s. Start reading after GO."
    )
    for n in (3, 2, 1):
        print(f"  {n}...")
        time.sleep(1)
    print("GO")

    # sd.rec starts recording in the background; sd.wait blocks until done.
    audio = sd.rec(
        int(args.seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    print("STOP")

    samples = audio[:, 0].astype(np.float32) / 32768.0
    peak = dbfs(float(np.max(np.abs(samples))))
    rms = dbfs(float(np.sqrt(np.mean(samples**2))))
    clipped = int(np.sum(np.abs(audio[:, 0]) >= 32767))

    path = next_take_path(args.name)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")

    print(f"Saved: {path}")
    print(f"Peak: {peak:.1f} dBFS   RMS: {rms:.1f} dBFS   clipped samples: {clipped}")
    if peak > CLIP_DBFS or clipped:
        print(
            "VERDICT: too loud / clipping. Lower the mic gain or move back, then retake."
        )
    elif peak < QUIET_DBFS:
        print("VERDICT: too quiet. Raise the mic gain or move closer, then retake.")
    else:
        print("VERDICT: level OK. Listen back once to check for noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
