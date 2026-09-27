#!/usr/bin/env python3
"""
spikes/tts-hinglish/run_spike.py
----------------------------------
Week 1 Friday Spike — Master Runner.

Executes the Day 5 live speech spike using Piper as the active working engine.
Validates:
1. Audio generation for Romanized and Devanagari Hinglish using Piper.
2. Output audio integrity (WAV RIFF headers, valid channels, sample rate).
3. The provider/adapter architecture (Piper is active; Sarvam adapter boundary
   is configured for future integration without making external calls).

Usage:
    python run_spike.py
"""

import sys
import wave
from pathlib import Path

# Add current directory to path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from generate_piper import main as generate_piper_main  # noqa: E402
from providers import (  # noqa: E402
    AuthenticationError,
    get_tts_provider,
)


def verify_audio_file(file_path: Path) -> dict:
    """Validate WAV file format and properties."""
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {file_path}")

    size_bytes = file_path.stat().st_size
    if size_bytes < 1000:
        raise ValueError(f"Audio file appears truncated or empty: {file_path}")

    with wave.open(str(file_path), "rb") as w:
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        nframes = w.getnframes()
        duration_s = nframes / framerate

    return {
        "file": file_path.name,
        "size_bytes": size_bytes,
        "channels": channels,
        "sample_width": sampwidth,
        "sample_rate": framerate,
        "duration_s": round(duration_s, 2),
    }


def main() -> None:
    print("=" * 60)
    print("VAANI WEEK 1 DAY 5 — LIVE SPEECH SPIKE (PIPER)")
    print("=" * 60)

    # 1. Run Piper Generation
    print("\n[Step 1/3] Generating audio clips with active provider (Piper)...")
    generate_piper_main()

    # 2. Verify Generated Audio Clips
    print("\n[Step 2/3] Verifying generated audio clips...")
    audio_dir = HERE / "audio"
    required_clips = ["piper_romanized.wav", "piper_devanagari.wav"]
    verified = []

    for clip_name in required_clips:
        path = audio_dir / clip_name
        info = verify_audio_file(path)
        verified.append(info)
        print(
            f"  ✓ {info['file']}: {info['size_bytes']:,} bytes | "
            f"{info['sample_rate']} Hz | {info['channels']} ch | {info['duration_s']}s"
        )

    # 3. Verify Provider Architecture & Sarvam Boundary
    print("\n[Step 3/3] Validating provider/adapter architecture...")
    piper_prov = get_tts_provider("piper")
    print(
        f"  ✓ Default active provider: '{piper_prov.name}' "
        f"(available={piper_prov.is_available()})"
    )

    sarvam_prov = get_tts_provider("sarvam")
    print(
        f"  ✓ Future provider boundary: '{sarvam_prov.name}' "
        f"(available={sarvam_prov.is_available()})"
    )
    try:
        # Confirm Sarvam does not attempt network calls when unconfigured
        sarvam_prov.synthesize("test")
    except AuthenticationError as e:
        print(f"  ✓ Future Sarvam boundary verified: guard raised '{e}'")

    print("\n" + "=" * 60)
    print("SPIKE RUN COMPLETE — PIPER LIVE SPEECH READY")
    print("=" * 60)
    print("All required Day 5 Piper audio clips generated and verified.")
    print("Architecture is decoupled for future Sarvam provider integration.")


if __name__ == "__main__":
    main()
