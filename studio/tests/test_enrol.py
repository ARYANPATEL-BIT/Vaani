"""Enrolment: consent required, challenge required, SNR floor, both identity checks.

The invariant behind every rejection test: a refused enrolment stores nothing.
"""

import json
import time

import numpy as np

from tests.conftest import UID, speech_like, wav_bytes
from voice_studio.verify import Challenge


def stored(rig) -> list[str]:
    return sorted(p.name for p in rig.folder.iterdir()) if rig.folder.exists() else []


def test_enrolment_stores_sample_embedding_and_consent(rig):
    response = rig.enrol()
    assert response.status_code == 200, response.text
    assert response.json()["enrolled"] is True
    assert stored(rig) == ["consent.json", "embedding.npy", "reference.wav"]
    consent = json.loads((rig.folder / "consent.json").read_text(encoding="utf-8"))
    assert consent["consent_text"] == rig.cfg.consent_text  # word for word (ETH-3)
    assert consent["consented_at"].endswith("+00:00")  # a UTC timestamp
    assert consent["email"] == "me@example.com"
    assert rig.client.get("/studio/voice").json()["enrolled"] is True


def test_consent_is_required(rig):
    response = rig.enrol(consent="")
    assert response.status_code == 422
    assert response.json()["code"] == "STUDIO_CONSENT_REQUIRED"
    assert stored(rig) == []


def test_consent_text_must_be_the_exact_text(rig):
    response = rig.enrol(consent=rig.cfg.consent_text + " (edited)")
    assert response.json()["code"] == "STUDIO_CONSENT_REQUIRED"
    assert stored(rig) == []


def test_no_challenge_means_no_enrolment(rig):
    response = rig.client.post(
        "/studio/enrol",
        files={
            "sample": ("s.wav", wav_bytes(speech_like(15)), "audio/wav"),
            "challenge": ("c.wav", wav_bytes(speech_like(3)), "audio/wav"),
        },
        data={"consent_text": rig.cfg.consent_text},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STUDIO_NO_CHALLENGE"


def test_expired_challenge_is_refused(rig):
    phrase = rig.challenge()
    old = time.monotonic() - rig.cfg.challenge_ttl_s - 1
    rig.studio.challenges[UID] = Challenge(phrase, old)
    rig.recognizer.text = phrase
    response = rig.client.post(
        "/studio/enrol",
        files={
            "sample": ("s.wav", wav_bytes(speech_like(15)), "audio/wav"),
            "challenge": ("c.wav", wav_bytes(speech_like(3)), "audio/wav"),
        },
        data={"consent_text": rig.cfg.consent_text},
    )
    assert response.json()["code"] == "STUDIO_NO_CHALLENGE"


def test_sample_shorter_than_10_s_is_refused(rig):
    response = rig.enrol(sample=speech_like(6.0))
    assert response.json()["code"] == "STUDIO_BAD_LENGTH"
    assert stored(rig) == []


def test_sample_longer_than_30_s_is_refused(rig):
    response = rig.enrol(sample=speech_like(31.0))
    assert response.json()["code"] == "STUDIO_BAD_LENGTH"


def test_noisy_sample_is_refused_with_a_fix(rig):
    response = rig.enrol(sample=speech_like(15.0, noise=0.08))
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "STUDIO_LOW_SNR"
    assert "quiet room" in body["message"]  # says how to fix it
    assert stored(rig) == []


def test_silent_challenge_is_refused(rig):
    hiss = np.random.default_rng(1).normal(0, 0.01, 24_000 * 3).astype(np.float32)
    response = rig.enrol(phrase_audio=hiss)
    assert response.json()["code"] == "STUDIO_LOW_SNR"


def test_wrong_words_fail_the_challenge(rig):
    response = rig.enrol(heard="something else entirely")
    assert response.status_code == 422
    assert response.json()["code"] == "STUDIO_CHALLENGE_MISMATCH"
    assert stored(rig) == []


def test_one_misheard_word_of_five_still_passes(rig):
    phrase = rig.challenge()
    words = phrase.split()
    rig.recognizer.text = " ".join(["mumble"] + words[1:]) + "."
    response = rig.client.post(
        "/studio/enrol",
        files={
            "sample": ("s.wav", wav_bytes(speech_like(15)), "audio/wav"),
            "challenge": ("c.wav", wav_bytes(speech_like(3)), "audio/wav"),
        },
        data={"consent_text": rig.cfg.consent_text},
    )
    assert response.status_code == 200, response.text


def test_another_speaker_reading_the_phrase_is_refused(rig):
    rig.encoder.same_speaker = False
    response = rig.enrol()
    assert response.status_code == 422
    assert response.json()["code"] == "STUDIO_SPEAKER_MISMATCH"
    assert stored(rig) == []


def test_unreadable_file_is_refused(rig):
    rig.challenge()
    response = rig.client.post(
        "/studio/enrol",
        files={
            "sample": ("s.m4a", b"not audio at all", "audio/mp4"),
            "challenge": ("c.wav", wav_bytes(speech_like(3)), "audio/wav"),
        },
        data={"consent_text": rig.cfg.consent_text},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "STUDIO_BAD_AUDIO"


def test_a_challenge_phrase_works_only_once(rig):
    assert rig.enrol().status_code == 200
    assert UID not in rig.studio.challenges
