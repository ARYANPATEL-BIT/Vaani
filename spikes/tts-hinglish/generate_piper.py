#!/usr/bin/env python3
"""
spikes/tts-hinglish/generate_piper.py
---------------------------------------
Week 1 Friday Spike — Piper TTS test.

Synthesises two Hinglish sentences (romanised and Devanagari) locally
using the Piper provider adapter and a downloaded Hindi voice model.

Model required (download first, or run this script with --download):
    models/hi_IN-priyamvada-medium.onnx
    models/hi_IN-priyamvada-medium.onnx.json

Usage:
    python generate_piper.py [--download]

    --download   fetch the voice model files from HuggingFace before running

Output files:
    audio/piper_romanized.wav
    audio/piper_devanagari.wav

Config log:
    results/piper_run.json

IMPORTANT: The .onnx model file is ~61 MB. It is listed in .gitignore
and must NOT be committed to the repository.
"""

import json
import sys
import urllib.request
from pathlib import Path

# Add parent directory for provider imports
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from providers import get_tts_provider  # noqa: E402

# ── model paths ───────────────────────────────────────────────────────────────
MODELS_DIR = HERE / "models"
MODEL_ONNX = MODELS_DIR / "hi_IN-priyamvada-medium.onnx"
MODEL_JSON = MODELS_DIR / "hi_IN-priyamvada-medium.onnx.json"

HF_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    "/hi/hi_IN/priyamvada/medium"
)

# ── test sentences ────────────────────────────────────────────────────────────
SENTENCES = {
    "romanized": (
        "Namaste, aaj hum real-time voice conversation ke baare mein baat karenge."
    ),
    "devanagari": (
        "नमस्ते, आज हम real-time voice conversation के बारे में बात करेंगे।"
    ),
}

OUT_DIR = HERE / "audio"
RESULTS_DIR = HERE / "results"


# ── helpers ───────────────────────────────────────────────────────────────────

def download_model() -> None:
    """Download the Piper Hindi voice model from HuggingFace."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for fname in [MODEL_ONNX.name, MODEL_JSON.name]:
        dest = MODELS_DIR / fname
        url = f"{HF_BASE}/{fname}"
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"  already present: {dest.name}")
            continue
        print(f"  downloading {fname} …")
        urllib.request.urlretrieve(url, dest)
        print(f"  saved {dest.stat().st_size / 1024 / 1024:.1f} MB → {dest}")


def synthesise(text: str) -> tuple[bytes, float]:
    """Synthesise text using the Piper TTS provider.

    Returns (wav_bytes, wall_time_seconds).
    """
    provider = get_tts_provider(
        "piper",
        model_onnx_path=MODEL_ONNX,
        model_json_path=MODEL_JSON,
    )
    result = provider.synthesize(text)
    return result.wav_bytes, result.latency_s


def main() -> None:
    # ── optional model download ────────────────────────────────────────────
    if "--download" in sys.argv:
        print("Downloading Piper Hindi voice model …")
        download_model()

    # ── verify model present ───────────────────────────────────────────────
    if not MODEL_ONNX.exists() or MODEL_ONNX.stat().st_size < 10_000:
        print(
            f"ERROR: Model not found or incomplete: {MODEL_ONNX}\n"
            f"  Run:  python generate_piper.py --download\n"
            f"  Or manually download the .onnx and .onnx.json from:\n"
            f"  {HF_BASE}/",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── check piper-tts is importable ────────────────────────────────────
    try:
        import piper  # noqa: F401
    except ImportError:
        print(
            "ERROR: piper-tts is not installed.\n"
            "  pip install piper-tts --break-system-packages",
            file=sys.stderr,
        )
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    run_log = {
        "provider": "piper",
        "model": MODEL_ONNX.name,
        "execution": "local",
        "clips": {},
    }

    for script, text in SENTENCES.items():
        out_path = OUT_DIR / f"piper_{script}.wav"
        print(f"\n[Piper] {script}")
        print(f"  text   : {text[:80]}")
        print(f"  output : {out_path}")

        try:
            wav_bytes, latency = synthesise(text)
            out_path.write_bytes(wav_bytes)
            size_kb = len(wav_bytes) / 1024
            print(f"  status : OK  ({size_kb:.1f} KB, {latency:.2f} s)")

            run_log["clips"][script] = {
                "text": text,
                "output_file": str(out_path.relative_to(HERE)),
                "size_bytes": len(wav_bytes),
                "latency_s": round(latency, 3),
                "status": "ok",
            }

        except Exception as exc:
            print(f"  status : FAILED — {exc}", file=sys.stderr)
            run_log["clips"][script] = {
                "text": text,
                "status": "failed",
                "error": str(exc),
            }

    log_path = RESULTS_DIR / "piper_run.json"
    log_path.write_text(json.dumps(run_log, ensure_ascii=False, indent=2))
    print(f"\nRun log written to: {log_path}")


if __name__ == "__main__":
    main()
