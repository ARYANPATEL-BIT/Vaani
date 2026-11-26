"""The pure parts: sentence split, language per sentence, SNR, decoding."""

import io

import av
import numpy as np
import pytest

from tests.conftest import speech_like, wav_bytes
from voice_studio.audio_checks import AudioError, decode, snr_db
from voice_studio.script import ScriptError, join, plan
from voice_studio.verify import new_challenge, phrase_match

DANDA = "\u0964"
NAMASTE = "\u0928\u092e\u0938\u094d\u0924\u0947"


def test_split_on_full_stops_questions_and_dandas():
    script = f"One. Two? {NAMASTE}{DANDA} {NAMASTE} ok{DANDA} Three!"
    assert [s for s, _ in plan(script, 500, 250)] == [
        "One.",
        "Two?",
        f"{NAMASTE}{DANDA}",
        f"{NAMASTE} ok{DANDA}",
        "Three!",
    ]


def test_language_is_hi_if_any_devanagari():
    langs = [
        lang for _, lang in plan(f"Plain English. Mixed {NAMASTE} text.", 500, 250)
    ]
    assert langs == ["en", "hi"]


def test_a_line_break_ends_a_sentence():
    assert [s for s, _ in plan("no stop here\nnext line", 500, 250)] == [
        "no stop here",
        "next line",
    ]


def test_caps():
    with pytest.raises(ScriptError) as total:
        plan("x" * 11, 10, 10)
    assert total.value.code == "STUDIO_SCRIPT_TOO_LONG"
    with pytest.raises(ScriptError) as one:
        plan("short. " + "y" * 30, 100, 20)
    assert one.value.code == "STUDIO_SENTENCE_TOO_LONG"


def test_join_puts_silence_between_sentences():
    joined = join([np.ones(100), np.ones(100)], rate=1000, gap_ms=50)
    assert len(joined) == 250
    assert joined[100:150].max() == 0


def test_snr_separates_quiet_room_from_noisy_room():
    assert snr_db(speech_like(10, 16_000), 16_000) > 40
    assert snr_db(speech_like(10, 16_000, noise=0.08), 16_000) < 20


def test_decode_resamples_a_wav():
    samples = decode(wav_bytes(speech_like(2.0, 48_000), 48_000), 16_000)
    assert abs(len(samples) - 32_000) < 200


def test_decode_reads_the_browsers_webm_opus():
    # MediaRecorder in Chrome records WebM with Opus inside: make one here.
    buf = io.BytesIO()
    with av.open(buf, "w", format="webm") as out:
        stream = out.add_stream("libopus", rate=48_000, layout="mono")
        tone = speech_like(1.0, 48_000)
        frame = av.AudioFrame.from_ndarray(
            tone.reshape(1, -1), format="flt", layout="mono"
        )
        frame.sample_rate = 48_000
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    samples = decode(buf.getvalue(), 16_000)
    assert abs(len(samples) / 16_000 - 1.0) < 0.1


def test_decode_refuses_garbage():
    with pytest.raises(AudioError):
        decode(b"\x00\x01 not audio", 16_000)


def test_challenge_words_are_distinct_and_from_the_list():
    words = ["a", "b", "c", "d", "e", "f"]
    phrase = new_challenge(words, 5).phrase.split()
    assert len(set(phrase)) == 5 and set(phrase) <= set(words)


def test_phrase_match_ignores_case_and_punctuation():
    assert phrase_match("river tiger lemon", "River, tiger... LEMON!") == 1.0
    assert phrase_match("river tiger lemon", "river") == pytest.approx(1 / 3)
