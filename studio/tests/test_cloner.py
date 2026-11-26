"""model.Cloner's own logic, with a stand-in for the Chatterbox model inside it.

No weights and no GPU: the stand-in replaces ChatterboxMultilingualTTS, so
these tests check OUR loop (stop between sentences, out-of-memory becomes
GpuBusy, no voice left loaded afterwards). Importing model.py does import
torch and chatterbox, which takes a few seconds.
"""

import threading

import pytest
import torch

from voice_studio.config import StudioSettings
from voice_studio.model import Cloner
from voice_studio.model_errors import GpuBusy


class StandIn:
    def __init__(
        self, stop: threading.Event | None = None, fail: Exception | None = None
    ):
        self.conds = None
        self.generated: list[str] = []
        self._stop = stop
        self._fail = fail

    def prepare_conditionals(self, path: str) -> None:
        self.conds = f"voice of {path}"

    def generate(self, text: str, language_id: str) -> torch.Tensor:
        if self._fail:
            raise self._fail
        self.generated.append(text)
        if self._stop:
            self._stop.set()  # as if the browser left during this sentence
        return torch.zeros(1, 2400)


def cloner_with(model: StandIn, tmp_path) -> Cloner:
    cloner = Cloner(StudioSettings(data_dir=str(tmp_path), device="cpu"))
    cloner._model = model  # skip the real load
    return cloner


SENTENCES = [("One.", "en"), ("Two.", "en"), ("Three.", "en")]


def test_all_sentences_and_no_voice_left_loaded(tmp_path):
    model = StandIn()
    waves = cloner_with(model, tmp_path).synthesize(
        tmp_path / "r.wav", SENTENCES, threading.Event()
    )
    assert len(waves) == 3
    assert model.conds is None  # cleared after the request


def test_stop_is_honoured_between_sentences(tmp_path):
    stop = threading.Event()
    model = StandIn(stop=stop)
    assert (
        cloner_with(model, tmp_path).synthesize(tmp_path / "r.wav", SENTENCES, stop)
        is None
    )
    assert model.generated == ["One."]  # the sentence in flight finished, no more
    assert model.conds is None


def test_stop_during_the_load_skips_conditioning(tmp_path):
    stop = threading.Event()
    stop.set()  # the browser left while the model was loading
    model = StandIn()
    assert (
        cloner_with(model, tmp_path).synthesize(tmp_path / "r.wav", SENTENCES, stop)
        is None
    )
    assert model.conds is None and model.generated == []


@pytest.mark.parametrize(
    "error",
    [
        torch.OutOfMemoryError("CUDA out of memory"),
        RuntimeError("CUBLAS_STATUS_ALLOC_FAILED"),
    ],
)
def test_out_of_memory_becomes_gpu_busy(tmp_path, error):
    model = StandIn(fail=error)
    with pytest.raises(GpuBusy):
        cloner_with(model, tmp_path).synthesize(
            tmp_path / "r.wav", SENTENCES, threading.Event()
        )
    assert model.conds is None


def test_other_errors_are_not_disguised_as_gpu_busy(tmp_path):
    model = StandIn(fail=ValueError("bad language"))
    with pytest.raises(ValueError):
        cloner_with(model, tmp_path).synthesize(
            tmp_path / "r.wav", SENTENCES, threading.Event()
        )
