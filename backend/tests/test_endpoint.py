"""Tests for vaani.endpoint: turn boundaries, pre-roll, and the length cap.

Events come from the real Hysteresis class fed plain True/False frames, so
they are exactly what VAD would emit (speech_started on the 4th speech frame,
speech_ended on the 10th silent one) without depending on the model.

Each "frame" is its own index as 4 bytes. The endpointer treats frames as
opaque bytes, so this lets a test decode turn.audio back into the exact list
of frame indexes it contains.
"""

from vaani.config import EndpointSettings
from vaani.endpoint import Endpointer, TurnEnded, ms_to_frames
from vaani.vad import Hysteresis

FRAME_MS = 20
START_N, END_M = 4, 10  # VAD hysteresis, as in config.toml
CFG = EndpointSettings()  # 700 ms silence, 40 ms min, 300 ms pre-roll, 30 s max
SILENCE_FRAMES = 35  # 700 / 20
PREROLL = 15  # 300 / 20

S, Q = True, False  # a speech frame, a quiet frame


def tag(i: int) -> bytes:
    return i.to_bytes(4, "little")


def frames_in(turn: TurnEnded) -> list[int]:
    a = turn.audio
    return [int.from_bytes(a[k : k + 4], "little") for k in range(0, len(a), 4)]


def run(
    pattern: list[bool], cfg: EndpointSettings = CFG
) -> list[tuple[int, TurnEnded]]:
    """Push the pattern through Hysteresis + Endpointer.

    Returns (frame index at which turn_ended fired, the turn) for each turn.
    """
    vad = Hysteresis(START_N, END_M)
    ep = Endpointer(cfg, FRAME_MS, 0.5)
    out = []
    for i, is_speech in enumerate(pattern):
        event = vad.update(is_speech, i, float(i))
        turn = ep.push(tag(i), event, 1.0 if is_speech else 0.0)
        if turn is not None:
            out.append((i, turn))
    return out


def test_short_pause_inside_speech_does_not_end_the_turn() -> None:
    # 400 ms pause: VAD fires speech_ended (it needs only 200 ms), but speech
    # comes back well inside the 700 ms window.
    turns = run([Q] * 20 + [S] * 30 + [Q] * 20 + [S] * 30 + [Q] * 60)
    assert len(turns) == 1
    _, turn = turns[0]
    assert turn.start_frame == 20 + START_N - 1  # first speech_started
    assert turn.end_frame == 100 + END_M - 1  # LAST speech_ended


def test_long_pause_ends_the_turn_exactly_when_the_window_closes() -> None:
    speech_ended = 50 + END_M - 1
    pattern = [Q] * 20 + [S] * 30 + [Q] * 60
    turns = run(pattern)
    assert len(turns) == 1
    fired_at, turn = turns[0]
    assert fired_at == speech_ended + SILENCE_FRAMES
    assert turn.duration_ms == (speech_ended - 23 + 1) * FRAME_MS
    assert not turn.forced
    # One frame short of the window: no turn yet.
    assert run(pattern[: speech_ended + SILENCE_FRAMES]) == []


def test_speech_shorter_than_min_utterance_makes_no_turn() -> None:
    # 4 speech frames: speech_started on the 4th, so 1 voiced frame counted,
    # under the default's 2 (40 ms).
    assert run([Q] * 20 + [S] * 4 + [Q] * 80) == []


def test_min_utterance_counts_voiced_frames_from_speech_started_only() -> None:
    # Counted from the speech_started frame (the 4th real speech frame) to the
    # last voiced frame. Neither the 3 voiced frames before it (they are in
    # the pre-roll) nor VAD's 10 silent frames before speech_ended count.
    # So 5 real frames (100 ms) -> 2 voiced (40 ms), kept.
    ((_, turn),) = run([Q] * 20 + [S] * 5 + [Q] * 80)
    assert turn.voiced_frames == 2
    # The span (speech_started..speech_ended) is still what duration_ms says.
    assert turn.duration_ms == (2 + END_M) * FRAME_MS
    # Raised to 300 ms (15 frames), it takes 18 real frames to pass.
    cfg = EndpointSettings(min_utterance_ms=300)
    assert run([Q] * 20 + [S] * 17 + [Q] * 80, cfg) == []
    assert len(run([Q] * 20 + [S] * 18 + [Q] * 80, cfg)) == 1


