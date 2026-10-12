"""Barge-in: is the user's speech an interruption, and what did they hear?

While the agent is thinking or speaking, turns.py feeds every frame to
`BargeIn.push` instead of endpointing it. Two jobs, both without I/O:

1. JUDGE the speech. speech_started alone is not enough: VAD confirms it
   after 80 ms, and a click or a short cough gets that far. The speech must
   add up to [barge_in].min_speech_ms, counted from its onset (VAD's own 80 ms
   included), in frames whose speech probability reaches
   [barge_in].threshold. A speech_ended first means it was a noise: the
   reply goes on.

   It counts SPEECH FRAMES, not time since speech_started. VAD keeps saying
   "in speech" for 200 ms after the sound stops (end_frames), so a 100 ms
   cough would look like 300 ms of speech by the clock.

2. KEEP THE AUDIO. Every frame since speech_started is held, with its VAD
   event and speech probability. If the speech is an interruption, turns.py
   replays them into the endpointer, so the user's new turn starts at their
   first sound, not 200 ms in. If it was a noise, they go to the endpointer as silence.

Every judged speech, whatever its outcome, writes one DEBUG line with the
probability of each of its frames. Day 14's tuning runs switch it on, and
scripts/barge_in_sweep.py replays those lines through this class to show
what other min_speech_ms and threshold values would have done.

When it is one, turns.py calls `stop_reply` (steps 1 to 3 below), then
closes the agent's turn and opens the user's (steps 4 and 5, turns.py).
In a push-to-talk session (v0.9) the judge is not used: pressing speak while
the agent is busy calls the same `stop_reply`, with the press as the onset.

`heard_text` is the other half of a cut: from the play-out estimate of each
chunk sent (speaker.py), which part of the reply had the user heard when
audio.flush went out? Only that part goes into the conversation history.
"""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from vaani.config import BargeInSettings, VadSettings
from vaani.endpoint import ms_to_frames
from vaani.protocol import TurnState
from vaani.reply import Responder
from vaani.session import Session
from vaani.speaker import Spoken
from vaani.telemetry import BARGE_IN, Telemetry
from vaani.vad import SPEECH_ENDED, SPEECH_STARTED, SpeechEvent

log = logging.getLogger("vaani.barge_in")

SendJson = Callable[[dict], Awaitable[None]]

# One held frame: its bytes, the VAD event it produced (usually None) and
# its speech probability.
Held = tuple[bytes, SpeechEvent | None, float]


class BargeIn:
    """One session's interruption judge. Built by TurnPipeline."""

    def __init__(self, cfg: BargeInSettings, vad: VadSettings, frame_ms: int) -> None:
        self._needed = ms_to_frames(cfg.min_speech_ms, frame_ms)
        self._threshold = cfg.threshold
        # VAD saw this many speech frames in a row before it fired speech_started.
        self._start_frames = vad.start_frames
        self._held: list[Held] = []
        # The speech_started being judged, or None between speech.
        self.started: SpeechEvent | None = None
        self._speech = 0  # speech frames counted since the onset

    @property
    def judging(self) -> bool:
        """True while speech has started and is not yet decided."""
        return self.started is not None

    def push(self, frame: bytes, event: SpeechEvent | None, probability: float) -> bool:
        """Feed one frame. True when this frame makes the speech an interruption.

        Every frame is held until the caller takes it with `take`: between
        speech that is just this frame; while judging, the whole utterance.
        """
        self._held.append((frame, event, probability))
        if self.started is None:
            if event is None or event.kind != SPEECH_STARTED:
                return False
            self.started = event
            # VAD needed start_frames speech frames in a row to fire, so those
            # are already speech; this frame is the last of them.
            self._speech = self._start_frames
        elif event is not None and event.kind == SPEECH_ENDED:
            self.started = None  # it stopped short: a noise, not an interruption
            self._log_judged("noise")
            return False
        elif probability >= self._threshold:
            self._speech += 1
        if self._speech < self._needed:
            return False
        self._log_judged("interruption")
        return True

    def take(self) -> list[Held]:
        """Hand over every held frame, oldest first, and start afresh."""
        if self.started is not None and self._speech < self._needed:
            # Still undecided: the reply ended (or the session closed) first.
            self._log_judged("undecided")
        held, self._held = self._held, []
        self.started = None
        self._speech = 0
        return held

    def _log_judged(self, outcome: str) -> None:
        # Debug: off in normal runs. One line per judged speech, frames from
        # speech_started on. "noise" ends on its speech_ended frame; the other
        # two outcomes are cut off, so what came next is unknown.
        log.debug(
            "judged speech: %s after %d frames; probabilities %s",
            outcome,
            len(self._held),
            # 3 decimals: a frame is voiced at >= 0.5, so 2 would misplace
            # every probability from 0.495 to 0.4999 in a replay.
            " ".join(f"{p:.3f}" for _, _, p in self._held),
        )


