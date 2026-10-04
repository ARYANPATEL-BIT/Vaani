#!/usr/bin/env python3
"""
validate_hinglish.py — Validates Hinglish test set recordings against the manifest.

Day 4 target: 100 recordings (H1-001 through H1-100) plus manifest.

Checks:
  - 100 total utterances scripted in manifest
  - 100 unique IDs (H1-001 through H1-100 all present)
  - No duplicate IDs
  - No duplicate texts
  - Every utterance has non-empty ground-truth text
  - All 100 WAV files exist in audio/
  - Each file is a readable WAV
  - Sample rate == 16000 Hz
  - Channels == 1 (mono)
  - Bit depth == 16-bit PCM
  - Duration >= 0.5 s
  - Audio contains real speech (RMS energy > threshold, not silence/zeros)
  - Exact 1:1 ground-truth mapping for every recording
  - Manifest integrity (docs/test-sets/hinglish-100.json and data/hinglish-test-set/manifest.json)

Usage (from repo root):
    python3 data/hinglish-test-set/validate_hinglish.py
    python3 data/hinglish-test-set/validate_hinglish.py --part 1
    python3 data/hinglish-test-set/validate_hinglish.py --part 2
"""

import argparse
import json
import math
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_DOCS = REPO_ROOT / "docs" / "test-sets" / "hinglish-100.json"
MANIFEST_DATA = REPO_ROOT / "data" / "hinglish-test-set" / "manifest.json"
AUDIO_DIR = REPO_ROOT / "data" / "hinglish-test-set" / "audio"

REQUIRED_SAMPLE_RATE = 16_000
REQUIRED_CHANNELS = 1
REQUIRED_BIT_DEPTH = 16
MIN_DURATION_S = 0.5
MIN_RMS_THRESHOLD = 0.003  # Flag absolute silence / muted mic


