"""End-to-end over the real WebSocket: speak a clip N times, time each reply.

For each turn the client streams, at real-time pace: 0.5 s of silence, the
clip, then silence until the server says turn.state idle (the reply is done).
It times, on its own clock:

  last voice -> transcript.final    endpointing + ASR
  last voice -> first agent.text    endpointing + ASR + model first token

"Last voice" is the last clip frame louder than VOICE_RMS, i.e. roughly when
the speaker stopped. Both numbers include the loopback socket, which is
microseconds. The server's own turn_ended -> first agent.text is in its log
(reply.py: "first token: ... turn_ended->first agent.text N ms").

Run the server first (echo off, so no audio comes back), e.g. on GPU ASR:
    VAANI_GATEWAY__ECHO_ENABLED=false VAANI_ASR__WHISPER__MODEL=large-v3 \
    VAANI_ASR__WHISPER__DEVICE=cuda VAANI_ASR__WHISPER__COMPUTE_TYPE=float16 \
    uv run --extra gpu uvicorn vaani.app:app
then:
    uv run python scripts/measure_turn.py --speech-wav hinglish_16k.wav --turns 12
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

VOICE_RMS = 300  # 16-bit sample RMS above which a frame counts as voiced
REPLY_TIMEOUT_S = 20.0


def p95(values: list[float]) -> float:
    """Nearest-rank p95, as telemetry.py computes it."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def rms(frame: bytes) -> float:
    samples = array("h", frame)
    return math.sqrt(sum(s * s for s in samples) / len(samples))


async def one_turn(ws, clip: list[bytes], last_voiced: int, inbox: asyncio.Queue):
    """Speak once; return (ms to final, ms to first text, reply text)."""
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
    final_at = first_text_at = None
    reply = ""
    stop_at = loop.time() + REPLY_TIMEOUT_S
    while loop.time() < stop_at:
        await ws.send(SILENT_FRAME)  # the mic stays open: keep streaming
        deadline += FRAME_SECONDS
        while not inbox.empty():
            at, msg = inbox.get_nowait()
            if msg["type"] == "transcript.final":
                final_at = at
                print(f"  heard: {msg['text']!r}")
            elif msg["type"] == "agent.text":
                first_text_at = first_text_at or at
                reply += msg["delta"]
            elif msg["type"] == "error":
                print(f"  error: {msg}")
            elif msg.get("state") == "idle" and final_at is not None:
                return (
                    (final_at - voice_end) * 1000,
                    None
                    if first_text_at is None
                    else (first_text_at - voice_end) * 1000,
                    reply,
                )
        await asyncio.sleep(max(0, deadline - loop.time()))
    raise TimeoutError("no reply within the timeout")


async def main(url: str, wav: Path, turns: int) -> None:
    clip = load_speech_frames(wav)
    last_voiced = max(i for i, f in enumerate(clip) if rms(f) > VOICE_RMS)
    inbox: asyncio.Queue = asyncio.Queue()
    to_final, to_text = [], []
    async with websockets.connect(url) as ws:
        start = {
            "type": "session.start",
            "persona": "default",
            "audio": {"sample_rate": 16000, "channels": 1, "frame_ms": 20},
        }
        await ws.send(json.dumps(start))
        print("server:", json.loads(await ws.recv()))

        async def receive() -> None:
            async for message in ws:
                if isinstance(message, str):  # ignore any audio
                    await inbox.put((perf_counter(), json.loads(message)))

        receiver = asyncio.create_task(receive())
        for t in range(turns):
            print(f"turn {t + 1}:")
            final_ms, text_ms, reply = await one_turn(ws, clip, last_voiced, inbox)
            print(f"  reply: {reply!r}")
            print(
                f"  last voice -> final {final_ms:.0f} ms, -> first text {text_ms} ms"
            )
            to_final.append(final_ms)
            if text_ms is not None:
                to_text.append(text_ms)
        await ws.send(json.dumps({"type": "session.end"}))
        receiver.cancel()

    print(f"\nover {turns} turns (client clock, from the speaker's last voiced frame):")
    print(
        f"  -> transcript.final  p50 {median(to_final):.0f}  p95 {p95(to_final):.0f} ms"
    )
    if to_text:
        print(
            f"  -> first agent.text  p50 {median(to_text):.0f}"
            f"  p95 {p95(to_text):.0f} ms"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--speech-wav", type=Path, default=DEFAULT_SPEECH_WAV)
    parser.add_argument("--turns", type=int, default=12)
    args = parser.parse_args()
    asyncio.run(main(args.url, args.speech_wav, args.turns))
