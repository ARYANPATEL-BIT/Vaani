"""What loading several Piper voices costs, and how fast each one speaks.

Day 15 (persona voices) gives each persona its own Piper voice. Before
choosing, this measures, for every voice named on the command line, in ONE
process and in the order given:

1. LOAD: seconds for PiperVoice.load (read the .onnx, build the ONNX Runtime
   session), seconds for the first synthesis (espeak-ng start-up and ONNX
   warm-up), and the process's resident memory (RSS) after each step. RSS is
   read from Windows (GetProcessMemoryInfo), because ONNX Runtime allocates
   outside Python, where tracemalloc cannot see it.
2. LOCK: two threads phonemise different texts with two different voices at
   once, many times, and every result is compared with the same text
   phonemised alone. Any mismatch means espeak-ng state leaked between voices.
3. TIMING: synthesis time and real-time factor (RTF = synthesis time / audio
   length) per voice for the same texts, median and max of --repeat, after
   the warm-up. Direct PiperVoice.synthesize calls, one at a time: this
   compares voices, it is not the server path (measure_tts.py is).

Everything printed is also written to docs/findings/persona-voices/
measure_voices_<timestamp>.txt, with the power scheme in the header
(run_log.py). Run it three times for three run files.

    uv run python scripts/measure_voices.py VOICE [VOICE ...]

Day 15 ran it with hi_IN-priyamvada-medium hi_IN-pratham-medium
hi_IN-rohan-medium, rotating which voice loads first between runs.
"""

import argparse
import ctypes
import threading
from ctypes import wintypes
from pathlib import Path
from statistics import median
from time import perf_counter

from run_log import REPO, RunLog  # scripts/ is on sys.path when run as a file

MODELS = Path(__file__).resolve().parent.parent / "models"
OUT = REPO / "docs" / "findings" / "persona-voices"

# measure_tts.py's lengths, shortest first: a first chunk, a clause, a
# sentence, and a long two-clause sentence. Devanagari reply format.
TEXTS = [
    "जी,",
    "मैं आपको याद दिला दूँगी।",
    "ठीक है, मैं कल सुबह आठ बजे आपको याद दिला दूँगी।",
    "ठीक है, मैं कल सुबह आठ बजे आपको याद दिला दूँगी, और ट्रैफ़िक का अपडेट "
    "भी दे दूँगी ताकि आप टाइम पर निकल सकें।",
]


class _Counters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS from the Windows API (psapi.h)."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_kernel32 = ctypes.windll.kernel32
# Declared, not left to ctypes' default (a 32-bit int): a process handle is
# 64 bits wide, and a truncated one makes the call fail and report 0.
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.K32GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(_Counters),
    wintypes.DWORD,
]
_kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL


def rss_mb() -> float:
    """This process's working set (resident memory) in MB."""
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    if not _kernel32.K32GetProcessMemoryInfo(
        _kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
    ):
        raise ctypes.WinError()
    return c.WorkingSetSize / 2**20


def synth(voice, text: str) -> tuple[float, float]:
    """(synthesis ms, audio seconds) for one call."""
    started = perf_counter()
    pcm = b"".join(c.audio_int16_bytes for c in voice.synthesize(text))
    return (perf_counter() - started) * 1000, len(pcm) / 2 / voice.config.sample_rate


def lock_check(log: RunLog, a, b, rounds: int) -> None:
    """Phonemise with two voices on two threads at once; compare to alone."""
    texts = (TEXTS[3], TEXTS[2])
    expected = [a.phonemize(texts[0]), b.phonemize(texts[1])]
    mismatches = [0, 0]

    def hammer(i: int, voice) -> None:
        for _ in range(rounds):
            if voice.phonemize(texts[i]) != expected[i]:
                mismatches[i] += 1

    threads = [
        threading.Thread(target=hammer, args=(i, v)) for i, v in enumerate((a, b))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log(f"{rounds} rounds per thread, mismatches {mismatches[0]} and {mismatches[1]}")


def main(names: list[str], repeat: int, rounds: int) -> None:
    log = RunLog("measure_voices", out=OUT)
    log(f"voices {names}, repeat {repeat}")
    log()
    log("1. load, in this order, in one process")
    base = rss_mb()
    from piper import PiperVoice  # after the baseline: the import has a cost too

    log(f"RSS before: {base:.0f} MB; after `import piper`: {rss_mb():.0f} MB")
    log(f"{'voice':<26} {'load s':>7} {'warm s':>7} {'RSS MB':>7} {'+MB':>6} {'Hz':>6}")
    voices = {}
    for name in names:
        before = rss_mb()
        started = perf_counter()
        voice = PiperVoice.load(MODELS / f"{name}.onnx")
        loaded = perf_counter() - started
        started = perf_counter()
        synth(voice, "namaste")
        warm = perf_counter() - started
        after = rss_mb()
        voices[name] = voice
        log(
            f"{name:<26} {loaded:>7.2f} {warm:>7.2f} {after:>7.0f} "
            f"{after - before:>6.0f} {voice.config.sample_rate:>6}"
        )
    log(f"all {len(names)} loaded: {rss_mb() - base:.0f} MB over the baseline")

    if len(voices) >= 2:
        log()
        log("2. espeak-ng lock: two voices phonemising on two threads")
        a, b = list(voices.values())[:2]
        lock_check(log, a, b, rounds)

    log()
    log(f"3. synthesis time, median and max of {repeat}, one call at a time")
    log(
        f"{'voice':<26} {'chars':>5} {'audio s':>8} "
        f"{'p50 ms':>7} {'max ms':>7} {'RTF':>6}"
    )
    for name, voice in voices.items():
        for text in TEXTS:
            runs = [synth(voice, text) for _ in range(repeat)]
            times = [ms for ms, _ in runs]
            audio_s = runs[-1][1]
            p50 = median(times)
            log(
                f"{name:<26} {len(text):>5} {audio_s:>8.2f} {p50:>7.0f} "
                f"{max(times):>7.0f} {p50 / 1000 / audio_s:>6.3f}"
            )
    log()
    log(f"wrote {log.path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("voices", nargs="+")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=200)
    args = parser.parse_args()
    main(args.voices, args.repeat, args.rounds)
