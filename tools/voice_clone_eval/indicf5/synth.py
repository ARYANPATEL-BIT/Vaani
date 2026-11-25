"""IndicF5 adapter for run_eval.py.

IndicF5 is F5-TTS (a flow-matching model: it starts from noise and refines a
mel spectrogram over 32 steps) trained by AI4Bharat on Indian languages. Unlike
XTTS and Chatterbox it needs the reference clip's TRANSCRIPT as well as its
audio: the model is shown "this audio says this text", then continues in that
voice with the new text. It has no language parameter; the text alone decides.

This mirrors INF5Model.forward() in the repo's model.py, with two differences:
- No trust_remote_code: that would run model.py from the Hub. We build the same
  model from the pinned f5_tts package and load the same model.safetensors.
- No torch.compile: it needs Triton, which has no Windows build. Compiling only
  speeds inference up, so our timings may be slower than upstream's.
"""

import atexit
import io
import os
from importlib.metadata import version
from pathlib import Path

import numpy as np
import soundfile as sf
from f5_tts.infer.utils_infer import (
    infer_process,
    load_model,
    load_vocoder,
    preprocess_ref_audio_text,
)
from f5_tts.model import DiT
from pydub import AudioSegment, silence
from safetensors.torch import load_file

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "IndicF5"
PACKAGE_INFO = (
    f"f5_tts {version('f5_tts')} (AI4Bharat/IndicF5 @13f7c4d), "
    "weights ai4bharat/IndicF5 (gated, card says MIT)"
)
# The architecture model.py builds; the weights only fit this exact shape.
DIT_CFG = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)
RATE = 24_000
TARGET_DBFS = -20.0  # model.py normalises every output to this loudness


def _weights(state: dict, prefix: str) -> dict:
    # model.py compiled both modules before saving, so every key carries
    # torch.compile's "_orig_mod." wrapper name; strip it for the plain modules.
    return {k[len(prefix):]: v for k, v in state.items() if k.startswith(prefix)}


def load(ref_wav: Path, ref_text: str, device: str):
    # load_vocoder fetches the Vocos architecture config (charactr/vocos-mel-24khz,
    # MIT) from the Hub; its weights are then replaced by IndicF5's own copy.
    vocoder = load_vocoder(vocoder_name="vocos", is_local=False, device=device)
    model = load_model(
        DiT,
        DIT_CFG,
        mel_spec_type="vocos",
        vocab_file=str(MODEL_DIR / "checkpoints" / "vocab.txt"),
        device=device,
    )
    state = load_file(str(MODEL_DIR / "model.safetensors"), device=device)
    # strict=True: a missing or extra weight is an error, not a silently worse model.
    model.load_state_dict(_weights(state, "ema_model._orig_mod."), strict=True)
    vocoder.load_state_dict(_weights(state, "vocoder._orig_mod."), strict=True)
    model.eval()

    # Trims the clip at silences to at most 15 s and writes the result to a temp
    # wav that infer_process re-reads per sentence. Upstream redoes this on every
    # call with the same result; we do it once, like the other adapters.
    ref_path, ref_text = preprocess_ref_audio_text(str(ref_wav), ref_text, device=device)
    # That temp file is a copy of the operator's voice outside the gitignored
    # audio folder (delete=False upstream), so remove it when the run ends.
    atexit.register(os.remove, ref_path)
    return model, vocoder, ref_path, ref_text, device


def synth(state, text: str, lang: str):
    # lang is unused: IndicF5 has no language input (see the module docstring).
    model, vocoder, ref_path, ref_text, device = state
    wave, rate, _ = infer_process(
        ref_path, ref_text, text, model, vocoder, mel_spec_type="vocos", device=device
    )
    # model.py's post-processing, kept so these clips match what IndicF5 ships:
    # cut pauses over 1 s down to 0.5 s each side, then normalise loudness.
    buf = io.BytesIO()
    sf.write(buf, wave, rate, format="WAV")
    buf.seek(0)
    seg = AudioSegment.from_file(buf, format="wav")
    parts = silence.split_on_silence(
        seg, min_silence_len=1000, silence_thresh=-50, keep_silence=500, seek_step=10
    )
    seg = sum(parts, AudioSegment.silent(duration=0))
    seg = seg.apply_gain(TARGET_DBFS - seg.dBFS)
    out = np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0
    return out, rate
