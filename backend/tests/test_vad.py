"""Tests for vaani.vad: hysteresis, the real Silero model, and session isolation.

Hysteresis tests feed plain True/False frames, so they are exact and do not
depend on the model. The model tests use the real ONNX file and a recorded
speech clip (tests/fixtures/speech_16k_mono.wav): Silero is trained to reject
tones and synthetic vowels, so a tone cannot stand in for speech.
"""

import math
import struct
import wave
from pathlib import Path

import pytest

from vaani.config import Settings
from vaani.gateway import expected_frame_bytes
from vaani.vad import (
    SPEECH_ENDED,
    SPEECH_STARTED,
    Hysteresis,
    VadStream,
    load_model,
)

SETTINGS = Settings()
FRAME_BYTES = expected_frame_bytes(SETTINGS.audio)
SILENCE = b"\x00" * FRAME_BYTES
FIXTURE = Path(__file__).parent / "fixtures" / "speech_16k_mono.wav"
START_N = 4  # values used by the hysteresis-only tests
END_M = 10


def speech_frames() -> list[bytes]:
    """The fixture clip split into protocol-sized frames."""
    with wave.open(str(FIXTURE), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    return [
        pcm[i : i + FRAME_BYTES]
        for i in range(0, len(pcm) - FRAME_BYTES + 1, FRAME_BYTES)
    ]


def tone_frames(count: int, hz: float = 440.0) -> list[bytes]:
    """A continuous 0.3-amplitude sine, as fake_client used to send."""
    per_frame = FRAME_BYTES // 2
    out = []
    for f in range(count):
        samples = (
            int(0.3 * 32767 * math.sin(2 * math.pi * hz * (f * per_frame + i) / 16000))
            for i in range(per_frame)
        )
        out.append(struct.pack(f"<{per_frame}h", *samples))
    return out


def new_stream() -> VadStream:
    model = load_model(SETTINGS.vad.model_path, SETTINGS.vad.model_sha256)
    return VadStream(model, SETTINGS.vad, SETTINGS.audio)


def run_hysteresis(pattern: list[bool]) -> list:
    h = Hysteresis(START_N, END_M)
    events = (h.update(s, i, 0.0) for i, s in enumerate(pattern))
    return [e for e in events if e is not None]


# --- Hysteresis (no model) -------------------------------------------------


def test_isolated_speech_frame_does_not_start_speech() -> None:
    assert run_hysteresis([False] * 20 + [True] + [False] * 20) == []


def test_run_one_short_of_start_frames_does_not_start_speech() -> None:
    pattern = [False] * 5 + [True] * (START_N - 1) + [False] * 20
    assert run_hysteresis(pattern) == []


def test_speech_started_fires_once_while_speech_continues() -> None:
    events = run_hysteresis([False] * 5 + [True] * 200)
    assert [e.kind for e in events] == [SPEECH_STARTED]
    # Confirmed by the Nth consecutive speech frame: index 5 + N - 1.
    assert events[0].frame_index == 5 + START_N - 1


def test_speech_ended_fires_after_configured_silence_run() -> None:
    pattern = [True] * 10 + [False] * END_M
    events = run_hysteresis(pattern)
    assert [e.kind for e in events] == [SPEECH_STARTED, SPEECH_ENDED]
    assert events[1].frame_index == 10 + END_M - 1


def test_short_pause_does_not_end_speech() -> None:
    pattern = [True] * 10 + [False] * (END_M - 1) + [True] * 10
    assert [e.kind for e in run_hysteresis(pattern)] == [SPEECH_STARTED]


# --- Real model ------------------------------------------------------------


def test_silence_produces_no_speech() -> None:
    vad = new_stream()
    events = [vad.push(SILENCE) for _ in range(250)]  # 5 s
    assert all(e is None for e in events)
    assert vad.probability < SETTINGS.vad.threshold


def test_speech_clip_produces_speech_then_ends_in_silence() -> None:
    vad = new_stream()
    frames = speech_frames() + [SILENCE] * 50  # clip, then 1 s of silence
    kinds = [e.kind for f in frames if (e := vad.push(f)) is not None]
    # The clip has pauses between phrases, so there may be several pairs, but
    # they must alternate, start with a start, and end with an end.
    assert kinds[0] == SPEECH_STARTED and kinds[-1] == SPEECH_ENDED
    assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False))


def test_pure_tone_is_not_speech() -> None:
    """Documents why fake_client sends a clip: Silero rejects a steady tone."""
    vad = new_stream()
    assert all(vad.push(f) is None for f in tone_frames(150))


def test_one_real_speech_frame_in_silence_does_not_start_speech() -> None:
    vad = new_stream()
    loud = speech_frames()[40]  # a frame from the middle of a word
    frames = [SILENCE] * 50 + [loud] + [SILENCE] * 50
    assert all(vad.push(f) is None for f in frames)


def test_two_sessions_sharing_the_model_do_not_affect_each_other() -> None:
    """Interleave a speech session and a silent session frame by frame on the
    one shared model; each must match what it produces when run alone."""
    speech = speech_frames()

    def solo(frames: list[bytes]) -> list[float]:
        vad = new_stream()
        return [(vad.push(f), vad.probability)[1] for f in frames]

    alone_a, alone_b = solo(speech), solo([SILENCE] * len(speech))

    a, b = new_stream(), new_stream()
    together_a, together_b = [], []
    for frame in speech:
        a.push(frame)
        b.push(SILENCE)
        together_a.append(a.probability)
        together_b.append(b.probability)

    assert together_a == alone_a
    assert together_b == alone_b


def test_model_is_loaded_once() -> None:
    cfg = SETTINGS.vad
    assert load_model(cfg.model_path, cfg.model_sha256) is load_model(
        cfg.model_path, cfg.model_sha256
    )


def test_wrong_checksum_is_refused() -> None:
    with pytest.raises(ValueError, match="sha256"):
        load_model.__wrapped__(SETTINGS.vad.model_path, "0" * 64)
