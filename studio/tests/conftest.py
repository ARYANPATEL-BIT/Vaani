"""Fakes for everything that would need a GPU, a model download or a voice.

FakeRecognizer, FakeEncoder and FakeCloner stand in for Whisper, the voice
encoder and Chatterbox. Fake audio is made here too: "speech" is bursts of a
tone with near-silent gaps between them (a high SNR, like a quiet room), and
"noise" is the same bursts buried under loud hiss (a low SNR).
"""

import io
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from pydantic import SecretStr
from vaani.asr.base import Transcript
from vaani.auth import COOKIE_NAME, sign_cookie
from vaani.config import AuthSettings

from voice_studio.app import create_app
from voice_studio.config import StudioSettings
from voice_studio.store import user_id

SECRET = "s" * 40  # a test-only HMAC key, at least 32 characters
ORIGIN = "http://localhost:5173"
EMAIL = "me@example.com"
UID = user_id(EMAIL)
RATE = 24_000


def speech_like(seconds: float, rate: int = RATE, noise: float = 0.0003) -> np.ndarray:
    """250 ms tone bursts, 150 ms gaps, over a noise floor of `noise`."""
    rng = np.random.default_rng(0)
    t = np.arange(int(seconds * rate)) / rate
    bursts = (t % 0.4) < 0.25
    tone = 0.3 * np.sin(2 * np.pi * 220 * t) * bursts
    return (tone + rng.normal(0, noise, t.size)).astype(np.float32)


def wav_bytes(samples: np.ndarray, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class FakeRecognizer:
    """Hears whatever `text` is set to."""

    def __init__(self) -> None:
        self.text = ""

    async def transcribe(self, pcm: bytes, cancel) -> Transcript:
        return Transcript(self.text, "en")


class FakeEncoder:
    """Every recording is the same speaker, unless `same_speaker` is False:
    then the sample and the challenge get orthogonal vectors."""

    def __init__(self) -> None:
        self.same_speaker = True
        self.calls = 0

    def embed(self, samples: np.ndarray) -> np.ndarray:
        self.calls += 1
        if self.same_speaker or self.calls % 2:
            return np.array([1.0, 0.0])
        return np.array([0.0, 1.0])


class FakeCloner:
    """Returns 0.5 s of quiet tone per sentence, or raises `fail`."""

    sample_rate = RATE

    def __init__(self) -> None:
        self.calls: list[list[tuple[str, str]]] = []
        self.fail: Exception | None = None

    def synthesize(self, reference: Path, sentences, stop) -> list[np.ndarray]:
        assert reference.exists(), "generate must use the enrolled sample"
        if self.fail:
            raise self.fail
        self.calls.append(list(sentences))
        return [speech_like(0.5) for _ in sentences]

    def stats(self) -> dict:
        return {"model_loaded": bool(self.calls), "device": "cpu"}


def auth_settings(enabled: bool = True) -> AuthSettings:
    return AuthSettings(
        enabled=enabled,
        google_client_id="test-client",
        session_secret=SecretStr(SECRET),
        allowed_emails=[EMAIL],
        allowed_origins=[ORIGIN],
    )


def cookie_for(email: str = EMAIL) -> str:
    return sign_cookie("sub-1", email, "Me", time.time() + 3600, SECRET)


class Rig:
    """A studio app with fakes, a signed-in client, and helpers."""

    def __init__(self, tmp_path: Path) -> None:
        self.cfg = StudioSettings(data_dir=str(tmp_path), device="cpu")
        self.recognizer = FakeRecognizer()
        self.encoder = FakeEncoder()
        self.cloner = FakeCloner()
        self.app = create_app(
            self.cfg, auth_settings(), self.cloner, self.encoder, self.recognizer
        )
        self.studio = self.app.state.studio
        self.client = TestClient(self.app, headers={"origin": ORIGIN})
        self.client.cookies.set(COOKIE_NAME, cookie_for())
        self.folder = tmp_path / UID

    def challenge(self) -> str:
        response = self.client.post("/studio/challenge")
        assert response.status_code == 200
        return response.json()["phrase"]

    def enrol(self, sample=None, phrase_audio=None, consent=None, heard=None):
        """Post an enrolment; by default every check passes."""
        phrase = self.challenge()
        self.recognizer.text = phrase if heard is None else heard
        sample = speech_like(15.0) if sample is None else sample
        phrase_audio = speech_like(3.0) if phrase_audio is None else phrase_audio
        return self.client.post(
            "/studio/enrol",
            files={
                "sample": ("sample.wav", wav_bytes(sample), "audio/wav"),
                "challenge": ("challenge.wav", wav_bytes(phrase_audio), "audio/wav"),
            },
            data={
                "consent_text": self.cfg.consent_text if consent is None else consent
            },
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)
