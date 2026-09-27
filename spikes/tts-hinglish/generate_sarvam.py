#!/usr/bin/env python3
"""
spikes/tts-hinglish/generate_sarvam.py
---------------------------------------
Week 1 Friday Spike — Sarvam Bulbul TTS test.

Sends two Hinglish sentences (romanised and Devanagari) to the Sarvam
Bulbul v2 REST API and saves the resulting WAV files to audio/.

Usage:
    SARVAM_API_KEY=<your-key> python generate_sarvam.py

    OR set the key in backend/.env and this script reads it from there
    (via python-dotenv if installed, or os.environ fallback).

Output files:
    audio/sarvam_romanized.wav
    audio/sarvam_devanagari.wav

Config log:
    results/sarvam_run.json   — metadata for this run (no secrets)

Do NOT commit .env or any file containing your API key.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

# ── locate the backend .env and load it if python-dotenv is available ─────────
_root = Path(__file__).resolve().parents[2]  # repo root
_env_file = _root / "backend" / ".env"

try:
    from dotenv import load_dotenv
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    # python-dotenv not installed; fall back to reading the file manually
    if _env_file.exists():
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ── constants ─────────────────────────────────────────────────────────────────
API_URL  = "https://api.sarvam.ai/text-to-speech"
MODEL    = "bulbul:v2"
SPEAKER  = "anushka"  # female, natural Hindi/Hinglish voice
PACE     = 1.0

# Test sentences — same semantic content, two scripts.
SENTENCES = {
    "romanized": (
        "Namaste, aaj hum real-time voice conversation ke baare mein baat karenge."
    ),
    "devanagari": (
        "नमस्ते, आज हम real-time voice conversation के बारे में बात करेंगे।"
    ),
}

OUT_DIR     = Path(__file__).parent / "audio"
RESULTS_DIR = Path(__file__).parent / "results"

# ── helpers ───────────────────────────────────────────────────────────────────

def call_sarvam(text: str, api_key: str) -> tuple[bytes, float]:
    """POST to Sarvam TTS, return (wav_bytes, latency_s)."""
    import urllib.error
    import urllib.request

    payload = json.dumps({
        "inputs":         [text],
        "target_language_code": "hi-IN",
        "speaker":        SPEAKER,
        "pitch":          0,
        "pace":           PACE,
        "loudness":       1.5,
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "model":          MODEL,
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "api-subscription-key": api_key,
            "Content-Type":         "application/json",
        },
        method="POST",
    )

    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    latency = time.perf_counter() - t0

    data = json.loads(body)
    # Sarvam returns {"audios": ["<base64-wav>", ...]}
    audio_b64 = data["audios"][0]
    audio_bytes = base64.b64decode(audio_b64)
    return audio_bytes, latency


def main() -> None:
    api_key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not api_key:
        print(
            "ERROR: SARVAM_API_KEY is not set.\n"
            "  Set it in backend/.env as:  SARVAM_API_KEY=<your-key>\n"
            "  Or export it before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    run_log = {
        "provider":    "sarvam",
        "model":       MODEL,
        "speaker":     SPEAKER,
        "api_url":     API_URL,
        "sample_rate": 16000,
        "clips":       {},
    }

    for script, text in SENTENCES.items():
        out_path = OUT_DIR / f"sarvam_{script}.wav"
        print(f"\n[Sarvam] {script}")
        print(f"  text   : {text[:80]}")
        print(f"  output : {out_path}")

        try:
            audio_bytes, latency = call_sarvam(text, api_key)
            out_path.write_bytes(audio_bytes)
            size_kb = len(audio_bytes) / 1024
            print(f"  status : OK  ({size_kb:.1f} KB, {latency:.2f} s)")

            run_log["clips"][script] = {
                "text":         text,
                "output_file":  str(out_path.relative_to(Path(__file__).parent)),
                "size_bytes":   len(audio_bytes),
                "latency_s":    round(latency, 3),
                "status":       "ok",
            }

        except Exception as exc:
            print(f"  status : FAILED — {exc}", file=sys.stderr)
            run_log["clips"][script] = {
                "text":   text,
                "status": "failed",
                "error":  str(exc),
            }

    log_path = RESULTS_DIR / "sarvam_run.json"
    log_path.write_text(json.dumps(run_log, ensure_ascii=False, indent=2))
    print(f"\nRun log written to: {log_path}")


if __name__ == "__main__":
    main()
