"""Voice activity detection: is there speech in this frame, and when did it
start and stop?

Three layers, smallest first:

1. `load_model` reads the Silero VAD ONNX file ONCE per process and returns
   an ONNX Runtime session. The session holds only the model's weights. It
   holds no memory of any audio, so every connection can share it.
2. `VadStream` is per session. It turns our 20 ms byte frames into what
   Silero needs (float32, 512-sample chunks, plus Silero's memory: the
   `state` tensor and 64 samples of `context`). It returns a speech yes/no
   for every frame.
3. `Hysteresis` turns those per-frame yes/no answers into two events,
   speech_started and speech_ended. A single frame never flips the answer.

Why 512 and not 320: Silero v5/v6 at 16 kHz accepts exactly 512 samples
(32 ms) per call. Our frame is 320 samples (20 ms). So VadStream buffers
samples and runs the model each time 512 have built up. Every 8 frames
(2,560 samples) that means 5 model runs. A frame that does not complete a
chunk reuses the latest probability. These sizes are fixed by the model's
design, not tuning knobs, which is why they are constants here and not config.

This file only DETECTS speech. It does not decide that a turn is over
(endpointing, day 9), transcribe, or trigger barge-in.
"""

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import numpy as np
import onnxruntime as ort

from vaani.config import AudioSettings, VadSettings

log = logging.getLogger("vaani.vad")

# Fixed by the Silero v5/v6 model at 16 kHz (see module docstring).
MODEL_SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512
CONTEXT_SAMPLES = 64
# Shape of Silero's recurrent state: (2, batch=1, 128).
STATE_SHAPE = (2, 1, 128)

# Event kinds.
SPEECH_STARTED = "speech_started"
SPEECH_ENDED = "speech_ended"

# backend/, so a relative model_path in config works from any working dir.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class SpeechEvent:
    """speech_started or speech_ended.

    `frame_index` is the 0-based index of the frame that CONFIRMED the event
    (the Nth speech frame, or the Mth silence frame), counted from the
    session's first valid frame. `at` is a perf_counter timestamp, the same
    clock as telemetry spans, so the two can be compared directly.
    """

    kind: str
    frame_index: int
    at: float


@lru_cache(maxsize=1)
def load_model(model_path: str, model_sha256: str) -> ort.InferenceSession:
    """Load the Silero ONNX model once per process and return the shared session.

    lru_cache makes the second and later calls return the SAME session
    instantly. That is what "load once" means here: the app, every session and
    every test share one copy of the weights.

    The sha256 check runs before the file is handed to ONNX Runtime. A wrong,
    truncated or swapped file stops startup with a clear error instead of
    quietly changing what counts as speech.
    """
    path = Path(model_path)
    if not path.is_absolute():
        path = _BACKEND_ROOT / path
    data = path.read_bytes()  # FileNotFoundError if missing: fail at startup
    actual = hashlib.sha256(data).hexdigest()
    if actual != model_sha256:
        raise ValueError(
            f"VAD model {path} has sha256 {actual}, config expects {model_sha256}"
        )

    opts = ort.SessionOptions()
    # One thread per call. The model is tiny, so extra threads cost more to
    # coordinate than they save. More threads would also compete with the
    # event loop and the other sessions for CPU.
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    started = perf_counter()
    session = ort.InferenceSession(
        data, sess_options=opts, providers=["CPUExecutionProvider"]
    )
    log.info("VAD model loaded in %.1f ms", (perf_counter() - started) * 1000)
    return session


class Hysteresis:
    """Per-frame speech booleans -> speech_started / speech_ended events.

    Two counters and one flag. While not in speech, count consecutive speech
    frames; at `start_frames`, emit speech_started. While in speech, count
    consecutive silence frames; at `end_frames`, emit speech_ended. Any frame
    of the other kind resets the run, so the run must be unbroken.

    Kept separate from the model so it can be tested with plain True/False
    input, and so day-9 endpointing can build on the same events.
    """

    def __init__(self, start_frames: int, end_frames: int) -> None:
        self._start_frames = start_frames
        self._end_frames = end_frames
        self.in_speech = False
        self._run = 0  # consecutive frames that disagree with in_speech

    def update(
        self, is_speech: bool, frame_index: int, at: float
    ) -> SpeechEvent | None:
        if is_speech == self.in_speech:
            # Frame agrees with the current state: any run toward a flip is broken.
            self._run = 0
            return None
        self._run += 1
        needed = self._end_frames if self.in_speech else self._start_frames
        if self._run < needed:
            return None
        self.in_speech = not self.in_speech
        self._run = 0
        kind = SPEECH_STARTED if self.in_speech else SPEECH_ENDED
        return SpeechEvent(kind=kind, frame_index=frame_index, at=at)


class VadStream:
    """One session's VAD: sample buffer, Silero memory, and hysteresis.

    Created per session and owned by that session's coroutine, so there is no
    locking. The ONNX session passed in is shared across all sessions. It is
    safe to share because Silero's memory (`_state`, `_context`) is passed in
    and returned on every call and stored HERE, never inside the model.
    """

    def __init__(
        self, model: ort.InferenceSession, vad: VadSettings, audio: AudioSettings
    ) -> None:
        if audio.sample_rate != MODEL_SAMPLE_RATE or audio.channels != 1:
            raise ValueError("Silero VAD needs 16 kHz mono audio")
        self._model = model
        self._threshold = vad.threshold
        self._hysteresis = Hysteresis(vad.start_frames, vad.end_frames)
        self._state = np.zeros(STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)
        self._sr = np.array(MODEL_SAMPLE_RATE, dtype=np.int64)
        # Samples received but not yet fed to the model (always < 512 between
        # calls to push).
        self._pending = np.zeros(0, dtype=np.float32)
        self._probability = 0.0  # latest model output; 0 until the first chunk
        self._frame_index = -1

    @property
    def probability(self) -> float:
        """The most recent speech probability (for tests and debugging)."""
        return self._probability

    def push(self, frame: bytes) -> SpeechEvent | None:
        """Feed one frame; return a speech event if this frame confirmed one.

        The caller has already checked the frame's size. The bytes are
        16-bit signed little-endian PCM, which is what the protocol specifies.
        """
        self._frame_index += 1
        # int16 -> float32 in [-1, 1): the scale Silero was trained on.
        samples = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768.0
        self._pending = np.concatenate((self._pending, samples))
        # At most one chunk completes per 320-sample frame, but a loop keeps
        # this correct if the frame size in config ever grows past 512.
        while len(self._pending) >= CHUNK_SAMPLES:
            chunk = self._pending[:CHUNK_SAMPLES]
            self._pending = self._pending[CHUNK_SAMPLES:]
            self._probability = self._infer(chunk)
        is_speech = self._probability >= self._threshold
        return self._hysteresis.update(is_speech, self._frame_index, perf_counter())

    def _infer(self, chunk: np.ndarray) -> float:
        """Run Silero on one 512-sample chunk and carry its memory forward.

        Silero expects the last 64 samples of the previous chunk in front of
        the new one (576 in total), plus its recurrent state. It returns the
        speech probability and the next state. This mirrors the upstream
        OnnxWrapper.__call__ in silero-vad v6.2.3, without torch.
        """
        x = np.concatenate((self._context, chunk[np.newaxis, :]), axis=1)
        out, self._state = self._model.run(
            None, {"input": x, "state": self._state, "sr": self._sr}
        )
        self._context = x[:, -CONTEXT_SAMPLES:]
        return float(out[0, 0])
