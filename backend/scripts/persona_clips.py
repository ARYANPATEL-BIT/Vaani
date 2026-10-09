"""One clip per persona per language, in its configured voice, for a verdict.

Each clip goes through build_synthesizers, the server's own path, so what
you hear is exactly config.toml's [tts.piper.voices]: the voice AND its
length_scale. Each persona says a typical reply twice: in the Devanagari
reply format, with first-person verbs in the gender of its voice, and in
English (feat/english-voice). The voice is picked from each text's script by
the server's own rule (vaani/language.py), as a reply's first chunk picks it.

An alternative voice is tried WITHOUT editing config.toml, by overriding
one persona's table from the environment (it merges over the TOML, so
length_scale is kept). Day 15's rohan alternative for support (PowerShell):

    $env:VAANI_TTS__PIPER__VOICES__SUPPORT__HI__VOICE = "hi_IN-rohan-medium"
    $h = "b65dc80fb34d9dcd1cf684cb297966a3" + "4983bbc93bb1696fe207f32b0b33a091"
    $env:VAANI_TTS__PIPER__VOICES__SUPPORT__HI__SHA256 = $h
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
from vaani.language import reply_language
from vaani.tts import build_synthesizers

OUT = REPO / "docs" / "findings" / "persona-voices"

# Feminine first person for the female voice (default, support), masculine
# for the male one (tutor), as the persona prompts now ask. The English text
# is the same reply in English, which has no gendered verb forms.
TEXTS = {
    "default": [
        "जी, मैं कल सुबह 8 बजे आपको याद दिला दूँगी और ट्रैफ़िक का अपडेट "
        "भी दे दूँगी। मीटिंग का लिंक भी मैं भेज सकती हूँ।",
        "Sure, I'll remind you at 8 a.m. tomorrow and give you a traffic "
        "update too. I can send you the meeting link as well.",
    ],
    "tutor": [
        "ठीक है, मैं फ़्रैक्शन को एक पिज़्ज़ा से समझाऊँगा। अगर पिज़्ज़ा के 4 "
        "बराबर हिस्से हों, तो एक हिस्सा 1 बटा 4 है। क्या आप समझ गए?",
        "All right, I'll explain fractions with a pizza. If a pizza has 4 "
        "equal slices, one slice is 1 out of 4, a quarter. Did that make sense?",
    ],
    "support": [
        "जी, मैं आपकी परेशानी समझ सकती हूँ। कृपया अपना ऑर्डर नंबर "
        "बताइए, मैं अभी उसका स्टेटस चेक कर दूँगी।",
        "I understand the problem. Please tell me your order number, and "
        "I'll check its status right away.",
    ],
}
# The same Devanagari replies in masculine forms, for a persona tried with a
# male Hindi voice. --masculine swaps these in for the Devanagari text only.
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
        for text in TEXTS[persona]:
            language = reply_language(text)  # the server's rule picks the voice
            if masculine and language == "hi":
                text = MASCULINE[persona]
            pv = tts.piper.voices[persona][language]
            synth = synths[persona][language]
            started = perf_counter()
            # The whole reply in one call: this is about the voice, not chunks.
            pcm = await synth.synthesize(text, cancel) or b""
            ms = (perf_counter() - started) * 1000
            rate = synth.sample_rate
            scale = pv.length_scale or 1.0
            path = OUT / f"persona_{persona}_{pv.voice}_ls{scale}_{log.stamp}.wav"
            with wave.open(str(path), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(rate)
                f.writeframes(pcm)
            log(
                f"{persona} ({language}): {pv.voice}, length_scale "
                f"{pv.length_scale}, {rate} Hz, {len(pcm) / 2 / rate:.2f} s audio "
                f"in {ms:.0f} ms -> {path.name}"
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
