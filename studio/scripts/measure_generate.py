"""Time a 2-sentence generation on the GPU and record the VRAM it takes.

Usage (from studio/):
    uv run python scripts/measure_generate.py

Uses the committed synthetic reference (backend/tests/fixtures/speech_16k_mono.wav)
and the configured model, forced onto CUDA. Runs the same script three times:
the first includes CUDA warm-up, the later ones are what a user waits for.
Writes docs/findings/voice-studio/generate_<stamp>.txt; prints ASCII only.
"""

import os

# As in voice_studio/__main__.py: no per-token progress bar, so the timing is
# the server's. Set before anything imports tqdm.
os.environ.setdefault("TQDM_DISABLE", "1")

import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from time import perf_counter  # noqa: E402

import perth  # noqa: E402
import torch  # noqa: E402

from voice_studio.config import get_studio_settings  # noqa: E402
from voice_studio.model import MIB, Cloner  # noqa: E402
from voice_studio.script import join  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "backend/tests/fixtures/speech_16k_mono.wav"
ENGLISH = "This is a short test of the voice studio."
# "This is a short test of the voice studio." in Hindi (escapes keep this file ASCII).
HINDI = (
    "\u092f\u0939 \u090f\u0915 \u091b\u094b\u091f\u093e "
    "\u092a\u0930\u0940\u0915\u094d\u0937\u0923 \u0939\u0948\u0964"
)
RUNS = 3


def main() -> int:
    if not torch.cuda.is_available():
        print("no CUDA device")
        return 1
    cfg = get_studio_settings().model_copy(update={"device": "cuda"})
    free, total = torch.cuda.mem_get_info()
    lines = [
        f"generate {time.strftime('%Y%m%d-%H%M%S')}",
        f"torch {torch.__version__} | {torch.cuda.get_device_name(0)}",
        f"model {cfg.hf_repo}@{cfg.hf_revision} t3={cfg.t3_model}",
        f"reference {REFERENCE.relative_to(REPO).as_posix()} (Windows SAPI voice)",
        f"script: English {len(ENGLISH)} chars + Hindi {len(HINDI)} chars",
        f"gpu free at start: {free // MIB} of {total // MIB} MiB",
        f"tqdm progress bars: {'off' if os.environ.get('TQDM_DISABLE') else 'on'}",
    ]
    cloner = Cloner(cfg)
    started = perf_counter()
    cloner._ensure_loaded()  # download (first run only) + load, timed alone
    lines.append(f"download_and_load_s: {perf_counter() - started:.1f}")
    lines.append(f"vram_after_load_mib: {torch.cuda.memory_allocated() // MIB}")
    watermarker = perth.PerthImplicitWatermarker()
    for run in range(1, RUNS + 1):
        torch.cuda.reset_peak_memory_stats()
        started = perf_counter()
        waves = cloner.synthesize(
            REFERENCE, [(ENGLISH, "en"), (HINDI, "hi")], threading.Event()
        )
        spent = perf_counter() - started
        audio = join(waves, cloner.sample_rate, cfg.sentence_gap_ms)
        seconds = len(audio) / cloner.sample_rate
        marks = [
            round(
                float(watermarker.get_watermark(w, sample_rate=cloner.sample_rate)), 2
            )
            for w in waves
        ]
        sentence_s = [round(len(w) / cloner.sample_rate, 2) for w in waves]
        peak = torch.cuda.max_memory_allocated() // MIB
        reserved = torch.cuda.memory_reserved() // MIB
        lines.append(
            f"run {run}: {spent:.2f} s for {seconds:.2f} s of audio"
            f" (rtf {spent / seconds:.2f}) | sentences {sentence_s} s"
            f" | peak vram {peak} MiB (reserved {reserved}) | watermark {marks}"
        )
    dest = (
        REPO
        / "docs/findings/voice-studio"
        / f"generate_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print("written:", dest.relative_to(REPO).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