def calc_audio_rms(path: Path):
    """Calculate RMS energy of 16-bit PCM audio without requiring third-party libraries."""
    with wave.open(str(path), "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if not raw:
        return 0.0, 0.0

    # 16-bit signed PCM little-endian
    count = len(raw) // 2
    sum_squares = 0.0
    peak = 0
    for i in range(0, len(raw), 2):
        val = int.from_bytes(raw[i:i+2], byteorder="little", signed=True)
        sum_squares += val * val
        if abs(val) > peak:
            peak = abs(val)

    rms = math.sqrt(sum_squares / count) / 32768.0 if count > 0 else 0.0
    normalized_peak = peak / 32768.0
    return rms, normalized_peak


def validate_test_set(part_filter="all"):
    print("\n" + "=" * 65)
    print("  Vaani — Hinglish Test Set Validator (Day 4: 100 Utterances)")
    print("=" * 65)

    errors = []
    warnings = []

    # 1. Check manifest files
    if not MANIFEST_DOCS.exists():
        errors.append(f"Missing primary manifest: {MANIFEST_DOCS.relative_to(REPO_ROOT)}")
        print(f"  ✗ ERROR: {MANIFEST_DOCS} not found")
        return 1

    with open(MANIFEST_DOCS, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_utterances = data.get("utterances", [])
    expected_ids = [f"H1-{i:03d}" for i in range(1, 101)]

    print(f"  Primary Manifest : {MANIFEST_DOCS.relative_to(REPO_ROOT)}")
    if MANIFEST_DATA.exists():
        print(f"  Dataset Manifest : {MANIFEST_DATA.relative_to(REPO_ROOT)}")
    print(f"  Audio Directory  : {AUDIO_DIR.relative_to(REPO_ROOT)}")
    print(f"  Total Scripted   : {len(all_utterances)} / 100")

    # 2. Manifest consistency checks
    actual_ids = [u["id"] for u in all_utterances]
    texts = [u["text"] for u in all_utterances]

    if len(all_utterances) != 100:
        errors.append(f"Manifest: expected 100 utterances, found {len(all_utterances)}")

    missing_expected_ids = set(expected_ids) - set(actual_ids)
    if missing_expected_ids:
        errors.append(f"Manifest missing expected IDs: {sorted(missing_expected_ids)}")

    dup_ids = [uid for uid in actual_ids if actual_ids.count(uid) > 1]
    if dup_ids:
        errors.append(f"Duplicate IDs in manifest: {sorted(set(dup_ids))}")

    dup_texts = [t for t in texts if texts.count(t) > 1]
    if dup_texts:
        errors.append(f"Duplicate texts found in manifest: {len(set(dup_texts))} duplicates")

    for u in all_utterances:
        if not u.get("text", "").strip():
            errors.append(f"Utterance {u.get('id', '?')} has empty ground-truth text")

    # Filter target utterances
    if part_filter == "1":
        target_utterances = [u for u in all_utterances if u.get("part") == 1]
        target_label = "Part 1 (H1-001..H1-050)"
    elif part_filter == "2":
        target_utterances = [u for u in all_utterances if u.get("part") == 2]
        target_label = "Part 2 (H1-051..H1-100)"
    else:
        target_utterances = all_utterances
        target_label = "All 100 Utterances (H1-001..H1-100)"

    print(f"  Validating Target: {target_label} ({len(target_utterances)} total)")
    print("-" * 65)

    # 3. Audio recordings checks
    missing_files = []
    format_errors = []
    silent_recordings = []
    valid_recordings = []

    for utt in target_utterances:
        uid = utt["id"]
        wav_file = AUDIO_DIR / f"{uid}.wav"

        if not wav_file.exists():
            missing_files.append(uid)
            continue

        if wav_file.stat().st_size <= 44:
            format_errors.append(f"{uid}: file size too small ({wav_file.stat().st_size} bytes, empty WAV)")
            continue

        try:
            with wave.open(str(wav_file), "rb") as wf:
                ch = wf.getnchannels()
                rate = wf.getframerate()
                bits = wf.getsampwidth() * 8
                n_frames = wf.getnframes()
                duration = n_frames / rate if rate > 0 else 0.0

            file_ok = True
            if rate != REQUIRED_SAMPLE_RATE:
                format_errors.append(f"{uid}: sample rate {rate}Hz != required {REQUIRED_SAMPLE_RATE}Hz")
                file_ok = False
            if ch != REQUIRED_CHANNELS:
                format_errors.append(f"{uid}: channels {ch} != required {REQUIRED_CHANNELS}")
                file_ok = False
            if bits != REQUIRED_BIT_DEPTH:
                format_errors.append(f"{uid}: bit depth {bits} != required {REQUIRED_BIT_DEPTH}")
                file_ok = False
            if duration < MIN_DURATION_S:
                warnings.append(f"{uid}: duration {duration:.2f}s is under {MIN_DURATION_S}s")

            # Real speech check
            rms, peak = calc_audio_rms(wav_file)
            if rms < MIN_RMS_THRESHOLD:
                silent_recordings.append(f"{uid}: silent or near-zero audio (RMS={rms:.4f}, peak={peak:.4f})")
                file_ok = False

            if file_ok:
                valid_recordings.append(uid)

        except Exception as e:
            format_errors.append(f"{uid}: unreadable WAV file ({e})")

    # 4. Ground-truth mapping check
    id_to_utt = {u["id"]: u for u in all_utterances}
    for uid in valid_recordings:
        utt = id_to_utt.get(uid)
        if not utt or not utt.get("text", "").strip():
            errors.append(f"{uid}: recording exists but has no ground-truth text")

    # 5. Manifest file check (data/hinglish-test-set/manifest.json)
    if MANIFEST_DATA.exists():
        try:
            with open(MANIFEST_DATA, "r", encoding="utf-8") as f:
                mdata = json.load(f)
            rec_list = mdata.get("recordings", [])
            if len(rec_list) != 100:
                errors.append(f"manifest.json has {len(rec_list)} recordings, expected 100")
        except Exception as e:
            errors.append(f"manifest.json unparseable: {e}")

    # 6. Print Summary
    p1_recorded = len([uid for uid in valid_recordings if int(uid.split("-")[1]) <= 50])
    p2_recorded = len([uid for uid in valid_recordings if int(uid.split("-")[1]) > 50])

    print("\n" + "=" * 65)
    print("  VALIDATION SUMMARY")
    print("=" * 65)
    print(f"  Utterances in Manifest   : {len(all_utterances)} / 100")
    print(f"  Part 1 Recordings (1..50): {p1_recorded} / 50")
    print(f"  Part 2 Recordings (51..100): {p2_recorded} / 50")
    print(f"  Total Valid Recordings   : {len(valid_recordings)} / {len(target_utterances)}")
    print(f"  Missing Recordings       : {len(missing_files)}")
    print(f"  Format Errors            : {len(format_errors)}")
    print(f"  Silent / Empty Audio     : {len(silent_recordings)}")
    print(f"  Warnings                 : {len(warnings)}")
    print(f"  Hard Errors              : {len(errors)}")
    print("=" * 65)

    if missing_files:
        print(f"\n  Missing Recordings ({len(missing_files)}):")
        # Print first 10 missing as preview
        preview = missing_files[:10]
        for uid in preview:
            txt = id_to_utt[uid]["text"] if uid in id_to_utt else ""
            print(f"    ✗ {uid}: \"{txt}\"")
        if len(missing_files) > 10:
            print(f"    ... and {len(missing_files) - 10} more.")

    if format_errors:
        print(f"\n  Format Errors ({len(format_errors)}):")
        for e in format_errors:
            print(f"    ✗ {e}")

    if silent_recordings:
        print(f"\n  Silent / Low Audio Warnings ({len(silent_recordings)}):")
        for s in silent_recordings:
            print(f"    ✗ {s}")

    if errors:
        print(f"\n  Hard Errors ({len(errors)}):")
        for e in errors:
            print(f"    ✗ {e}")

    is_complete = (
        len(all_utterances) == 100
        and len(valid_recordings) == len(target_utterances)
        and not missing_files
        and not format_errors
        and not silent_recordings
        and not errors
    )

    print()
    if is_complete:
        print("  \033[1;32m✅ PASS — All 100 Hinglish recordings verified and ready for Aryan's benchmark.\033[0m")
        print("       100 scripted, 100 recorded, correct format, exact ground-truth mapping.")
    else:
        print("  \033[1;31m❌ NOT COMPLETE — Test set requirements not yet fulfilled.\033[0m")
        if missing_files:
            print(f"       Action: Record the missing utterances with:")
            print(f"       python3 data/hinglish-test-set/record_hinglish.py")
    print()

    return 0 if is_complete else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Hinglish Test Set")
    parser.add_argument("--part", choices=["1", "2", "all"], default="all", help="Part to validate: 1, 2, or all")
    args = parser.parse_args()
    sys.exit(validate_test_set(args.part))
