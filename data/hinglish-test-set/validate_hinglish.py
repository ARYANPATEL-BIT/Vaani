#!/usr/bin/env python3
"""
validate_hinglish.py — Validates Part 1 recordings against the manifest.

Checks:
  - H1-001 through H1-050 WAV files all exist
  - Each file is a readable WAV
  - Sample rate == 16000 Hz
  - Channels == 1
  - Bit depth == 16 bit
  - Duration >= 0.5 s (warn if shorter)
  - Every recording has exact ground-truth text in the manifest
  - No duplicate IDs
  - No missing mappings

Usage (from repo root):
    python3 data/hinglish-test-set/validate_hinglish.py
"""

import json
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST  = REPO_ROOT / "docs" / "test-sets" / "hinglish-100.json"
AUDIO_DIR = REPO_ROOT / "data" / "hinglish-test-set" / "audio"

REQUIRED_SAMPLE_RATE = 16_000
REQUIRED_CHANNELS    = 1
REQUIRED_BIT_DEPTH   = 16
MIN_DURATION_S       = 0.5


def main():
    print("\n" + "=" * 60)
    print("  Vaani — Hinglish Test Set Validator")
    print("=" * 60)

    # Load manifest
    with open(MANIFEST) as f:
        data = json.load(f)

    all_utterances = data["utterances"]
    part1 = [u for u in all_utterances if u["part"] == 1]
    part2 = [u for u in all_utterances if u["part"] == 2]

    print(f"\n  Manifest    : {MANIFEST.relative_to(REPO_ROOT)}")
    print(f"  Audio dir   : {AUDIO_DIR.relative_to(REPO_ROOT)}")
    print(f"  Total scripted : {len(all_utterances)} (need 100)")
    print(f"  Part 1 scripted: {len(part1)} (need 50)")
    print(f"  Part 2 scripted: {len(part2)} (need 50)")

    errors   = []
    warnings = []

    # ── Manifest checks ─────────────────────────────────────────────────────
    ids   = [u["id"] for u in all_utterances]
    texts = [u["text"] for u in all_utterances]

    if len(ids) != 100:
        errors.append(f"Manifest: {len(ids)} utterances, expected 100")

    dup_ids = [i for i in ids if ids.count(i) > 1]
    if dup_ids:
        errors.append(f"Duplicate IDs: {sorted(set(dup_ids))}")

    dup_texts = [t for t in texts if texts.count(t) > 1]
    if dup_texts:
        errors.append(f"Duplicate texts found ({len(set(dup_texts))} unique duplicates)")

    for u in all_utterances:
        if not u.get("text", "").strip():
            errors.append(f"{u['id']}: empty ground-truth text")

    # ── Recording checks ─────────────────────────────────────────────────────
    recorded   = []
    missing    = []
    wav_errors = []

    print("\n  Checking recordings...\n")

    for utt in part1:
        uid  = utt["id"]
        path = AUDIO_DIR / f"{uid}.wav"

        if not path.exists():
            missing.append(uid)
            print(f"  ✗ MISSING   {uid}")
            continue

        try:
            with wave.open(str(path), "rb") as wf:
                ch    = wf.getnchannels()
                rate  = wf.getframerate()
                bits  = wf.getsampwidth() * 8
                dur   = wf.getnframes() / wf.getframerate()

            ok = True
            if rate != REQUIRED_SAMPLE_RATE:
                wav_errors.append(f"{uid}: sample_rate={rate} (need {REQUIRED_SAMPLE_RATE})")
                ok = False
            if ch != REQUIRED_CHANNELS:
                wav_errors.append(f"{uid}: channels={ch} (need {REQUIRED_CHANNELS})")
                ok = False
            if bits != REQUIRED_BIT_DEPTH:
                wav_errors.append(f"{uid}: bit_depth={bits} (need {REQUIRED_BIT_DEPTH})")
                ok = False
            if dur < MIN_DURATION_S:
                warnings.append(f"{uid}: duration={dur:.2f}s (< {MIN_DURATION_S}s — may be too short)")

            status = "✓ OK" if ok else "✗ BAD FORMAT"
            print(f"  {status}  {uid}  ({dur:.1f}s · {rate}Hz · {ch}ch · {bits}bit)")
            recorded.append(uid)

        except Exception as exc:
            wav_errors.append(f"{uid}: unreadable WAV — {exc}")
            print(f"  ✗ ERROR     {uid}: {exc}")

    # ── Ground-truth check ──────────────────────────────────────────────────
    id_to_text = {u["id"]: u["text"] for u in part1}
    for uid in recorded:
        if not id_to_text.get(uid, "").strip():
            errors.append(f"{uid}: recorded but no ground-truth text in manifest")

    # ── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Utterances scripted : {len(all_utterances)} / 100")
    print(f"  Part 1 recordings   : {len(recorded)} / 50")
    print(f"  Missing             : {len(missing)}")
    print(f"  Format errors       : {len(wav_errors)}")
    print(f"  Warnings            : {len(warnings)}")
    print(f"  Hard errors         : {len(errors)}")

    if missing:
        print(f"\n  Missing recordings ({len(missing)}):")
        for uid in missing:
            gt = id_to_text.get(uid, "(no text)")
            print(f"    {uid}: \"{gt}\"")

    if wav_errors:
        print(f"\n  Format errors:")
        for e in wav_errors:
            print(f"    {e}")

    if warnings:
        print(f"\n  Warnings:")
        for w in warnings:
            print(f"    {w}")

    if errors:
        print(f"\n  Hard errors:")
        for e in errors:
            print(f"    {e}")

    all_ok = (
        len(all_utterances) == 100
        and len(recorded) == 50
        and not missing
        and not wav_errors
        and not errors
    )

    print()
    if all_ok:
        print("  ✅  PASS — Day 3 recording requirements met.")
        print("       100 scripted, 50 recorded, all valid, all have ground truth.")
    else:
        print("  ❌  NOT COMPLETE — see above for what remains.")
        if len(recorded) < 50:
            remaining = 50 - len(recorded)
            print(f"       Run record_hinglish.py to record the {remaining} remaining utterances.")
    print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