def heard_text(spoken: list[Spoken], cut_at: float) -> str:
    """The part of the reply the user had heard at `cut_at`.

    Each chunk has an estimated play-out window on the server clock. A chunk
    that finished playing before the cut was heard whole. The chunk playing
    at the cut is cut by the share of its play-out time that had passed,
    then back to a whole word: half a word was not heard as a word. Chunks
    after it were not heard.

    An ESTIMATE. It assumes the browser plays each frame the moment it is
    sent, at the declared rate, without gaps, and that every character
    takes the same time to say. See docs/learning/backend-learning/13-barge-in.md.
    """
    words: list[str] = []
    for chunk in spoken:
        if cut_at >= chunk.end:
            words.append(chunk.text)
            continue
        if cut_at > chunk.start:
            share = (cut_at - chunk.start) / (chunk.end - chunk.start)
            cut = int(len(chunk.text) * share)
            part = chunk.text[:cut]
            if cut < len(chunk.text) and chunk.text[cut] != " ":
                part = part[: part.rfind(" ") + 1]  # "" if no whole word yet
            words.append(part.strip())
        break
    return " ".join(w for w in words if w)


async def stop_reply(
    responder: Responder,
    session: Session,
    telemetry: Telemetry,
    send_json: SendJson,
    onset_at: float,  # perf_counter of speech_started, or of a ptt.start
    state: TurnState,
) -> str:
    """Steps 1 to 3 of a barge-in on the current turn's reply.

    1. Stop playback: audio.flush is the first message out, because the
       user judges the interruption by when the speaker goes quiet.
    2. and 3. The reply's token ends the model's stream and drops a
       synthesis in flight; the reply task then ends on its own, unawaited.
    Then history: only what the user heard is recorded.

    Returns the words to carry into the next reply: the transcript if the
    user heard nothing, else "". Also "" when the reply never started; the
    transcript is then still being made, and turns.py carries it on arrival.
    """
    turn_id = session.current_turn_id
    assert turn_id is not None  # thinking and speaking belong to a turn
    triggered = telemetry.record(BARGE_IN, turn_id).at
    # The token FIRST, with no await before it: from this line not one more
    # frame of the reply can be sent. It is a flag, not a message, so
    # audio.flush is still the first thing the browser receives.
    responder.cancel()
    await session.flush(send_json, telemetry)
    cut_at = perf_counter()
    started = responder.turn_id == turn_id
    spoken = responder.speaker.spoken if started and responder.speaker else []
    heard = heard_text(spoken, cut_at)
    log.info(
        "session %s: barge-in on turn %s while %s, %d chars heard. SERVER-SIDE "
        "only, not PERF-3: onset -> audio.flush sent %.1f ms "
        "(judging %.1f ms, stopping %.1f ms)",
        session.session_id,
        turn_id,
        state,
        len(heard),
        (cut_at - onset_at) * 1000,
        (triggered - onset_at) * 1000,
        (cut_at - triggered) * 1000,
    )
    if not started:
        return ""
    if not heard:
        return responder.transcript
    responder.remember(responder.transcript, heard)
    return ""


def join_speech(first: str, second: str | None) -> str:
    """Two pieces of the user's speech as one text; either may be empty."""
    return " ".join(p.strip() for p in (first, second or "") if p and p.strip())
