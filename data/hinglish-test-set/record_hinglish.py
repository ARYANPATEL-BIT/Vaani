#!/usr/bin/env python3
"""
record_hinglish.py — Interactive recorder for the Vaani Hinglish test set.

Records Hinglish utterances (H1-001 through H1-100) one at a time, saving each
as a 16 kHz mono PCM-16 WAV file in data/hinglish-test-set/audio/.

Usage (from repo root):
    python3 data/hinglish-test-set/record_hinglish.py              # record all unrecorded (1..100)
    python3 data/hinglish-test-set/record_hinglish.py --part 2     # record Part 2 (H1-051 to H1-100)
    python3 data/hinglish-test-set/record_hinglish.py --part 1     # record Part 1 (H1-001 to H1-050)
    python3 data/hinglish-test-set/record_hinglish.py --id H1-051  # record or re-record specific utterance
    python3 data/hinglish-test-set/record_hinglish.py --start H1-051 # resume starting at H1-051
    python3 data/hinglish-test-set/record_hinglish.py --list       # list status of all 100 utterances

Controls during recording:
    Enter          → start recording / finish recording
    Enter (after)  → accept recording and move to next
    r              → re-record current utterance
    s              → skip this utterance
    q              → quit (progress is always saved)

Requirements:
    pip3 install sounddevice numpy --break-system-packages

Format:
    Sample rate : 16,000 Hz
    Channels    : 1 (mono)
    Bit depth   : 16-bit signed PCM
    Format      : WAV
"""

import argparse
import json
import os
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = REPO_ROOT / "docs" / "test-sets" / "hinglish-100.json"
AUDIO_DIR = REPO_ROOT / "data" / "hinglish-test-set" / "audio"

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "int16"


def _ensure_sounddevice():
    try:
        import sounddevice as sd
        import numpy as np
        return sd, np
    except ImportError:
        print("\n[ERROR] sounddevice or numpy not installed.")
        print("Run:  pip3 install sounddevice numpy --break-system-packages")
        sys.exit(1)


def _load_manifest(manifest_path: Path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["utterances"]


def _already_recorded(audio_dir: Path):
    return {p.stem for p in audio_dir.glob("H1-*.wav") if p.stat().st_size > 44}


def _save_wav(path: Path, frames, sample_rate: int):
    import numpy as np
    combined = np.concatenate(frames, axis=0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit PCM = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(combined.tobytes())


def _calc_stats(path: Path):
    """Compute duration and RMS energy of WAV file."""
    import numpy as np
    with wave.open(str(path), "rb") as wf:
        n_frames = wf.getnframes()
        rate = wf.getframerate()
        ch = wf.getnchannels()
        bits = wf.getsampwidth() * 8
        raw_bytes = wf.readframes(n_frames)

    duration_s = n_frames / rate if rate > 0 else 0.0
    if len(raw_bytes) > 0:
        samples = np.frombuffer(raw_bytes, dtype=np.int16)
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) / 32768.0
        peak = float(np.max(np.abs(samples))) / 32768.0
    else:
        rms = 0.0
        peak = 0.0

    return {
        "duration_s": round(duration_s, 2),
        "sample_rate": rate,
        "channels": ch,
        "bit_depth": bits,
        "rms": round(rms, 4),
        "peak": round(peak, 4),
    }


def record_single_utterance(sd, np, utt, outfile: Path, idx: int, total: int):
    uid = utt["id"]
    text = utt["text"]
    cat = utt.get("category", "")
    part = utt.get("part", 1)

    while True:
        print("\n" + "-" * 60)
        print(f"[{idx}/{total}]  {uid}  (Part {part} · {cat})")
        print(f"  Speak aloud:")
        print(f"    \033[1;36m\"{text}\"\033[0m")
        print("-" * 60)

        prompt = input("  Press [Enter] to start recording (or 's' to skip, 'q' to quit): ").strip().lower()
        if prompt == "q":
            return "quit"
        if prompt == "s":
            print(f"  Skipped {uid}.")
            return "skip"

        # Record
        print("  \033[1;31m● RECORDING...\033[0m (speak now, press [Enter] when finished)")
        frames = []
        state = {"active": True}

        def callback(indata, f, t, status):
            if status:
                print(f"  [warn] {status}", file=sys.stderr)
            if state["active"]:
                frames.append(indata.copy())

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, callback=callback):
                input()  # Wait for Enter
                state["active"] = False
        except Exception as e:
            print(f"  [ERROR recording] {e}")
            return "error"

        if not frames:
            print("  [!] Nothing captured. Press Enter to retry.")
            continue

        _save_wav(outfile, frames, SAMPLE_RATE)
        stats = _calc_stats(outfile)

        print(f"  ✓ Saved: {outfile.name} ({stats['duration_s']}s · {stats['sample_rate']}Hz · mono · 16-bit)")
        print(f"    Audio level: RMS={stats['rms']:.3f}, Peak={stats['peak']:.3f}")

        if stats["duration_s"] < 0.5:
            print("  \033[1;33m[!] Warning: Recording is under 0.5s (very short).\033[0m")
        if stats["rms"] < 0.005:
            print("  \033[1;33m[!] Warning: Audio level is near silent. Microphone might be muted.\033[0m")

        post = input("  Press [Enter] to accept, 'r' to re-record, 'q' to quit: ").strip().lower()
        if post == "r":
            print("  Re-recording...")
            continue
        elif post == "q":
            return "quit"
        else:
            return "ok"


