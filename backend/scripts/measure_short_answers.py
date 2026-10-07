"""Voiced frames of short answers, through the real VAD and endpointer.

Which min_utterance_ms keeps "haan", "nahi", "ji" and "ok" as turns and
drops "hmm"? Since day 14 the endpointer compares min_utterance_ms with the
VOICED frames counted from speech_started (endpoint.py), so this script
reports exactly that count for each word, as TurnEnded.voiced_frames.

The recording (record_fixture.ps1 -Out ...) is: haan, nahi, ji, ok, hmm, said
twice in that order, with about 2 s of silence between words. It goes through
VadStream and Endpointer as the gateway calls them, with min_utterance_ms set
to 0 so that every utterance comes out as a turn and can be counted. CPU
only, no model calls.

Run from backend/ (output also goes to docs/findings/tuning/):
    uv run python scripts/measure_short_answers.py tests/fixtures/short_answers_16k.wav
"""

import argparse
import wave
from pathlib import Path

from run_log import TUNING, RunLog  # scripts/ is on sys.path when run as a file

from vaani.config import get_settings
from vaani.endpoint import Endpointer, TurnEnded
from vaani.gateway import expected_frame_bytes
from vaani.vad import VadStream, load_model

WORDS = ["haan", "nahi", "ji", "ok", "hmm"] * 2
KEEP = {"haan", "nahi", "ji", "ok"}  # must stay turns; "hmm" must not


def utterances(path: Path) -> list[TurnEnded]:
    settings = get_settings()
    frame_ms = settings.audio.frame_ms
    frame_bytes = expected_frame_bytes(settings.audio)
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == settings.audio.sample_rate
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        pcm = wav.readframes(wav.getnframes())
    frames = [
        pcm[i : i + frame_bytes]
        for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes)
    ]
    frames += [b"\x00" * frame_bytes] * round(2000 / frame_ms)  # let the last end
    cfg = settings.endpoint.model_copy(update={"min_utterance_ms": 0})
    model = load_model(settings.vad.model_path, settings.vad.model_sha256)
    vad = VadStream(model, settings.vad, settings.audio)
    endpointer = Endpointer(cfg, frame_ms, settings.vad.threshold)
    turns = []
    for frame in frames:
        event = vad.push(frame)
        if (turn := endpointer.push(frame, event, vad.probability)) is not None:
            turns.append(turn)
    return turns


def main(path: Path) -> None:
    log = RunLog("measure_short_answers", out=TUNING)
    settings = get_settings()
    frame_ms = settings.audio.frame_ms
    log(
        f"clip {path.name}; [vad] threshold {settings.vad.threshold}, "
        f"start_frames {settings.vad.start_frames}, end_frames "
        f"{settings.vad.end_frames}; committed min_utterance_ms "
        f"{settings.endpoint.min_utterance_ms}"
    )
    turns = utterances(path)
    labelled = len(turns) == len(WORDS)
    if not labelled:
        log(
            f"WARNING: {len(turns)} utterances, expected {len(WORDS)}: "
            "words cannot be matched to utterances, no value is chosen"
        )
    log("\n  #  word   start s  voiced frames  voiced ms  span ms")
    for n, turn in enumerate(turns):
        word = WORDS[n] if labelled else "?"
        log(
            f"{n + 1:>3}  {word:<5} {turn.start_frame * frame_ms / 1000:>8.2f}"
            f"  {turn.voiced_frames:>13}  {turn.voiced_frames * frame_ms:>9}"
            f"  {turn.duration_ms:>7}"
        )
    if not labelled:
        return

    keep = [t.voiced_frames for t, w in zip(turns, WORDS, strict=True) if w in KEEP]
    drop = [t.voiced_frames for t, w in zip(turns, WORDS, strict=True) if w not in KEEP]
    # min_utterance_ms keeps a turn when voiced_frames >= ms_to_frames(value),
    # so in frames, any minimum in (max(drop), min(keep)] separates them.
    low, high = max(drop) + 1, min(keep)
    if low <= high:
        log(
            f"\nseparating values: {low * frame_ms} to {high * frame_ms} ms "
            f"(fewest voiced frames kept: {high}, most dropped: {low - 1})"
        )
    else:
        log("\nno value keeps every haan/nahi/ji/ok and drops every hmm")
    committed = settings.endpoint.min_utterance_ms
    lost = [
        f"{w} #{n + 1} ({t.voiced_frames * frame_ms} ms)"
        for n, (t, w) in enumerate(zip(turns, WORDS, strict=True))
        if (w in KEEP) == (t.voiced_frames * frame_ms < committed)
    ]
    log(
        f"at the committed {committed} ms, wrongly kept or dropped: "
        f"{', '.join(lost) or 'none'}"
    )
    log(f"\nwrote {log.path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", type=Path, help="16 kHz mono 16-bit WAV")
    main(parser.parse_args().wav)
