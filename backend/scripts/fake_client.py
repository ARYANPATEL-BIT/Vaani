"""A synthetic WebSocket client, so the gateway can be demonstrated without the
frontend.

It connects to /ws/session, starts a session, streams audio frames at
real-time pace (one per frame_ms) for --duration seconds (default 10), then
ends the session. The audio is
a pure sine tone generated with only the standard library (`math`, `struct`), so
no audio files or extra packages are needed.

Because the server now ECHOES every frame back (day 3), the client also runs a
receiver coroutine alongside the sender: websockets lets us send and receive on
the same connection at once. The receiver counts the echoed frames and prints
the audio.start / audio.end control messages that bracket them.

Day 4: with --flush-after SECONDS the client sends the development-only
dev.flush message at that point in the stream. The server replies audio.flush;
the receiver answers flush.ack at once (as a browser would after silencing its
speaker) and from then on DISCARDS any frame for the flushed turn, counting
them instead of playing them.

Day 8: with --speech-s A --silence-s B the client alternates A seconds of
SPEECH with B seconds of real silence (all-zero frames), repeating, so VAD can
be tested without a microphone. The speech is a recorded clip
(tests/fixtures/speech_16k_mono.wav), not the tone: Silero is trained to
reject pure tones, so a tone never registers as speech. The client prints
each switch with its time so it can be matched against the server's
speech_started / speech_ended log lines.

Day 9: --turn-test sends one fixed script instead: 0.5 s silence, the clip,
a 0.4 s pause, the clip again, 2 s silence. The server must log exactly ONE
turn_ended: the short pause is someone thinking, not the end of the turn.

Run the server first:
    uv run uvicorn vaani.app:app
Then, in another terminal:
    uv run python scripts/fake_client.py
    uv run python scripts/fake_client.py --flush-after 3
    uv run python scripts/fake_client.py --duration 600   # 10-minute soak
    uv run python scripts/fake_client.py --speech-s 3 --silence-s 2
    uv run python scripts/fake_client.py --turn-test

You should see the server log about 50 frames per second with a median echo
time, and the client should report ~500 echoed frames received.
"""

import argparse
import asyncio
import json
import math
import struct
import time
import wave
from pathlib import Path

import websockets

from vaani.config import get_settings

# The audio format comes from the same config.toml [audio] block the server
# reads, so the two cannot drift apart (a mismatch gets UNSUPPORTED_FORMAT).
_AUDIO = get_settings().audio
SAMPLE_RATE = _AUDIO.sample_rate
CHANNELS = _AUDIO.channels
FRAME_MS = _AUDIO.frame_ms
TONE_HZ = 440  # musical A; any audible frequency works, it is only a demo

SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 320
FRAME_SECONDS = FRAME_MS / 1000  # 0.02
# The address uvicorn listens on by default. A dev-script default, overridable
# with --url; the server itself has no URL setting to read it from.
DEFAULT_URL = "ws://127.0.0.1:8000/ws/session"
# Speech clip for --speech-s; regenerate with scripts/make_speech_fixture.ps1.
DEFAULT_SPEECH_WAV = (
    Path(__file__).resolve().parent.parent / "tests/fixtures/speech_16k_mono.wav"
)
SILENT_FRAME = b"\x00" * (SAMPLES_PER_FRAME * CHANNELS * 2)


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


def load_speech_frames(path: Path) -> list[bytes]:
    """Split a WAV file into protocol-sized frames (a partial tail is dropped).

    The WAV must already be in our wire format; we check rather than resample,
    so a wrong file fails loudly instead of sending distorted audio.
    """
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
            SAMPLE_RATE,
            CHANNELS,
            2,
        ):
            raise SystemExit(f"{path} is not {SAMPLE_RATE} Hz / {CHANNELS} ch / 16-bit")
        pcm = wav.readframes(wav.getnframes())
    size = SAMPLES_PER_FRAME * CHANNELS * 2
    return [pcm[i : i + size] for i in range(0, len(pcm) - size + 1, size)]


def turn_test_frames(speech: list[bytes]) -> list[bytes]:
    """The --turn-test script: silence, clip, short pause, clip, long silence.

    The clip's all-zero lead-in and tail are stripped first. Left in, they
    would stretch the 0.4 s pause to about 1.2 s, which SHOULD end the turn.
    """
    voiced = [i for i, frame in enumerate(speech) if any(frame)]
    clip = speech[voiced[0] : voiced[-1] + 1]

    def silence(seconds: float) -> list[bytes]:
        return [SILENT_FRAME] * round(seconds / FRAME_SECONDS)

    return silence(0.5) + clip + silence(0.4) + clip + silence(2.0)


def alternating_frame(
    n: int, speech: list[bytes], speech_frames: int, silence_frames: int
) -> tuple[bytes, bool]:
    """Frame n of the speech/silence pattern, and whether it is speech.

    Each cycle is speech_frames of speech then silence_frames of zeros. The
    clip restarts every cycle (and loops if a speech phase outlasts it).
    """
    pos = n % (speech_frames + silence_frames)
    if pos < speech_frames:
        return speech[pos % len(speech)], True
    return SILENT_FRAME, False


