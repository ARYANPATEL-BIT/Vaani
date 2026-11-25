"""Record one reference take from the default microphone and report its quality.

Usage (from tools/voice_clone_eval/score):
    uv run python record_reference.py a 12     # clip A, 12 seconds of reading
    uv run python record_reference.py b 18     # clip B, 18 seconds of reading
    uv run python record_reference.py impostor 18   # a SECOND person reads clip B's text

Reads the text from ../reference_script.txt (open it in an editor; the Hindi is
not printed here). Writes audio/reference/clip_<a|b>_take<N>.wav, or
impostor_take<N>.wav for the second person, never overwriting an earlier take.
Output is ASCII only. The impostor clip gives score.py a real "different person"
floor; until it exists, score.py falls back to the Piper voices.

The take starts with 1.5 s of silence ("room tone") so the script can measure the
background noise, then you read. The saved file drops most of that lead-in.
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

ROOM_TONE_S = 1.5  # stay silent for this long before GO
SKIP_S = 0.5  # mic start-up: the first ~0.4 s of a take is digital silence
KEEP_LEAD_S = 0.2  # silence kept before the speech in the saved file
FRAME = SAMPLE_RATE // 50  # 20 ms frames for level measurement

# Thresholds in dBFS (decibels relative to the loudest value a 16-bit sample can
# hold, so they are negative). SNR, signal-to-noise ratio, is how far the voice
# sits above the background noise; cloning models copy that noise into every clip.
CLIP_DBFS = -1.0
QUIET_DBFS = -20.0
MIN_SNR_DB = 25.0


def next_take_path(name: str) -> Path:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    stem = "impostor" if name == "impostor" else f"clip_{name}"
    n = 1
    while (AUDIO_DIR / f"{stem}_take{n}.wav").exists():
        n += 1
    return AUDIO_DIR / f"{stem}_take{n}.wav"


def frame_dbfs(x: np.ndarray) -> np.ndarray:
    """Loudness (RMS, in dBFS) of each 20 ms frame."""
    frames = x[: len(x) // FRAME * FRAME].reshape(-1, FRAME)
    return 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=["a", "b", "impostor"])
    parser.add_argument("seconds", type=float)
    args = parser.parse_args()

    device = sd.query_devices(kind="input")["name"]
    print("Input device:", device.encode("ascii", "replace").decode())
    print(f"Clip {args.name.upper()}: stay SILENT until GO, then read.")
    for n in (3, 2, 1):
        print(f"  {n}...")
        time.sleep(1)

    # sd.rec returns at once and records in the background; sd.wait blocks
    # until the buffer is full. The sleep in between is the room-tone lead-in.
    total = ROOM_TONE_S + args.seconds
    audio = sd.rec(
        int(total * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16"
    )
    print("  (silence, measuring the room)")
    time.sleep(ROOM_TONE_S)
    print("GO")
    sd.wait()
    print("STOP")

    x = audio[:, 0].astype(np.float32) / 32768.0
    lead = int(ROOM_TONE_S * SAMPLE_RATE)
    noise = frame_dbfs(x[int(SKIP_S * SAMPLE_RATE) : lead])
    speech = frame_dbfs(x[lead:])
    noise_db = float(np.median(noise))
    voice_db = float(np.percentile(speech, 90))  # the louder stretches of speech
    snr = voice_db - noise_db
    peak = 20 * np.log10(float(np.max(np.abs(x[lead:]))) + 1e-9)
    clipped = int(np.sum(np.abs(audio[lead:, 0]) >= 32767))

    path = next_take_path(args.name)
    keep = audio[lead - int(KEEP_LEAD_S * SAMPLE_RATE) :]
    sf.write(path, keep, SAMPLE_RATE, subtype="PCM_16")

    print(f"Saved: {path} ({len(keep) / SAMPLE_RATE:.1f} s)")
    print(
        f"Peak {peak:.1f} dBFS | voice {voice_db:.1f} dBFS | "
        f"room noise {noise_db:.1f} dBFS | SNR {snr:.1f} dB | clipped {clipped}"
    )
    if peak > CLIP_DBFS or clipped:
        print("VERDICT: clipping. Lower the mic level or move back, then retake.")
    elif peak < QUIET_DBFS:
        print("VERDICT: too quiet. Raise the mic level or move closer, then retake.")
    elif snr < MIN_SNR_DB:
        print(
            f"VERDICT: too noisy (SNR under {MIN_SNR_DB:.0f} dB). Move closer, "
            "turn off fans/AC, or use a headset mic, then retake."
        )
    else:
        print("VERDICT: OK. Listen back once to check it sounds natural.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
