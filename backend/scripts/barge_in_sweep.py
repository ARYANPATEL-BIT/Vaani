"""What would other barge-in settings have done? Replay logged speech through
the real BargeIn.

While the agent thinks or speaks, every speech VAD reports is judged by
BargeIn (barge_in.py), and each judged speech writes one DEBUG line: its
outcome and the speech probability of every frame from speech_started on.
The runs it is built for (A2 and B, pending since day 14) set min_speech_ms
to 2000, so judging goes on to the end of almost every speech, and the lines
hold whole sequences. Checked so far only on synthetic lines. This script feeds
those sequences, frame by frame, through the REAL BargeIn at other
min_speech_ms and threshold values, so nothing about the rule is copied here.

Two inputs:
  --echo    run A2: speakers on, nobody talking while the agent spoke. Every
            interruption here is the agent hearing itself: a FALSE stop.
  --speech  run B: the user really talked over the agent.

For each (threshold, min_speech_ms): false stops per minute of agent speech
(A2); for B, how many speeches stop the agent, the judging time (audio from
speech_started to the decision; the server adds ~1 ms of stopping), and how
many of those stops were for nothing: the new turn then has too few voiced
frames for min_utterance_ms and is discarded. That last count replays the
frames through the real Endpointer too.

Each input may be a server log or an episodes file this script wrote. A server
log is first reduced to an episodes file in docs/findings/tuning/: the agent's
speaking time and the judged lines, nothing else. The sweep then reproduces
from the repo alone:
    uv run python scripts/barge_in_sweep.py --echo <A2 log> --speech <B log>
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from run_log import TUNING, RunLog  # scripts/ is on sys.path when run as a file

from vaani.barge_in import BargeIn
from vaani.config import BargeInSettings, get_settings
from vaani.endpoint import Endpointer
from vaani.vad import SPEECH_ENDED, SPEECH_STARTED, Hysteresis, SpeechEvent

THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]
MIN_SPEECH_MS = [100, 140, 200, 300]

JUDGED = re.compile(r"judged speech: (\w+) after \d+ frames; probabilities ([\d. ]+)")
# Server logs are run with a "%(relativeCreated)d" (ms) prefix on each line.
STATE = re.compile(r"^(\d+) .*: (\w+) -> (\w+)$")


@dataclass
class Episode:
    outcome: str  # noise (ended by speech_ended), interruption, undecided
    probs: list[float]


@dataclass
class Run:
    speaking_s: float
    episodes: list[Episode]


def read(path: Path, label: str, log: RunLog) -> Run:
    """Read a server log or an episodes file; reduce a log to an episodes file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    episodes = [
        Episode(m[1], [float(p) for p in m[2].split()])
        for line in lines
        if (m := JUDGED.search(line))
    ]
    if lines and lines[0].startswith("speaking_s "):
        return Run(float(lines[0].split()[1]), episodes)
    # Time spent `speaking`, from the timestamped state changes.
    speaking_ms, since = 0, None
    for line in lines:
        if m := STATE.match(line):
            at, old, new = int(m[1]), m[2], m[3]
            if old == "speaking" and since is not None:
                speaking_ms += at - since
            since = at if new == "speaking" else since
    run = Run(speaking_ms / 1000, episodes)
    out = TUNING / f"barge_in_episodes_{label}_{log.stamp}.txt"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"speaking_s {run.speaking_s:.1f}\n")
        f.write(f"source {path.name}\n")
        for line in lines:
            if m := JUDGED.search(line):
                f.write(m[0] + "\n")
    log(f"{label}: wrote {out.name} from {path.name}")
    return run


def fires(ep: Episode, min_ms: int, threshold: float) -> int | None:
    """Frame (from speech_started = 0) at which the real BargeIn fires."""
    s = get_settings()
    cfg = BargeInSettings(min_speech_ms=min_ms, threshold=threshold)
    judge = BargeIn(cfg, s.vad, s.audio.frame_ms)
    last = len(ep.probs) - 1
    for k, p in enumerate(ep.probs):
        event = None
        if k == 0:
            event = SpeechEvent(SPEECH_STARTED, k, 0.0)
        elif k == last and ep.outcome == "noise":
            event = SpeechEvent(SPEECH_ENDED, k, 0.0)
        if judge.push(b"", event, p):
            return k
    return None


