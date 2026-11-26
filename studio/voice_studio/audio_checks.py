"""Reading an uploaded recording, and measuring whether it is good enough.

Decoding: the browser records webm/opus (MediaRecorder), a phone records m4a
(AAC), a desktop tool records WAV. PyAV (FFmpeg's decoders, bundled in its
wheel) reads all of them and resamples to the rate we ask for, so the rest of
the studio only ever sees one shape: mono float32 samples in [-1, 1].

SNR (signal-to-noise ratio): how far the voice sits above the background
noise, in decibels. A cloning model copies the noise of its reference into
every sentence it makes: the spike's clip A, at about 5 dB, cloned to audio
in which Whisper large-v3 found no words at all (commit b7ef4ba).

An upload has no "silent lead-in" to measure the room from, so the estimate
comes from the recording itself. It is cut into 20 ms frames and each frame's
loudness is measured. The quietest frames are the pauses between words, so
they show the noise; the loudest frames are speech. SNR is the gap between
the 90th and the 10th percentile frame. Pure silence, or pure noise, gives a
gap near zero, so the same check also rejects a file with no speech in it.
"""

import io

import av
import numpy as np

# Part of the estimator's definition, not tunables: changing them changes
# what "SNR" means here, and the threshold (config min_snr_db) was calibrated
# with exactly these.
FRAME_MS = 20
NOISE_PERCENTILE = 10
SPEECH_PERCENTILE = 90


class AudioError(Exception):
    """The upload is not audio we can read."""


def decode(data: bytes, rate: int) -> np.ndarray:
    """Any audio file's bytes -> mono float32 samples at `rate` Hz."""
    try:
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.audio:
                raise AudioError("the file has no audio track")
            stream = container.streams.audio[0]
            # The resampler converts on the fly: whatever the file's rate and
            # channel layout, every frame comes out as mono floats at `rate`.
            resampler = av.AudioResampler(format="flt", layout="mono", rate=rate)
            chunks = []
            for frame in container.decode(stream):
                chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
            # None flushes the samples the resampler still holds back.
            chunks.extend(f.to_ndarray() for f in resampler.resample(None))
    except av.FFmpegError as exc:
        raise AudioError("the file could not be read as audio") from exc
    if not chunks:
        raise AudioError("the file contains no audio samples")
    return np.concatenate(chunks, axis=1)[0].astype(np.float32)


def duration_s(samples: np.ndarray, rate: int) -> float:
    return len(samples) / rate


def snr_db(samples: np.ndarray, rate: int) -> float:
    """Speech level minus noise level, in dB (see the module docstring)."""
    frame = rate * FRAME_MS // 1000
    frames = samples[: len(samples) // frame * frame].reshape(-1, frame)
    # RMS loudness per frame in dBFS; the tiny constant keeps log10 off zero
    # for digital silence.
    levels = 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9)
    noise = np.percentile(levels, NOISE_PERCENTILE)
    speech = np.percentile(levels, SPEECH_PERCENTILE)
    return float(speech - noise)


def to_pcm16(samples: np.ndarray) -> bytes:
    """Float samples -> 16-bit little-endian PCM, what vaani's Whisper takes."""
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767).astype("<i2").tobytes()
