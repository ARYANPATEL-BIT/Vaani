#!/usr/bin/env python3
"""
record_hinglish.py — Interactive recorder for the Vaani Hinglish test set.

Records Part 1 utterances (H1-001 through H1-050) one at a time, saving each
as a 16 kHz mono PCM-16 WAV file in data/hinglish-test-set/audio/.

Usage (from repo root):
    python3 data/hinglish-test-set/record_hinglish.py

Controls:
    Enter      → start recording (then speak, then press Enter again to stop)
    s          → skip this utterance (you can come back later)
    q          → quit (progress is saved; resume by running again)

Requirements:
    pip3 install sounddevice --break-system-packages
    (already installed if you ran Day 3 setup)

Format:
    Sample rate : 16,000 Hz
    Channels    : 1 (mono)
    Bit depth   : 16-bit signed PCM
    Format      : WAV
"""

import json
import os
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST   = REPO_ROOT / "docs" / "test-sets" / "hinglish-100.json"
AUDIO_DIR  = REPO_ROOT / "data" / "hinglish-test-set" / "audio"

SAMPLE_RATE = 16_000
CHANNELS    = 1
DTYPE       = "int16"

def _ensure_sounddevice():
    try:
        import sounddevice as sd
        import numpy as np
        return sd, np
    except ImportError:
        print("\n[ERROR] sounddevice not installed.")
        print("Run:  pip3 install sounddevice --break-system-packages")
        sys.exit(1)


def _load_part1(manifest_path: Path):
    with open(manifest_path) as f:
        data = json.load(f)
    return [u for u in data["utterances"] if u["part"] == 1]


def _already_recorded(audio_dir: Path):
    return {p.stem for p in audio_dir.glob("H1-*.wav")}


def _save_wav(path: Path, frames, sample_rate: int):
    import numpy as np
    combined = np.concatenate(frames, axis=0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)          # 16-bit = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(combined.tobytes())


def _duration_str(path: Path) -> str:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate   = wf.getframerate()
    return f"{frames/rate:.1f}s"


def _validate_wav(path: Path) -> dict:
    """Return basic WAV properties for validation output."""
    with wave.open(str(path), "rb") as wf:
        return {
            "channels"   : wf.getnchannels(),
            "sample_rate": wf.getframerate(),
            "bit_depth"  : wf.getsampwidth() * 8,
            "frames"     : wf.getnframes(),
            "duration_s" : round(wf.getnframes() / wf.getframerate(), 2),
        }


def main():
    sd, np = _ensure_sounddevice()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    utterances = _load_part1(MANIFEST)
    done = _already_recorded(AUDIO_DIR)

    remaining = [u for u in utterances if u["id"] not in done]
    total     = len(utterances)

    print("\n" + "=" * 60)
    print("  Vaani — Hinglish Test Set Recorder")
    print("  Part 1: H1-001 through H1-050")
    print("=" * 60)
    print(f"  Manifest   : {MANIFEST.relative_to(REPO_ROOT)}")
    print(f"  Audio dir  : {AUDIO_DIR.relative_to(REPO_ROOT)}")
    print(f"  Format     : {SAMPLE_RATE} Hz · mono · 16-bit PCM WAV")
    print(f"  Total      : {total} utterances")
    print(f"  Done       : {len(done)}")
    print(f"  Remaining  : {len(remaining)}")
    print()
    print("  Controls:")
    print("    Enter            → start / stop recording")
    print("    s + Enter        → skip this utterance")
    print("    q + Enter        → quit (progress saved)")
    print("=" * 60)

    if not remaining:
        print("\n  All 50 Part 1 utterances already recorded!")
        print("  Run validate_hinglish.py to check all recordings.\n")
        return

    for idx, utt in enumerate(remaining, start=1):
        uid   = utt["id"]
        text  = utt["text"]
        cat   = utt["category"]
        outfile = AUDIO_DIR / f"{uid}.wav"

        print(f"\n[{idx}/{len(remaining)}]  {uid}  ({cat})")
        print(f"  Read aloud: \"{text}\"")
        print()

        action = input("  Press Enter to record, 's' to skip, 'q' to quit: ").strip().lower()

        if action == "q":
            print("\n  Quitting. Run again to continue.\n")
            break
        if action == "s":
            print(f"  Skipped {uid}.")
            continue

        # Record
        print("  ● Recording... (speak now, press Enter when done)")
        frames = []
        recording = {"active": True}

        def callback(indata, f, t, status):
            if status:
                print(f"  [warn] {status}", file=sys.stderr)
            if recording["active"]:
                frames.append(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype=DTYPE, callback=callback):
            input()          # blocks until user presses Enter
            recording["active"] = False

        if not frames:
            print("  [!] Nothing recorded — skipping.")
            continue

        _save_wav(outfile, frames, SAMPLE_RATE)
        props = _validate_wav(outfile)
        print(f"  ✓ Saved: {outfile.name}  "
              f"({props['duration_s']}s · {props['sample_rate']} Hz · "
              f"mono · {props['bit_depth']}-bit)")

        # Brief silence check (warn only — do not delete)
        total_samples = props["frames"]
        if total_samples < SAMPLE_RATE * 0.5:
            print("  [warn] Recording is under 0.5 seconds — may be too short.")

    done_after = _already_recorded(AUDIO_DIR)
    print(f"\n  Session complete. Recorded this session: "
          f"{len(done_after) - len(done)} new files.")
    print(f"  Total completed: {len(done_after)} / {total}\n")


if __name__ == "__main__":
    main()
