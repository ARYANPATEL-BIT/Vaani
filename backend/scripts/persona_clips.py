"""One clip per persona, in its configured voice, for a listening verdict.

Each clip goes through build_synthesizers, the server's own path, so what
you hear is exactly config.toml's [tts.piper.voices]: the voice AND its
length_scale. Each persona says a typical reply in the Devanagari reply
format, with first-person verbs in the gender of its voice.

An alternative voice is tried WITHOUT editing config.toml, by overriding
one persona's table from the environment (it merges over the TOML, so
length_scale is kept). Day 15's rohan alternative for support (PowerShell):

    $env:VAANI_TTS__PIPER__VOICES__SUPPORT__VOICE = "hi_IN-rohan-medium"
    $h = "b65dc80fb34d9dcd1cf684cb297966a3" + "4983bbc93bb1696fe207f32b0b33a091"
    $env:VAANI_TTS__PIPER__VOICES__SUPPORT__SHA256 = $h
    uv run python scripts/persona_clips.py --persona support --masculine

rohan is not in config.toml (its licence is unclear), so fetch_models.py
does not fetch it: download it by hand from the pinned voices_url first.

Clips go to docs/findings/persona-voices/persona_<persona>_<voice>_ls<length
scale>_<timestamp>.wav, and the run's text file lists what each one says.

    uv run python scripts/persona_clips.py
"""

import argparse
import asyncio
import wave
from time import perf_counter

from run_log import REPO, RunLog  # scripts/ is on sys.path when run as a file

from vaani.config import get_settings
from vaani.tts import build_synthesizers

OUT = REPO / "docs" / "findings" / "persona-voices"

# Feminine first person for the female voice (default, support), masculine
# for the male one (tutor), as the persona prompts now ask.
TEXTS = {
    "default": "जी, मैं कल सुबह 8 बजे आपको याद दिला दूँगी और ट्रैफ़िक का अपडेट "
    "भी दे दूँगी। मीटिंग का लिंक भी मैं भेज सकती हूँ।",
    "tutor": "ठीक है, मैं फ़्रैक्शन को एक पिज़्ज़ा से समझाऊँगा। अगर पिज़्ज़ा के 4 "
    "बराबर हिस्से हों, तो एक हिस्सा 1 बटा 4 है। क्या आप समझ गए?",
    "support": "जी, मैं आपकी परेशानी समझ सकती हूँ। कृपया अपना ऑर्डर नंबर "
    "बताइए, मैं अभी उसका स्टेटस चेक कर दूँगी।",
}
# The same replies in masculine forms, for a persona tried with a male voice.
MASCULINE = {
    "support": "जी, मैं आपकी परेशानी समझ सकता हूँ। कृपया अपना ऑर्डर नंबर "
    "बताइए, मैं अभी उसका स्टेटस चेक कर दूँगा।",
}


async def main(personas: list[str], masculine: bool) -> None:
    log = RunLog("persona_clips", out=OUT)
    tts = get_settings().tts
    synths = build_synthesizers(tts)
    cancel = asyncio.Event()
    for persona in personas or list(synths):
        pv = tts.piper.voices[persona]
        text = MASCULINE[persona] if masculine else TEXTS[persona]
        started = perf_counter()
        # The whole reply in one call: this is about the voice, not chunking.
        pcm = await synths[persona].synthesize(text, cancel) or b""
        ms = (perf_counter() - started) * 1000
        rate = synths[persona].sample_rate
        scale = pv.length_scale or 1.0
        path = OUT / f"persona_{persona}_{pv.voice}_ls{scale}_{log.stamp}.wav"
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes(pcm)
        log(
            f"{persona}: {pv.voice}, length_scale {pv.length_scale}, {rate} Hz, "
            f"{len(pcm) / 2 / rate:.2f} s audio in {ms:.0f} ms -> {path.name}"
        )
        log(f"  text: {text}")
    log()
    log(f"wrote {log.path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", nargs="*", default=[], help="default: all")
    parser.add_argument(
        "--masculine", action="store_true", help="say the masculine text"
    )
    args = parser.parse_args()
    asyncio.run(main(args.persona, args.masculine))