def main():
    parser = argparse.ArgumentParser(description="Vaani Hinglish Test Set Recorder (100 Utterances)")
    parser.add_argument("--part", choices=["1", "2", "all"], default="all", help="Part to record: 1 (H1-001..H1-050), 2 (H1-051..H1-100), or all")
    parser.add_argument("--id", type=str, help="Record/re-record a specific utterance ID (e.g. H1-051)")
    parser.add_argument("--start", type=str, help="Start recording from a specific utterance ID")
    parser.add_argument("--list", action="store_true", help="List all utterances and recording status")
    parser.add_argument("--force", action="store_true", help="Re-record even if audio file already exists")
    args = parser.parse_args()

    sd, np = _ensure_sounddevice()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    all_utterances = _load_manifest(MANIFEST)
    done_ids = _already_recorded(AUDIO_DIR)

    if args.list:
        print("\n" + "=" * 70)
        print("  Vaani Hinglish Test Set — Utterance Status")
        print("=" * 70)
        for u in all_utterances:
            uid = u["id"]
            status = "✓ RECORDED" if uid in done_ids else "✗ MISSING "
            p = AUDIO_DIR / f"{uid}.wav"
            dur_info = f"({_calc_stats(p)['duration_s']}s)" if uid in done_ids else ""
            print(f"  {status}  {uid} [Part {u.get('part', 1)}] {dur_info:10s} \"{u['text'][:40]}...\"")
        print("=" * 70)
        print(f"  Total recorded: {len(done_ids)} / {len(all_utterances)}")
        return

    # Filter utterances based on options
    if args.id:
        target = [u for u in all_utterances if u["id"].upper() == args.id.upper()]
        if not target:
            print(f"[ERROR] Utterance ID '{args.id}' not found in manifest.")
            sys.exit(1)
        utterances_to_record = target
    else:
        if args.part == "1":
            subset = [u for u in all_utterances if u["part"] == 1]
        elif args.part == "2":
            subset = [u for u in all_utterances if u["part"] == 2]
        else:
            subset = all_utterances

        if args.start:
            start_id = args.start.upper()
            found_start = False
            filtered = []
            for u in subset:
                if u["id"].upper() == start_id:
                    found_start = True
                if found_start:
                    filtered.append(u)
            if not found_start:
                print(f"[ERROR] Start ID '{args.start}' not found in selected part.")
                sys.exit(1)
            subset = filtered

        if args.force:
            utterances_to_record = subset
        else:
            utterances_to_record = [u for u in subset if u["id"] not in done_ids]

    total_target = len(utterances_to_record)
    total_corpus = len(all_utterances)

    print("\n" + "=" * 65)
    print("  Vaani — Hinglish Test Set Recorder")
    print(f"  Mode: Part {args.part.upper()} | Remaining to record: {total_target}")
    print("=" * 65)
    print(f"  Manifest   : {MANIFEST.relative_to(REPO_ROOT)}")
    print(f"  Audio dir  : {AUDIO_DIR.relative_to(REPO_ROOT)}")
    print(f"  Format     : {SAMPLE_RATE} Hz · mono · 16-bit PCM WAV")
    print(f"  Corpus     : {len(done_ids)} recorded / {total_corpus} total")
    print("=" * 65)

    if total_target == 0:
        print("\n  🎉 All selected utterances are already recorded!")
        print("  Run: python3 data/hinglish-test-set/validate_hinglish.py\n")
        return

    recorded_this_session = 0
    for idx, utt in enumerate(utterances_to_record, start=1):
        uid = utt["id"]
        outfile = AUDIO_DIR / f"{uid}.wav"
        result = record_single_utterance(sd, np, utt, outfile, idx, total_target)
        if result == "ok":
            recorded_this_session += 1
        elif result == "quit":
            print("\n  Session terminated by user.")
            break

    done_after = _already_recorded(AUDIO_DIR)
    print("\n" + "=" * 65)
    print(f"  Recorded this session : {recorded_this_session}")
    print(f"  Total recorded so far : {len(done_after)} / {total_corpus}")
    print("=" * 65)
    print("  To validate current recordings, run:")
    print("    python3 data/hinglish-test-set/validate_hinglish.py\n")


if __name__ == "__main__":
    main()