def test_quiet_frames_inside_speech_do_not_count_as_voiced() -> None:
    # The no-regression case. A 3-frame dip ("o-k") is too short for
    # speech_ended; its frames are not voiced. The tightest such word the old
    # 300 ms span rule kept: speech_started 23, last voiced frame 27,
    # speech_ended 37, a span of 15. It has 2 voiced frames (23 and 27), so
    # the 40 ms default keeps it too.
    pattern = [Q] * 20 + [S] * 4 + [Q] * 3 + [S] * 1 + [Q] * 80
    ((_, turn),) = run(pattern)
    assert turn.voiced_frames == 2
    assert turn.duration_ms == 15 * FRAME_MS  # what the old rule measured


def test_a_blip_in_the_silence_window_is_not_part_of_the_utterance() -> None:
    # After speech_ended, 3 speech frames (too few for speech_started) inside
    # the window: the turn still ends at the first speech_ended and the blip
    # adds nothing to its voiced count.
    speech = [Q] * 20 + [S] * 30 + [Q] * 15 + [S] * 3 + [Q] * 80
    ((_, turn),) = run(speech)
    assert turn.end_frame == 50 + END_M - 1
    assert turn.voiced_frames == 30 - (START_N - 1)


def test_speech_resuming_in_the_window_cancels_the_pending_end() -> None:
    # Pause of 30 frames: speech_ended at +10, speech_started again at +33,
    # i.e. 23 frames into the 35-frame window.
    turns = run([Q] * 20 + [S] * 30 + [Q] * 30 + [S] * 30 + [Q] * 60)
    assert len(turns) == 1
    _, turn = turns[0]
    # One continuous utterance: the pause frames are inside it, no gaps.
    got = frames_in(turn)
    assert got == list(range(got[0], turn.end_frame + 1))


def test_utterance_audio_includes_the_preroll() -> None:
    ((_, turn),) = run([Q] * 20 + [S] * 30 + [Q] * 60)
    start = turn.start_frame
    assert frames_in(turn) == list(range(start - PREROLL, turn.end_frame + 1))
    # The pre-roll reaches back past the 3 speech frames VAD needed before it
    # confirmed speech_started, to the real start (frame 20) and beyond.
    assert frames_in(turn)[0] < 20
    assert turn.frame_count == PREROLL + turn.end_frame - start + 1


def test_back_to_back_utterances_make_two_turns_with_correct_bounds() -> None:
    pattern = [Q] * 20 + [S] * 30 + [Q] * 50 + [S] * 40 + [Q] * 60
    turns = run(pattern)
    assert len(turns) == 2
    (_, first), (_, second) = turns
    assert (first.start_frame, first.end_frame) == (23, 59)
    assert (second.start_frame, second.end_frame) == (103, 149)
    # The second pre-roll is the silence just before it, not the first turn.
    assert frames_in(second) == list(range(103 - PREROLL, 150))
    assert frames_in(first)[-1] < frames_in(second)[0]


def test_exceeding_max_utterance_forces_a_turn_end() -> None:
    cfg = EndpointSettings(max_utterance_ms=1000)  # 50 frames
    turns = run([Q] * 20 + [S] * 90 + [Q] * 60, cfg)  # 1.8 s of speech
    assert len(turns) == 2
    (fired, forced), (_, rest) = turns
    assert forced.forced and forced.speech_ended_at is None
    assert (forced.start_frame, forced.end_frame) == (23, 72)
    assert fired == 72
    # Buffer stayed bounded: pre-roll + exactly the 50-frame cap.
    assert forced.frame_count == PREROLL + 50
    # Still talking: the next frame starts the next utterance, no gap, and no
    # pre-roll (it would duplicate audio the forced turn already has).
    assert rest.start_frame == 73 and not rest.forced
    assert frames_in(rest)[0] == 73


def test_cap_is_not_applied_during_the_silence_window() -> None:
    cfg = EndpointSettings(max_utterance_ms=1000)  # 50 frames
    # 42 frames from speech_started to speech_ended (23..64), then the window
    # pushes the buffer past 50. That is a normal end, not a forced one: the
    # window itself is bounded (35 frames), so memory still is.
    ((fired, turn),) = run([Q] * 20 + [S] * 35 + [Q] * 60, cfg)
    assert not turn.forced
    assert turn.end_frame == 64 and fired == 64 + SILENCE_FRAMES


def test_ms_to_frames_rounds_up() -> None:
    assert ms_to_frames(700, 20) == 35
    assert ms_to_frames(710, 20) == 36
