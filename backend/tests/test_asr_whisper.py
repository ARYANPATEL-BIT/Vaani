"""WhisperRecognizer: what it asks faster-whisper for, and what it gets back.

The first group swaps faster_whisper.WhisperModel for a recorder, so it runs
in the default suite: a wrong `task` or `language` fails SILENTLY in real use
(you get a translation, or the wrong script), so both are asserted directly.

The second group (@pytest.mark.slow) loads the real model named in
config.toml. Run with: uv run pytest -m slow
"""

import asyncio
import wave
from pathlib import Path

import faster_whisper
import pytest

import vaani.asr.whisper as whisper_mod
from tests.test_asr_gateway import frame_rate_during_inference, make_client
from vaani.asr import AsrError, Recognizer, Transcript, build_recognizer
from vaani.asr.whisper import WhisperRecognizer
from vaani.config import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "speech_16k_mono.wav"


def asr_cfg(**whisper_update):
    base = Settings().asr
    return base.model_copy(
        update={
            "enabled": True,
            "whisper": base.whisper.model_copy(update=whisper_update),
        }
    )


def fixture_pcm() -> bytes:
    with wave.open(str(FIXTURE), "rb") as wav:
        return wav.readframes(wav.getnframes())


# --- Fast: a recording stand-in for the model -------------------------------


class RecordingModel:
    """Records every transcribe() call's keyword arguments."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        RecordingModel.init_kwargs = kwargs

    def transcribe(self, audio, **kwargs):
        RecordingModel.calls.append(kwargs)

        class Info:
            language = kwargs.get("language")

        class Segment:
            text = " haan ji "

        return iter([Segment()]), Info()


@pytest.fixture
def recording_model(monkeypatch):
    RecordingModel.calls = []
    monkeypatch.setattr(faster_whisper, "WhisperModel", RecordingModel)
    return RecordingModel


def test_task_is_transcribe_and_language_comes_from_config(recording_model) -> None:
    # "mr" (Marathi) is not the committed default, so passing proves the value
    # is read from config, not hardcoded.
    cfg = asr_cfg(language="mr", initial_prompt="kal milte hain", temperature=[0.0])
    rec = WhisperRecognizer(cfg, 16000)
    result = asyncio.run(rec.transcribe(b"\x00\x00" * 16000, asyncio.Event()))

    call = recording_model.calls[-1]  # [0] is the startup warm-up
    assert call["task"] == "transcribe"
    assert call["language"] == "mr"
    assert call["initial_prompt"] == "kal milte hain"
    assert call["temperature"] == [0.0]
    assert call["vad_filter"] is True
    assert result == Transcript("haan ji", "mr")


def test_warm_up_runs_once_at_construction(recording_model) -> None:
    WhisperRecognizer(asr_cfg(), 16000)
    assert len(recording_model.calls) == 1
    assert recording_model.calls[0]["task"] == "transcribe"


def test_model_device_and_compute_type_come_from_config(recording_model) -> None:
    WhisperRecognizer(asr_cfg(compute_type="int8_float32"), 16000)
    assert recording_model.init_kwargs["compute_type"] == "int8_float32"
    assert recording_model.init_kwargs["device"] == "cpu"


def test_cuda_requested_but_unavailable_fails_loudly(monkeypatch) -> None:
    import ctranslate2

    monkeypatch.setattr(whisper_mod, "_add_windows_cuda_dll_dirs", lambda: None)
    monkeypatch.setattr(ctranslate2, "get_cuda_device_count", lambda: 0)
    with pytest.raises(AsrError, match="refusing to fall back to CPU"):
        WhisperRecognizer(asr_cfg(device="cuda"), 16000)


def test_wrong_sample_rate_is_refused() -> None:
    with pytest.raises(AsrError, match="16000 Hz"):
        WhisperRecognizer(asr_cfg(), 8000)


# --- Slow: the real model from config.toml ----------------------------------


def real_recognizer() -> Recognizer:
    return build_recognizer(asr_cfg(), 16000)


@pytest.mark.slow
def test_speech_fixture_gives_a_non_empty_transcript() -> None:
    result = asyncio.run(real_recognizer().transcribe(fixture_pcm(), asyncio.Event()))
    assert result is not None
    print(f"transcript: {result.text!r}")
    assert result.text.strip()


@pytest.mark.slow
def test_silence_gives_no_hallucinated_words() -> None:
    silence = b"\x00\x00" * 16000 * 5  # 5 s of digital silence
    result = asyncio.run(real_recognizer().transcribe(silence, asyncio.Event()))
    assert result is not None
    assert len(result.text.split()) <= 1, result.text


class TimedRecognizer(Recognizer):
    """Wraps the real recogniser and records when each decode ran."""

    def __init__(self, inner: Recognizer) -> None:
        self.inner = inner
        self.windows: list[tuple[float, float]] = []

    async def transcribe(self, pcm, cancel):
        from time import perf_counter

        start = perf_counter()
        try:
            return await self.inner.transcribe(pcm, cancel)
        finally:
            self.windows.append((start, perf_counter()))


@pytest.mark.slow
def test_frames_keep_flowing_during_real_inference(monkeypatch) -> None:
    """THE test of the threading design, against the real engine: frames are
    still counted at ~50/s while CTranslate2 decodes on a worker thread. It
    passes only because CTranslate2 releases the GIL while it computes."""
    rec = TimedRecognizer(real_recognizer())
    rate, max_gap_ms, decode_s = frame_rate_during_inference(
        monkeypatch, make_client(rec), lambda: rec.windows[0], silence_s=8.0
    )
    print(f"decode {decode_s:.2f}s: {rate:.1f} frames/s, max gap {max_gap_ms:.0f}ms")
    assert decode_s > 0.2  # long enough to mean something
    assert rate >= 45, f"{rate:.1f} frames/s during inference"
    assert max_gap_ms < 100, f"longest gap {max_gap_ms:.0f} ms"
