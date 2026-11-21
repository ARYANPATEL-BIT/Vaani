"""Speaker similarity of every clip in a run, against the held-out clip B.

Usage (from tools/voice_clone_eval/score):
    uv run python score.py --run ../../../docs/findings/voice-cloning/<run>_run_<stamp>.tsv \
        --ref-b ../audio/reference/clip_b_take1.wav --ref-a ../audio/reference/clip_a_take1.wav

Writes <run>_similarity_<stamp>.tsv next to the run file and prints ASCII only.
Calibration points are added so a score can be read on this model's scale:
  ceiling  = the --ref-a clip vs real clip B (same person, two recordings)
  floor    = each Piper voice in docs/findings/persona-voices vs clip B (other speakers)
  impostor = each audio/reference/impostor_take*.wav vs clip B (a real second
             person), added once `record_reference.py impostor` has been run.
             Piper voices are synthetic, so they are a weak floor; a real
             person is the honest one.
"""

import argparse
import csv
import statistics
import sys
from pathlib import Path

import speaker

REPO = Path(__file__).resolve().parents[3]
IMPOSTORS = sorted((REPO / "docs" / "findings" / "persona-voices").glob("*.wav"))
PEOPLE = sorted(
    (REPO / "tools" / "voice_clone_eval" / "audio" / "reference").glob(
        "impostor_take*.wav"
    )
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--ref-a", required=True, type=Path)
    ap.add_argument("--ref-b", required=True, type=Path)
    args = ap.parse_args()

    enc = speaker.load_encoder("cpu")
    b = speaker.embed_file(enc, args.ref_b)
    ceiling = speaker.cosine(speaker.embed_file(enc, args.ref_a), b)
    floors = [speaker.cosine(speaker.embed_file(enc, p), b) for p in IMPOSTORS]
    people = [speaker.cosine(speaker.embed_file(enc, p), b) for p in PEOPLE]

    with args.run.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    out = []
    for r in rows:
        sim = (
            ""
            if r["error"]
            else round(speaker.cosine(speaker.embed_file(enc, REPO / r["wav"]), b), 4)
        )
        out.append(
            {"id": r["id"], "lang": r["lang"], "similarity_to_b": sim, "wav": r["wav"]}
        )
        print(f"  {r['id']}_{r['lang']:<3} {sim}")

    sims = [o["similarity_to_b"] for o in out if o["similarity_to_b"] != ""]
    dest = args.run.with_name(args.run.name.replace("_run_", "_similarity_"))
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=list(out[0]), delimiter="\t", lineterminator="\n"
        )
        w.writeheader()
        w.writerows(out)
        # Summary rows at the end, so one file holds the clip scores and their scale.
        f.write(f"# ceiling_real_a_vs_real_b\t{ceiling:.4f}\n")
        f.write(
            f"# floor_piper_voices_vs_b_max\t{max(floors):.4f}\t(n={len(floors)})\n"
        )
        if people:
            f.write(
                f"# floor_impostor_vs_b_max\t{max(people):.4f}\t(n={len(people)})\n"
            )
        if sims:
            f.write(
                f"# clips_mean\t{statistics.mean(sims):.4f}\n# clips_min\t{min(sims):.4f}\n"
            )
    print(f"ceiling (real A vs real B): {ceiling:.4f}")
    print(f"floor (max Piper voice vs B, n={len(floors)}): {max(floors):.4f}")
    if people:
        print(f"floor (max impostor take vs B, n={len(people)}): {max(people):.4f}")
    else:
        print("floor (impostor): no impostor_take*.wav yet, Piper floor only")
    if sims:
        print(
            f"clips mean {statistics.mean(sims):.4f}  min {min(sims):.4f}  (n={len(sims)})"
        )
    print("written:", dest.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
