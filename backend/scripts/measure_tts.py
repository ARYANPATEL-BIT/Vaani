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
   Written to docs/findings/tts-day12/prosody_<name>.wav, for listening.

    uv run python scripts/measure_tts.py
"""

import argparse
import asyncio
import re
import wave
from pathlib import Path
from statistics import median
from time import perf_counter

from vaani.chunker import ClauseChunker
from vaani.config import get_settings
from vaani.tts import build_synthesizer

OUT = Path(__file__).resolve().parent.parent.parent / "docs/findings/tts-day12"

LENGTHS = [
    "Theek hai,",
    "Main aapko yaad dila doongi.",
    "Theek hai, main kal subah aath baje aapko yaad dila doongi.",
    "Theek hai, main kal subah aath baje aapko yaad dila doongi, aur traffic "
    "ka update bhi de doongi taaki aap time par nikal sakein.",
    "Theek hai, main kal subah aath baje aapko yaad dila doongi, aur traffic "
    "ka update bhi de doongi taaki aap time par nikal sakein, kyunki subah "
    "ke samay highway par bahut bheed hoti hai aur dentist ka clinic door hai.",
]

REPLY = (
    "Theek hai, main kal subah 8 baje yaad dila doongi aur traffic ka update "
    "bhi de doongi. Agar aap chahein toh main dentist ka address bhi bhej "
    "sakti hoon."
)


def chunks_of(text: str, **cfg) -> list[str]:
    chunker = ClauseChunker(get_settings().chunker.model_copy(update=cfg))
    out = []
    for token in re.findall(r"\S+\s*", text):
        out += chunker.push(token)
    if (last := chunker.flush()) is not None:
        out.append(last)
    return out


async def main(repeat: int) -> None:
    synth = build_synthesizer(get_settings().tts)
    rate = synth.sample_rate
    cancel = asyncio.Event()
    await synth.synthesize("namaste", cancel)  # warm-up, untimed

    print(f"1. time to first byte (= synthesis time), median of {repeat}")
    print(f"{'chars':>5} {'audio s':>8} {'p50 ms':>7} {'max ms':>7} {'RTF':>6}")
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
        print(
            f"{len(text):>5} {audio_s:>8.2f} {p50:>7.0f} {max(times):>7.0f} "
            f"{p50 / 1000 / audio_s:>6.3f}"
        )

    print("\n2. prosody: the same reply chunked three ways")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, chunks in [
        ("aggressive", chunks_of(REPLY, first_min_chars=4)),
        ("conservative", chunks_of(REPLY, first_min_chars=60, first_max_chars=200)),
        ("whole", [REPLY]),
    ]:
        started = perf_counter()
        first = await synth.synthesize(chunks[0], cancel) or b""
        ttfb = (perf_counter() - started) * 1000
        rest = [await synth.synthesize(c, cancel) or b"" for c in chunks[1:]]
        with wave.open(str(OUT / f"prosody_{name}.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes(first + b"".join(rest))
        print(f"{name:>12}: first chunk {ttfb:.0f} ms, chunks {chunks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    asyncio.run(main(parser.parse_args().repeat))
