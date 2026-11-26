"""Measure the two enrolment thresholds on real recordings: SNR and speaker match.

Usage (from studio/):
    uv run python scripts/calibrate.py

Writes docs/findings/voice-studio/calibration_<stamp>.txt and prints ASCII only.

Recordings used (none is committed audio of a person except as noted):
  noisy  - the voice-cloning spike's reference clips (the operator, through
           laptop AGC; gitignored, tools/voice_clone_eval/audio/reference/)
  clean  - backend/tests/fixtures/hinglish_real_16k.wav (the operator, per
           docs/findings/groq-stt/smoke_20261125.txt) and short_answers_16k.wav
           (recorded with record_fixture.ps1; speaker not documented)
  other  - synthetic voices: the Piper persona clips and the Windows SAPI
           fixture. A real second person was never recorded (no impostor clip
           exists), so "other" is a weak floor.

Each pair is scored whole-vs-whole and 4 s window vs whole: the live
challenge is a few seconds long, and a short clip gives a noisier embedding.
"""

import sys
import time
from itertools import combinations
from pathlib import Path

from voice_studio.audio_checks import decode, snr_db
from voice_studio.config import get_studio_settings
from voice_studio.model import ENCODER_RATE, SpeakerEncoder
from voice_studio.verify import cosine

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "backend/tests/fixtures"
GROUPS = {
    "noisy": sorted(
        (REPO / "tools/voice_clone_eval/audio/reference").glob("clip_*.wav")
    ),
    "clean": [FIXTURES / "hinglish_real_16k.wav", FIXTURES / "short_answers_16k.wav"],
    "other": sorted((REPO / "docs/findings/persona-voices").glob("*.wav"))
    + [FIXTURES / "speech_16k_mono.wav"],
}
WINDOW = int(4.0 * ENCODER_RATE)


def main() -> int:
    enc = SpeakerEncoder(get_studio_settings())
    clips = {
        group: {
            p.stem: decode(p.read_bytes(), ENCODER_RATE) for p in paths if p.exists()
        }
        for group, paths in GROUPS.items()
    }
    whole = {n: enc.embed(x) for g in clips.values() for n, x in g.items()}
    short = {n: enc.embed(x[:WINDOW]) for g in clips.values() for n, x in g.items()}
    out = [f"calibration {time.strftime('%Y%m%d-%H%M%S')}", "", "SNR (dB)"]
    for group, members in clips.items():
        for name, x in members.items():
            out.append(f"  {snr_db(x, ENCODER_RATE):6.1f}  {group:5}  {name}")

    def scores(pairs):
        values = []
        for a, b in pairs:
            values += [cosine(whole[a], whole[b]), cosine(short[a], whole[b])]
        return values

    def same(group):
        return list(combinations(sorted(clips[group]), 2))

    def cross(g1, g2):
        return [(a, b) for a in sorted(clips[g1]) for b in sorted(clips[g2])]

    rows = [
        ("same speaker, clean vs clean", scores(same("clean"))),
        ("same speaker, noisy vs noisy", scores(same("noisy"))),
        ("same speaker, clean vs noisy", scores(cross("clean", "noisy"))),
        ("other vs clean operator", scores(cross("other", "clean"))),
        ("other vs noisy operator", scores(cross("other", "noisy"))),
    ]
    out += ["", "Speaker similarity (cosine), whole and 4 s window, min / max (n)"]
    for label, values in rows:
        if values:
            out.append(
                f"  {min(values):.3f} / {max(values):.3f} (n={len(values)})  {label}"
            )
    dest = (
        REPO
        / "docs/findings/voice-studio"
        / f"calibration_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(out))
    print("written:", dest.relative_to(REPO).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
