"""Chatterbox Multilingual adapter for run_eval.py.

Chatterbox clones in two stages. Once per reference: prepare_conditionals turns
the clip into (a) a speaker embedding from its voice encoder (timbre) and (b)
speech tokens from the first seconds of the clip (speaking style). Then per
sentence: a Llama-style model (T3) predicts speech tokens from the text, and
S3Gen decodes them to a 24 kHz waveform. Every output gets a Perth watermark.
"""

from importlib.metadata import version
from pathlib import Path

import huggingface_hub
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "chatterbox"
REPO_ID = "ResembleAI/chatterbox"
# The multilingual checkpoint only, the same files its from_pretrained() fetches.
WEIGHTS = [
    "ve.pt",
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
    "Cangjie5_TC.json",
]
PACKAGE_INFO = f"chatterbox-tts {version('chatterbox-tts')}, weights {REPO_ID} multilingual (MIT)"


def load(ref_wav: Path, ref_text: str, device: str):
    # ref_text is unused: Chatterbox conditions on audio alone.
    huggingface_hub.snapshot_download(
        REPO_ID, local_dir=MODEL_DIR, allow_patterns=WEIGHTS
    )
    model = ChatterboxMultilingualTTS.from_local(MODEL_DIR, device)
    model.prepare_conditionals(str(ref_wav))  # library defaults (exaggeration 0.5)
    return model


def synth(model, text: str, lang: str):
    # No audio_prompt_path: reuse the conditioning from load(), like XTTS's latents.
    wav = model.generate(text, language_id=lang)  # library defaults for sampling
    return wav.squeeze(0).numpy(), model.sr
