"""End-to-end over the real WebSocket: speak a clip N times, time each reply.

For each turn the client streams, at real-time pace: 0.5 s of silence, the
clip, then silence until the server says turn.state idle (the reply is done).
It times, on its own clock:

  last voice -> transcript.final    endpointing + ASR
  last voice -> first agent.text    endpointing + ASR + model first token
  last voice -> first audio frame   ... + first chunk + its synthesis (day 12)

"Last voice" is the last clip frame louder than VOICE_RMS, i.e. roughly when
the speaker stopped. Both numbers include the loopback socket, which is
microseconds. The server's own turn_ended -> first agent.text and
turn_ended -> first audio frame are in its log (reply.py: "turn_ended->first
agent.text N ms"; speaker.py: "turn_ended->first audio N ms").

Run the server first (echo is off by default since day 12), e.g. on GPU ASR:
    VAANI_ASR__WHISPER__MODEL=large-v3 \
    VAANI_ASR__WHISPER__DEVICE=cuda VAANI_ASR__WHISPER__COMPUTE_TYPE=float16 \
    uv run --extra gpu uvicorn vaani.app:app
then:
    uv run python scripts/measure_turn.py --speech-wav hinglish_16k.wav --turns 12 \
        --label "cuda/large-v3, gemini"

Everything printed is also written to docs/findings/groq-primary/
measure_turn_<timestamp>.txt (run_log.py), one file per run. Earlier runs
stay where they were written (tts-day12/, reply-script/). This client
cannot see the server's settings, so --label (free text, e.g. the ASR device
and model the server was started with) goes into the file's header.
"""

import argparse
import asyncio
import json
import math
from array import array
from pathlib import Path
from statistics import median
from time import perf_counter

import websockets
from fake_client import (  # scripts/ is on sys.path when run as a file
    DEFAULT_SPEECH_WAV,
    DEFAULT_URL,
    FRAME_SECONDS,
    SILENT_FRAME,
    load_speech_frames,
)
from run_log import REPO, RunLog

OUT = REPO / "docs" / "findings" / "groq-primary"
VOICE_RMS = 300  # 16-bit sample RMS above which a frame counts as voiced
REPLY_TIMEOUT_S = 20.0


def p95(values: list[float]) -> float:
    """Nearest-rank p95, as telemetry.py computes it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def rms(frame: bytes) -> float:
    samples = array("h", frame)
    return math.sqrt(sum(s * s for s in samples) / len(samples))


async def one_turn(
    ws, clip: list[bytes], last_voiced: int, inbox: asyncio.Queue, log: RunLog
):
    """Speak once; return ms to final, to first text, to first audio, and
    the reply text."""
    loop = asyncio.get_running_loop()
    deadline = loop.time()
    script = [SILENT_FRAME] * 25 + clip
    voice_end = None
    for n, frame in enumerate(script):
        await ws.send(frame)
        if n == 25 + last_voiced:
            voice_end = perf_counter()
        deadline += FRAME_SECONDS
        await asyncio.sleep(max(0, deadline - loop.time()))
    final_at = first_text_at = first_audio_at = None
    reply = ""
    stop_at = loop.time() + REPLY_TIMEOUT_S
    while loop.time() < stop_at:
        await ws.send(SILENT_FRAME)  # the mic stays open: keep streaming
        deadline += FRAME_SECONDS
        while not inbox.empty():
            at, msg = inbox.get_nowait()
            if msg["type"] == "transcript.final":
                final_at = at
                log(f"  heard: {msg['text']!r}")
            elif msg["type"] == "agent.text":
                first_text_at = first_text_at or at
                reply += msg["delta"]
            elif msg["type"] == "frame":
                first_audio_at = first_audio_at or at
            elif msg["type"] == "error":
                log(f"  error: {msg}")
            elif msg.get("state") == "idle" and final_at is not None:
                return (
                    (final_at - voice_end) * 1000,
                    None
                    if first_text_at is None
                    else (first_text_at - voice_end) * 1000,
                    None
                    if first_audio_at is None
                    else (first_audio_at - voice_end) * 1000,
                    reply,
                )
        await asyncio.sleep(max(0, deadline - loop.time()))
    raise TimeoutError("no reply within the timeout")


def fmt(ms: float | None) -> str:
    return "none" if ms is None else f"{ms:.0f}"


async def main(url: str, wav: Path, turns: int, label: str) -> None:
    log = RunLog("measure_turn", out=OUT)
    log(f"server: {url} ({label or 'no --label given'})")
    log(f"clip: {wav.name}, {turns} turns")
    clip = load_speech_frames(wav)
    last_voiced = max(i for i, f in enumerate(clip) if rms(f) > VOICE_RMS)
    inbox: asyncio.Queue = asyncio.Queue()
    to_final, to_text, to_audio = [], [], []
    model_ms, tts_ms = [], []  # per-turn stage gaps, see "per stage" below
    async with websockets.connect(url) as ws:
        start = {
            "type": "session.start",
            "persona": "default",
            "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 20},
        }
        await ws.send(json.dumps(start))
        log(f"server: {json.loads(await ws.recv())}")

        async def receive() -> None:
            async for message in ws:
                if isinstance(message, str):
                    await inbox.put((perf_counter(), json.loads(message)))
                else:  # an audio frame: only its arrival time matters
                    await inbox.put((perf_counter(), {"type": "frame"}))

        receiver = asyncio.create_task(receive())
        for t in range(turns):
            log(f"turn {t + 1}:")
            final_ms, text_ms, audio_ms, reply = await one_turn(
                ws, clip, last_voiced, inbox, log
            )
            log(f"  reply: {reply!r}")
            log(
                f"  last voice -> final {fmt(final_ms)} ms, -> first text "
                f"{fmt(text_ms)} ms, -> first audio {fmt(audio_ms)} ms"
            )
            to_final.append(final_ms)
            if text_ms is not None:
                to_text.append(text_ms)
                model_ms.append(text_ms - final_ms)
            if audio_ms is not None:
                to_audio.append(audio_ms)
            if text_ms is not None and audio_ms is not None:
                tts_ms.append(audio_ms - text_ms)
        await ws.send(json.dumps({"type": "session.end"}))
        receiver.cancel()

    log()
    log(f"over {turns} turns (client clock, from the speaker's last voiced frame):")
    log(
        f"  -> transcript.final  p50 {median(to_final):.0f}  p95 {p95(to_final):.0f} ms"
    )
    if to_text:
        log(
            f"  -> first agent.text  p50 {median(to_text):.0f}"
            f"  p95 {p95(to_text):.0f} ms"
        )
    if to_audio:
        log(
            f"  -> first audio frame p50 {median(to_audio):.0f}"
            f"  p95 {p95(to_audio):.0f} ms"
        )
    # Per stage: the gaps between the three arrivals above, per turn, so a
    # slower total can be pinned on one stage. "model" starts at
    # transcript.final because reply.py dispatches the request right then.
    log("per stage (client clock):")
    for stage, gaps in (
        ("endpoint + ASR", to_final),
        ("model first token", model_ms),
        ("first chunk + TTS", tts_ms),
    ):
        if gaps:
            log(f"  {stage:18s} p50 {median(gaps):5.0f}  p95 {p95(gaps):5.0f} ms")
    log(f"wrote {log.path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--speech-wav", type=Path, default=DEFAULT_SPEECH_WAV)
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--label", default="", help="server setup, for the file")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.speech_wav, args.turns, args.label))
