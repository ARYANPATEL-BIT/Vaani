"""Generate the 8-sentence test set with one cloning model and measure it.

Run from inside a model's folder so its own uv environment is used:
    cd tools/voice_clone_eval/xtts
    uv run python ../run_eval.py --model xtts --ref ../audio/reference/clip_a_take1.wav

The model folder provides synth.py with two functions:
    load(ref_wav, ref_text, device) -> state     (model load + reference conditioning)
    synth(state, text, lang) -> (float32 numpy wave, sample_rate)
This file does everything the three models share: timing, VRAM, file naming,
and the run files in docs/findings/voice-cloning/. Console output is ASCII only.
"""

import argparse
import csv
import importlib
import platform
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import pynvml
import soundfile as sf
import torch

EVAL_DIR = Path(__file__).resolve().parent
REPO = EVAL_DIR.parents[1]
TEST_SET = REPO / "docs" / "test-sets" / "voice-cloning-8.tsv"
REF_TEXT = EVAL_DIR / "clip_a_transcript.txt"
FINDINGS = REPO / "docs" / "findings" / "voice-cloning"
# Thrown away: the first GPU call compiles kernels and is much slower than the rest.
WARMUP_TEXT, WARMUP_LANG = "यह एक छोटा परीक्षण है।", "hi"
SEED = 0  # same seed for every model, so a rerun gives comparable clips


def free_vram_mib() -> tuple[int, int]:
    """Whole-GPU free/total from NVML, the same numbers nvidia-smi shows.
    Unlike torch's counters this includes other programs (games, browsers)."""
    pynvml.nvmlInit()
    info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
    pynvml.nvmlShutdown()
    return info.free // 2**20, info.total // 2**20


def timed(fn, *args):
    """Wall-clock a GPU call. CUDA runs asynchronously: without synchronize()
    the timer would stop when work is queued, not when it has finished."""
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    result = fn(*args)
    torch.cuda.synchronize()
    return result, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model folder name, e.g. xtts")
    ap.add_argument("--ref", required=True, type=Path, help="clip A wav")
    args = ap.parse_args()

    sys.path.insert(0, str(EVAL_DIR / args.model))
    synth_mod = importlib.import_module("synth")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = EVAL_DIR / "audio" / "out" / args.model / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    FINDINGS.mkdir(parents=True, exist_ok=True)
    ref_text = REF_TEXT.read_text(encoding="utf-8").strip()
    with TEST_SET.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    free0, total = free_vram_mib()
    print(f"[{args.model}] free VRAM at start: {free0} / {total} MiB")
    torch.manual_seed(SEED)

    state, load_s = timed(synth_mod.load, args.ref.resolve(), ref_text, "cuda")
    print(f"[{args.model}] loaded + conditioned in {load_s:.1f} s")
    _, warmup_s = timed(synth_mod.synth, state, WARMUP_TEXT, WARMUP_LANG)
    print(f"[{args.model}] warm-up clip in {warmup_s:.1f} s (discarded)")

    results = []
    for row in rows:
        for lang in row["langs"].split(","):
            name = f"{row['id']}_{lang}"
            rec = {
                "id": row["id"],
                "kind": row["kind"],
                "lang": lang,
                "chars": len(row["text"]),
                "synth_ms": "",
                "audio_s": "",
                "rtf": "",
                "wav": "",
                "error": "",
            }
            try:
                (wave, rate), secs = timed(synth_mod.synth, state, row["text"], lang)
                path = out_dir / f"{name}.wav"
                sf.write(path, wave, rate, subtype="PCM_16")
                dur = len(wave) / rate
                # Real-time factor: seconds of compute per second of audio. Below 1 = faster than real time.
                rec.update(
                    synth_ms=round(secs * 1000),
                    audio_s=round(dur, 2),
                    rtf=round(secs / dur, 3) if dur else "",
                    wav=path.relative_to(REPO).as_posix(),
                )
                print(
                    f"  {name:<8} {secs * 1000:7.0f} ms  audio {dur:5.2f} s  rtf {rec['rtf']}"
                )
            except Exception as exc:  # one failing clip must not end the run
                rec["error"] = f"{type(exc).__name__}: {exc}".encode(
                    "ascii", "replace"
                ).decode()[:300]
                print(f"  {name:<8} ERROR {rec['error'][:120]}")
                traceback.print_exc(file=sys.stderr)
            results.append(rec)

    peak_alloc = torch.cuda.max_memory_allocated() // 2**20
    peak_res = torch.cuda.max_memory_reserved() // 2**20

    tsv = FINDINGS / f"{args.model}_run_{stamp}.tsv"
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=list(results[0]), delimiter="\t", lineterminator="\n"
        )
        w.writeheader()
        w.writerows(results)

    ok = [r for r in results if not r["error"]]
    rtfs = sorted(r["rtf"] for r in ok if r["rtf"] != "")
    summary = [
        f"model: {args.model}",
        f"run: {stamp}",
        f"python {platform.python_version()} | torch {torch.__version__} | {torch.cuda.get_device_name(0)}",
        f"package: {getattr(synth_mod, 'PACKAGE_INFO', 'n/a')}",
        f"reference: {args.ref.name} ({sf.info(str(args.ref)).duration:.2f} s)",
        f"free_vram_at_start_mib: {free0} of {total}",
        f"load_and_condition_s: {load_s:.2f}",
        f"warmup_s: {warmup_s:.2f}",
        f"peak_vram_allocated_mib: {peak_alloc}",
        f"peak_vram_reserved_mib: {peak_res}",
        f"clips_ok: {len(ok)} of {len(results)}",
        f"rtf_median: {rtfs[len(rtfs) // 2] if rtfs else 'n/a'}",
        f"rtf_max: {rtfs[-1] if rtfs else 'n/a'}",
        f"per_clip: {tsv.name}",
    ]
    (FINDINGS / f"{args.model}_run_{stamp}.txt").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
