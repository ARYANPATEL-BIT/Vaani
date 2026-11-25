"""XTTS-v2 adapter for run_eval.py.

XTTS clones in two stages. Once per reference: get_conditioning_latents turns the
clip into (a) GPT conditioning latents (speaking style) and (b) a speaker
embedding (timbre). Then per sentence: inference() predicts speech tokens with a
GPT-style model and decodes them to a 24 kHz waveform.
"""

from importlib.metadata import version
from pathlib import Path

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "XTTS-v2"
PACKAGE_INFO = f"coqui-tts {version('coqui-tts')}, weights coqui/XTTS-v2 (CPML)"
TEMPERATURE = 0.7  # coqui's documented default for inference()


def load(ref_wav: Path, ref_text: str, device: str):
    # ref_text is unused: XTTS conditions on audio alone.
    config = XttsConfig()
    config.load_json(str(MODEL_DIR / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=str(MODEL_DIR), use_deepspeed=False)
    model.to(device)
    latents, speaker = model.get_conditioning_latents(audio_path=[str(ref_wav)])
    return model, latents, speaker, config.audio.output_sample_rate


def synth(state, text: str, lang: str):
    model, latents, speaker, rate = state
    out = model.inference(text, lang, latents, speaker, temperature=TEMPERATURE)
    return out["wav"], rate