async def receive_echo(ws) -> None:
    """Read echoed audio and control messages until the server closes the socket.

    `async for message in ws` yields each incoming message; websockets hands us
    `bytes` for a binary (audio) message and `str` for a text (JSON control)
    message. We count the audio frames and print the control ones. The loop ends
    when the server closes the socket, which raises ConnectionClosedOK.

    Like the browser, we track which turn each frame belongs to (the latest
    audio.start) and drop frames for any turn we have been told to flush.
    """
    frames = 0
    discarded = 0
    current_turn = None
    flushed_turns = set()
    try:
        async for message in ws:
            if isinstance(message, bytes):
                if current_turn in flushed_turns:
                    discarded += 1  # late frame for a flushed turn: never play
                else:
                    frames += 1
                continue
            msg = json.loads(message)
            print("server:", msg)
            if msg["type"] == "audio.start":
                current_turn = msg["turn_id"]
            elif msg["type"] == "audio.flush":
                flushed_turns.add(msg["turn_id"])
                # A browser would stop its audio here, then ack. client_ts is
                # our own clock in ms; the server only logs it, never subtracts.
                ack = {
                    "type": "flush.ack",
                    "turn_id": msg["turn_id"],
                    "client_ts": time.perf_counter() * 1000,
                }
                await ws.send(json.dumps(ack))
                print("client: sent flush.ack")
    except websockets.ConnectionClosedOK:
        pass
    print(f"received {frames} echoed frames, discarded {discarded} late frames")


async def main(
    url: str,
    duration_s: float,
    flush_after: float | None,
    pattern: tuple[float, float] | None,
    speech_wav: Path,
    turn_test: bool,
) -> None:
    # Which frame index to send dev.flush before; None means never flush.
    flush_at = None if flush_after is None else int(flush_after / FRAME_SECONDS)
    async with websockets.connect(url) as ws:
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

        # Start reading echoes now, concurrently with the send loop below.
        receiver = asyncio.create_task(receive_echo(ws))

        total_frames = int(duration_s / FRAME_SECONDS)  # 500 for 10 s
        script = None
        if turn_test:
            script = turn_test_frames(load_speech_frames(speech_wav))
            total_frames = len(script)
            print(f"client: turn test, {total_frames} frames; expect ONE turn_ended")
        if pattern is not None:
            speech = load_speech_frames(speech_wav)
            speech_frames = round(pattern[0] / FRAME_SECONDS)
            silence_frames = round(pattern[1] / FRAME_SECONDS)
        was_speech = None
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        for n in range(total_frames):
            if n == flush_at:
                # DEV-ONLY message: stands in for barge-in until VAD exists.
                await ws.send(json.dumps({"type": "dev.flush"}))
                print(f"client: sent dev.flush at {flush_after}s")
            if script is not None:
                frame = script[n]
            elif pattern is None:
                frame = make_frame(n * SAMPLES_PER_FRAME)
            else:
                frame, is_speech = alternating_frame(
                    n, speech, speech_frames, silence_frames
                )
                if is_speech != was_speech:
                    phase = "speech" if is_speech else "silence"
                    print(f"client: {phase} from frame {n} ({n * FRAME_SECONDS:.2f}s)")
                    was_speech = is_speech
            await ws.send(frame)
            # Pace to real time: schedule each send one frame apart and sleep to
            # the next deadline, so we stream at ~50 frames/sec, not as fast as
            # possible. Drift is avoided by advancing an absolute deadline.
            next_deadline += FRAME_SECONDS
            await asyncio.sleep(max(0, next_deadline - loop.time()))

        await ws.send(json.dumps({"type": "session.end"}))
        print(f"sent {total_frames} frames, ended session")

        # Wait for the receiver to drain audio.end and the close before exiting.
        await receiver


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="how long to stream audio (default 10)",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="gateway WebSocket URL")
    parser.add_argument(
        "--flush-after",
        type=float,
        metavar="SECONDS",
        help="send dev.flush this many seconds into the stream",
    )
    parser.add_argument(
        "--speech-s",
        type=float,
        metavar="SECONDS",
        help="alternate this many seconds of speech with --silence-s of silence",
    )
    parser.add_argument(
        "--silence-s",
        type=float,
        metavar="SECONDS",
        help="seconds of all-zero silence between speech phases",
    )
    parser.add_argument(
        "--speech-wav",
        type=Path,
        default=DEFAULT_SPEECH_WAV,
        help="16 kHz mono 16-bit WAV used for the speech phase",
    )
    parser.add_argument(
        "--turn-test",
        action="store_true",
        help="send speech, a 0.4 s pause, speech, 2 s silence: expect one turn",
    )
    args = parser.parse_args()
    if (args.speech_s is None) != (args.silence_s is None):
        parser.error("--speech-s and --silence-s go together")
    pattern = None if args.speech_s is None else (args.speech_s, args.silence_s)
    asyncio.run(
        main(
            args.url,
            args.duration,
            args.flush_after,
            pattern,
            args.speech_wav,
            args.turn_test,
        )
    )
