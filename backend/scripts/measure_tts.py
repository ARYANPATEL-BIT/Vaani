"""Piper's time to first byte, and what chunk size does to prosody.

1. TIME TO FIRST BYTE vs CHUNK LENGTH. Piper is not a streaming synthesiser:
   nothing comes back until the whole chunk is synthesised, so time to first
   byte IS the synthesis time. Each length is timed `--repeat` times through
   the real PiperSynthesizer (thread pool included), after one warm-up.

2. PROSODY vs FIRST-CHUNK THRESHOLD. One reply is chunked by the real
   ClauseChunker three ways, each chunk synthesised separately (as the server
   does) and the pieces joined back to back (as the browser plays them):
     aggressive   first_min_chars = 4   (the first chunk is cut very early)
     conservative first_min_chars = 60, first_max_chars = 200 (the first
                  chunk is a whole sentence)
     whole        the reply in one call (no chunk boundaries at all)
   Written to docs/findings/reply-script/prosody_<name>_<timestamp>.wav, for
   listening. The timestamp is the run's: a new run never overwrites the
   WAVs an earlier verdict was given on.

All text is in the reply format the persona asks for since fix/reply-script:
every word in Devanagari, English words too (hinglish_C in
docs/learning/backend-learning/12-chunking-tts.md section 5).

Everything printed is also written to docs/findings/reply-script/
measure_tts_<timestamp>.txt (run_log.py), one file per run.

    uv run python scripts/measure_tts.py
    uv run python scripts/measure_tts.py --persona tutor
"""

import argparse
import asyncio
import re
import wave
from statistics import median
from time import perf_counter

from run_log import OUT, RunLog  # scripts/ is on sys.path when run as a file

from vaani.chunker import ClauseChunker
from vaani.config import get_settings
from vaani.tts import build_synthesizers

# Day 12's Latin texts, written in Devanagari word for word. "जी," first
# since day 14: replies open with it, and it is now a first chunk on its own.
LENGTHS = [
    "जी,",
    "ठीक है,",
    "मैं आपको याद दिला दूँगी।",
    "ठीक है, मैं कल सुबह आठ बजे आपको याद दिला दूँगी।",
    "ठीक है, मैं कल सुबह आठ बजे आपको याद दिला दूँगी, और ट्रैफ़िक का अपडेट "
    "भी दे दूँगी ताकि आप टाइम पर निकल सकें।",
    "ठीक है, मैं कल सुबह आठ बजे आपको याद दिला दूँगी, और ट्रैफ़िक का अपडेट "
    "भी दे दूँगी ताकि आप टाइम पर निकल सकें, क्योंकि सुबह के समय हाईवे पर "
    "बहुत भीड़ होती है और डेंटिस्ट का क्लिनिक दूर है।",
]

# First sentence: hinglish_C's text exactly. Second: day 12's second sentence.
REPLY = (
    "ठीक है, मैं कल सुबह 8 बजे याद दिला दूँगी और ट्रैफ़िक का अपडेट भी दे "
    "दूँगी। अगर आप चाहें तो मैं डेंटिस्ट का एड्रेस भी भेज सकती हूँ।"
)


def chunks_of(text: str, **cfg) -> list[str]:
    chunker = ClauseChunker(get_settings().chunker.model_copy(update=cfg))
    out = []
    for token in re.findall(r"\S+\s*", text):
        out += chunker.push(token)
    if (last := chunker.flush()) is not None:
        out.append(last)
    return out


async def main(repeat: int, persona: str) -> None:
    log = RunLog("measure_tts")
    tts = get_settings().tts
    synth = build_synthesizers(tts)[persona]
    rate = synth.sample_rate
    pv = tts.piper.voices[persona]
    log(
        f"persona {persona}: voice {pv.voice}, length_scale {pv.length_scale}, "
        f"{rate} Hz, one synthesis at a time"
    )
    log()
    cancel = asyncio.Event()
    await synth.synthesize("namaste", cancel)  # warm-up, untimed

    log(f"1. time to first byte (= synthesis time), median of {repeat}")
    log(f"{'chars':>5} {'audio s':>8} {'p50 ms':>7} {'max ms':>7} {'RTF':>6}")
    for text in LENGTHS:
        times, pcm = [], b""
        for _ in range(repeat):
            started = perf_counter()
            pcm = await synth.synthesize(text, cancel) or b""
            times.append((perf_counter() - started) * 1000)
        audio_s = len(pcm) / 2 / rate
        p50 = median(times)
        # Real-time factor: synthesis time / audio length. Under 1 = faster
        # than real time, which is what lets later chunks keep up.
        log(
            f"{len(text):>5} {audio_s:>8.2f} {p50:>7.0f} {max(times):>7.0f} "
            f"{p50 / 1000 / audio_s:>6.3f}"
        )

    log()
    log("2. prosody: the same reply chunked three ways")
    for name, chunks in [
        ("aggressive", chunks_of(REPLY, first_min_chars=4)),
        ("conservative", chunks_of(REPLY, first_min_chars=60, first_max_chars=200)),
        ("whole", [REPLY]),
    ]:
        started = perf_counter()
        first = await synth.synthesize(chunks[0], cancel) or b""
        ttfb = (perf_counter() - started) * 1000
        rest = [await synth.synthesize(c, cancel) or b"" for c in chunks[1:]]
        with wave.open(str(OUT / f"prosody_{name}_{log.stamp}.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes(first + b"".join(rest))
        log(f"{name:>12}: first chunk {ttfb:.0f} ms, chunks {chunks}")
    # No WAV: only which of the three the committed config.toml matches.
    log(f"{'committed':>12}: chunks {chunks_of(REPLY)}")
    log()
    log(f"wrote {log.path.name} and prosody_*_{log.stamp}.wav")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--persona", default="default", help="whose voice to time")
    args = parser.parse_args()
    asyncio.run(main(args.repeat, args.persona))
