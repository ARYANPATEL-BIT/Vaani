"""What the Hindi Piper voice does with Hinglish: phoneme dump, WAVs, ASR floor.

One real agent reply (day 12, Gemini, default persona) in three scripts:
  A  as the agent actually sent it: all Latin script (the persona asked for it);
  B  mixed: Hindi words in Devanagari, English words in Latin (hand-written);
  C  all Devanagari (hand-written), as the control.
Three real replies in the all-Devanagari format the persona asks for since
fix/reply-script, verbatim from docs/findings/reply-script/
ask_script_check_20261006-115858.tsv (Gemini, default persona):
  R1 line 1: a digit and an English loanword pair (8, dentist appointment);
  R2 line 7: many loanwords and the conjunction kyunki;
  R3 line 9: technical English terms (Python, list, mutable, tuple).

For each, written to docs/findings/reply-script/, named with the run's
timestamp so a new run never overwrites the WAVs a verdict was given on
(docs/findings/tts-day12/ is frozen):
  * hinglish_<X>_<timestamp>.wav - what the voice produced (22050 Hz, as
    the browser gets it);
  * hinglish_phonemes_<timestamp>.txt - per variant:
      - espeak-ng's raw output. "(en)...(hi)" marks words espeak switched to
        ENGLISH pronunciation rules; Piper strips those markers, so the Hindi
        voice then speaks English-rule phonemes;
      - the phonemes Piper fed the network;
      - phonemes the voice has no id for (Piper drops them silently);
      - a Whisper large-v3 transcript of the WAV. This is a FLOOR, not a pass:
        Whisper recovering the words does not mean a listener finds it
        natural, but Whisper failing means a listener likely will too.

    uv run python scripts/hinglish_tts.py            # Whisper on cuda/large-v3
    uv run python scripts/hinglish_tts.py --no-asr   # dump and WAVs only
"""

import argparse
import re
import wave
from datetime import datetime
from pathlib import Path

from piper import PiperVoice, espeakbridge
from piper.phonemize_espeak import ESPEAK_DATA_DIR

from vaani.config import get_settings

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND.parent / "docs" / "findings" / "reply-script"

VARIANTS = {
    "A": "Theek hai, main kal subah 8 baje yaad dila doongi aur traffic ka update "
    "bhi de doongi.",
    "B": "ठीक है, मैं कल सुबह 8 बजे याद दिला दूँगी और traffic का update भी दे दूँगी।",
    "C": "ठीक है, मैं कल सुबह 8 बजे याद दिला दूँगी और ट्रैफ़िक का अपडेट भी दे दूँगी।",
    "R1": "ज़रूर, मैं कल सुबह 8 बजे आपके डेंटिस्ट अपॉइंटमेंट के लिए आपको याद दिला दूँगी।",
    "R2": "अभी मैप्स के हिसाब से एक्सप्रेसवे वाला रूट सबसे फ़ास्ट है, क्योंकि "
    "वहाँ ट्रैफ़िक कम है। आप वही रास्ता ले सकते हैं।",
    "R3": "पायथन में लिस्ट म्यूटेबल होती है यानी इसे बदला जा सकता है, जबकि "
    "ट्यूबल इम्म्यूटेबल होता है और इसे बदला नहीं जा सकता है।",
}


def write_wav(path: Path, pcm: bytes, rate: int) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm)


def main(asr: bool) -> None:
    cfg = get_settings().tts.piper
    voice = PiperVoice.load(BACKEND / cfg.model_path, BACKEND / cfg.config_path)
    rate = voice.config.sample_rate
    known = set(voice.config.phoneme_id_map)
    espeakbridge.initialize(str(ESPEAK_DATA_DIR))
    espeakbridge.set_voice(voice.config.espeak_voice)
    whisper = None
    if asr:
        # The server's own setup: puts the pip-installed CUDA DLLs on the
        # Windows DLL path, which must happen before CTranslate2 loads.
        from vaani.asr.whisper import _add_windows_cuda_dll_dirs

        _add_windows_cuda_dll_dirs()
        from faster_whisper import WhisperModel

        whisper = WhisperModel("large-v3", device="cuda", compute_type="float16")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    lines = [
        f"Voice: {Path(cfg.model_path).name}, espeak voice "
        f"'{voice.config.espeak_voice}', {rate} Hz",
        "",
    ]
    for name, text in VARIANTS.items():
        raw = " | ".join(p for p, _, _ in espeakbridge.get_phonemes(text))
        english = re.findall(r"\(en\)(.*?)\(hi\)", raw)
        phonemes = [p for sentence in voice.phonemize(text) for p in sentence]
        missing = sorted({p for p in phonemes if p not in known})
        pcm = b"".join(c.audio_int16_bytes for c in voice.synthesize(text))
        wav = OUT / f"hinglish_{name}_{stamp}.wav"
        write_wav(wav, pcm, rate)
        lines += [
            f"=== {name}: {text}",
            f"audio {len(pcm) / 2 / rate:.2f} s (timing: see measure_tts.py)",
            f"espeak raw:  {raw}",
            f"English-rule stretches ({len(english)}): {english}",
            f"piper phonemes: {''.join(phonemes)}",
            f"no id in voice (dropped): {missing or 'none'}",
        ]
        if whisper is not None:
            segments, _ = whisper.transcribe(str(wav), language="hi", beam_size=5)
            heard = " ".join(s.text.strip() for s in segments)
            lines.append(f"whisper large-v3 (floor, not a pass): {heard}")
        lines.append("")
    dump = OUT / f"hinglish_phonemes_{stamp}.txt"
    dump.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {dump.name} and {len(VARIANTS)} WAVs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-asr", action="store_true")
    main(asr=not parser.parse_args().no_asr)
