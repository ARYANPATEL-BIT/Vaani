"""A synthetic WebSocket client, so the gateway can be demonstrated without the
frontend.

It connects to /ws/session, starts a session, streams 10 seconds of 20 ms audio
frames at real-time pace (one every 20 ms), then ends the session. The audio is
a pure sine tone generated with only the standard library (`math`, `struct`), so
no audio files or extra packages are needed.

Run the server first:
    uv run uvicorn vaani.app:app
Then, in another terminal:
    uv run python scripts/fake_client.py

You should see the server log about 50 frames per second for ten seconds.
"""

import asyncio
import json
import math
import struct

import websockets

# These MUST match the server's config.toml [audio] block, otherwise the server
# replies UNSUPPORTED_FORMAT and rejects the session.
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_MS = 20
TONE_HZ = 440  # musical A; any audible frequency works, it is only a demo

SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 320
FRAME_SECONDS = FRAME_MS / 1000  # 0.02
DURATION_SECONDS = 10
URL = "ws://127.0.0.1:8000/ws/session"


def make_frame(start_sample: int) -> bytes:
    """Build one 20 ms frame of a sine tone as 16-bit little-endian PCM.

    `start_sample` is the running sample index so the wave is continuous across
    frames (each frame picks up where the last left off). Each sample is a
    signed 16-bit int packed little-endian ('<h'), matching the protocol.
    """
    samples = bytearray()
    for i in range(SAMPLES_PER_FRAME):
        t = (start_sample + i) / SAMPLE_RATE
        # 0.3 amplitude keeps it well short of clipping the 16-bit range.
        value = int(0.3 * 32767 * math.sin(2 * math.pi * TONE_HZ * t))
        samples += struct.pack("<h", value)
    return bytes(samples)


async def main() -> None:
    async with websockets.connect(URL) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "session.start",
                    "persona": "default",
                    "audio": {
                        "sample_rate": SAMPLE_RATE,
                        "channels": CHANNELS,
                        "frame_ms": FRAME_MS,
                    },
                }
            )
        )
        ack = json.loads(await ws.recv())
        print("server:", ack)

        total_frames = DURATION_SECONDS * 1000 // FRAME_MS  # 500
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        for n in range(total_frames):
            await ws.send(make_frame(n * SAMPLES_PER_FRAME))
            # Pace to real time: schedule each send one frame apart and sleep to
            # the next deadline, so we stream at ~50 frames/sec, not as fast as
            # possible. Drift is avoided by advancing an absolute deadline.
            next_deadline += FRAME_SECONDS
            await asyncio.sleep(max(0, next_deadline - loop.time()))

        await ws.send(json.dumps({"type": "session.end"}))
        print(f"sent {total_frames} frames, ended session")


if __name__ == "__main__":
    asyncio.run(main())