def discarded(ep: Episode) -> bool | None:
    """Would the real Endpointer discard this speech as a turn (too few voiced
    frames)? None when unknown: the sequence was cut off and the replay says
    discard, but the real speech may have gone on."""
    s = get_settings()
    vad, frame_ms = s.vad, s.audio.frame_ms
    hysteresis = Hysteresis(vad.start_frames, vad.end_frames)
    endpointer = Endpointer(s.endpoint, frame_ms, vad.threshold)
    # The speech run VAD needed before speech_started (pre-roll, never
    # counted), the logged frames, then 5 s of silence: far longer than VAD's
    # end_frames plus end_of_turn_silence_ms, so the utterance always ends.
    lead = [1.0] * (vad.start_frames - 1)
    tail = [0.0] * (5000 // frame_ms)
    for i, p in enumerate(lead + ep.probs + tail):
        event = hysteresis.update(p >= vad.threshold, i, 0.0)
        was_open = endpointer.utterance_open
        if endpointer.push(b"", event, p) is not None:
            return False
        if was_open and not endpointer.utterance_open:
            return True if ep.outcome == "noise" else None
    raise AssertionError("the silence tail always ends the utterance")


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def describe(label: str, run: Run, log: RunLog) -> None:
    frames = [p for ep in run.episodes for p in ep.probs[1:]]  # after onset
    outcomes = {
        o: sum(e.outcome == o for e in run.episodes)
        for o in ("noise", "interruption", "undecided")
    }
    log(
        f"\n{label}: {len(run.episodes)} judged speeches {outcomes}, "
        f"agent speaking {run.speaking_s:.1f} s (server's play-out estimate)"
    )
    if not frames:
        return
    log(
        f"  frame probability after speech_started: p10 {pct(frames, 0.1):.2f}, "
        f"p50 {pct(frames, 0.5):.2f}, p90 {pct(frames, 0.9):.2f} "
        f"over {len(frames)} frames"
    )
    share = "  ".join(
        f">={t}: {sum(p >= t for p in frames) / len(frames):.0%}" for t in THRESHOLDS
    )
    log(f"  share of frames {share}")
    peaks = sorted(max(ep.probs) for ep in run.episodes)
    log(f"  peak probability per speech: {' '.join(f'{p:.2f}' for p in peaks)}")


def main(echo_path: Path, speech_path: Path) -> None:
    log = RunLog("barge_in_sweep", out=TUNING)
    frame_ms = get_settings().audio.frame_ms
    echo = read(echo_path, "A2", log)
    speech = read(speech_path, "B", log)
    describe("A2 echo (nobody talking)", echo, log)
    describe("B real speech", speech, log)

    minutes = echo.speaking_s / 60
    log(
        "\nthr   min ms | A2 false stops  per min | B stops  undecided  "
        "judging p50 ms  stopped for nothing"
    )
    for threshold in THRESHOLDS:
        for min_ms in MIN_SPEECH_MS:
            false = sum(
                fires(ep, min_ms, threshold) is not None for ep in echo.episodes
            )
            fired = [(ep, fires(ep, min_ms, threshold)) for ep in speech.episodes]
            hits = [k for _, k in fired if k is not None]
            # Cut off before this value was reached: would it have fired?
            unknown = sum(k is None and ep.outcome != "noise" for ep, k in fired)
            verdicts = [discarded(ep) for ep, k in fired if k is not None]
            judging = f"{median(hits) * frame_ms:.0f}" if hits else "-"
            rate = f"{false / minutes:.2f}" if minutes else "-"
            log(
                f"{threshold:.1f}  {min_ms:>6} | {false:>14}  {rate:>7} | "
                f"{len(hits):>3}/{len(speech.episodes):<3} {unknown:>9}  "
                f"{judging:>14}  {verdicts.count(True)} "
                f"(+{verdicts.count(None)} unknown)"
            )
    log(f"\nwrote {log.path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--echo", type=Path, required=True, help="run A2 input")
    parser.add_argument("--speech", type=Path, required=True, help="run B input")
    args = parser.parse_args()
    main(args.echo, args.speech)
