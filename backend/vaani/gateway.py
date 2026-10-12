"""The /ws/session WebSocket endpoint: session lifecycle and ingest validation.

One coroutine runs per connection (FastAPI gives us that for free), and that
coroutine owns the whole session. It accepts the socket, reads messages in a
loop, validates each one at the moment it arrives, and cleans up in a `finally`
block however the connection ends. A separate background task logs the
per-interval frame count so the read loop — the start of the latency-critical
audio path — is never blocked by logging.

What happens to a valid audio frame after validation (VAD, endpointing,
turns, speech recognition, the day-3 echo) lives in turns.py: this file hands
each frame to the session's TurnPipeline and stays a dispatcher.

Day 4 FLUSH: the server tells the browser to silence a turn (audio.flush);
the browser's flush.ack, handled here, closes the round trip.

Day 11: session.start's persona must be a key of config.toml's [personas].

Day 12: the agent's reply is spoken; its audio leaves through the same
send_bytes as the echo did (speaker.py, called from reply.py).

Day 13: barge-in. It is decided frame by frame inside TurnPipeline.on_frame
(turns.py, barge_in.py), so nothing here changes except that the dev-only
dev.flush message, its stand-in since day 4, is gone (protocol v0.7).

Push-to-talk (v0.9): session.start's mode is kept on the Session, and
ptt.start / ptt.end go to the pipeline, in a ptt session only.
"""

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from vaani.config import AudioSettings, Settings
from vaani.protocol import (
    ErrorCode,
    FlushAck,
    SessionStart,
    error,
    session_started,
)
from vaani.session import Session
from vaani.telemetry import Telemetry
from vaani.turns import TurnPipeline

log = logging.getLogger("vaani.gateway")

# WebSocket close code for a normal, intentional shutdown (RFC 6455).
CLOSE_NORMAL = 1000

router = APIRouter()


def expected_frame_bytes(audio: AudioSettings) -> int:
    """Bytes in one valid audio frame, derived entirely from config.

    samples_per_frame = sample_rate * frame_ms / 1000
    bytes = samples_per_frame * channels * 2   (2 bytes per 16-bit sample)

    For 16 kHz / 20 ms / mono this is 320 * 1 * 2 = 640. We compute it so the
    number is never hardcoded and follows the config if it ever changes.
    """
    samples_per_frame = audio.sample_rate * audio.frame_ms // 1000
    return samples_per_frame * audio.channels * 2


def _audio_matches(claimed, expected: AudioSettings) -> bool:
    """True if the client's declared audio format matches what we serve."""
    return (
        claimed.sample_rate == expected.sample_rate
        and claimed.channels == expected.channels
        and claimed.frame_ms == expected.frame_ms
    )


def _fmt_ms(stats: tuple[float, float] | None) -> str:
    """'p50=1.234ms p95=5.678ms', or dashes while there are too few samples."""
    if stats is None:
        return "p50=- p95=-"
    return f"p50={stats[0]:.3f}ms p95={stats[1]:.3f}ms"


async def _log_frames(
    session: Session, telemetry: Telemetry, interval_s: float, vad_enabled: bool
) -> None:
    """Background task: every `interval_s`, log frame count, echo and VAD timing.

    It reads and resets the session's interval counter and reads the rolling
    statistics. Because everything runs on one event loop (no real threads),
    the read-and-reset cannot interleave with the read loop's increment, so no
    lock is needed. Cancellation (on disconnect) surfaces as CancelledError out
    of `sleep`, which ends the task.

    The stats are None until enough samples exist; _fmt_ms prints dashes then
    so an early, meaningless number is never shown.
    """
    while True:
        await asyncio.sleep(interval_s)
        count = session.take_interval_count()
        vad = _fmt_ms(telemetry.vad_stats_ms()) if vad_enabled else "off"
        log.info(
            "session %s: %d frames in last %.3fs (echo %s) (vad %s)",
            session.session_id,
            count,
            interval_s,
            _fmt_ms(telemetry.echo_stats_ms()),
            vad,
        )


@router.websocket("/ws/session")
async def session_endpoint(websocket: WebSocket) -> None:
    """Handle one WebSocket connection for its entire lifetime."""
    settings: Settings = websocket.app.state.settings
    audio_cfg = settings.audio
    expected = expected_frame_bytes(audio_cfg)
    interval_s = settings.gateway.frame_log_interval_s
    vad_enabled = settings.vad.enabled

    await websocket.accept()

    session: Session | None = None
    telemetry: Telemetry | None = None
    pipeline: TurnPipeline | None = None
    log_task: asyncio.Task | None = None

    try:
        while True:
            event = await websocket.receive()

            # The client closed the socket; leave the loop and let `finally`
            # clean up. Using the raw event lets us see disconnects explicitly.
            if event["type"] == "websocket.disconnect":
                break

            # --- Binary path: an audio frame ---------------------------------
            data = event.get("bytes")
            if data is not None:
                if session is None:
                    await websocket.send_json(
                        error(ErrorCode.SESSION_NOT_STARTED, "send session.start first")
                    )
                    continue
                if len(data) != expected:
                    await websocket.send_json(
                        error(
                            ErrorCode.BAD_FRAME_SIZE,
                            f"expected {expected} bytes, got {len(data)}",
                        )
                    )
                    continue
                session.record_frame()
                if pipeline is not None:
                    await pipeline.on_frame(data)
                continue

            # --- Text path: a JSON control message ---------------------------
            text = event.get("text")
            if text is None:
                continue  # ignore any other ASGI event kind

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await websocket.send_json(
                    error(ErrorCode.BAD_MESSAGE, "not valid JSON")
                )
                continue
            if not isinstance(payload, dict) or "type" not in payload:
                await websocket.send_json(
                    error(ErrorCode.BAD_MESSAGE, "missing 'type'")
                )
                continue

            mtype = payload["type"]

            if mtype == "session.start":
                try:
                    start = SessionStart.model_validate(payload)
                except ValidationError:
                    await websocket.send_json(
                        error(ErrorCode.BAD_MESSAGE, "malformed session.start")
                    )
                    continue
                # A second session.start on a live session is idempotent: just
                # re-acknowledge the existing session id, don't make a new one.
                if session is not None:
                    await websocket.send_json(
                        session_started(session.session_id, session.mode)
                    )
                    continue
                if not _audio_matches(start.audio, audio_cfg):
                    await websocket.send_json(
                        error(
                            ErrorCode.UNSUPPORTED_FORMAT, "audio settings not supported"
                        )
                    )
                    continue
                if start.persona not in settings.personas:
                    await websocket.send_json(
                        error(
                            ErrorCode.BAD_MESSAGE, f"unknown persona: {start.persona}"
                        )
                    )
                    continue
                session = Session(
                    session_id=uuid.uuid4().hex, persona=start.persona, mode=start.mode
                )
                telemetry = Telemetry(session.session_id)
                # Fresh per-session VAD / endpointing / ASR / reply state. The
                # models (VAD, Whisper) and the LLM chain are built once per
                # process and shared; getattr gives None for one disabled.
                # The voices are the persona's (day 15), chosen once here,
                # never per turn: one per language, and each reply's first
                # chunk picks between them (speaker.py). {} when TTS is off,
                # so .get gives None.
                voices = getattr(websocket.app.state, "synthesizers", {}).get(
                    session.persona
                )
                pipeline = TurnPipeline(
                    settings,
                    session,
                    telemetry,
                    websocket.send_json,
                    websocket.send_bytes,
                    getattr(websocket.app.state, "vad_model", None),
                    getattr(websocket.app.state, "recognizer", None),
                    getattr(websocket.app.state, "llm", None),
                    voices,
                )
                log_task = asyncio.create_task(
                    _log_frames(session, telemetry, interval_s, vad_enabled)
                )
                await websocket.send_json(
                    session_started(session.session_id, session.mode)
                )
                continue

            # Every other control message requires a live session first.
            if session is None:
                await websocket.send_json(
                    error(ErrorCode.SESSION_NOT_STARTED, "send session.start first")
                )
                continue

            if mtype == "flush.ack":
                try:
                    ack = FlushAck.model_validate(payload)
                except ValidationError:
                    await websocket.send_json(
                        error(ErrorCode.BAD_MESSAGE, "malformed flush.ack")
                    )
                    continue
                # Acks for turns never flushed, or acked twice, are logged and
                # ignored inside the session.
                session.handle_flush_ack(ack, telemetry)
                continue

            if mtype in ("ptt.start", "ptt.end"):
                # No field but "type", so nothing more to validate.
                if session.mode != "ptt":
                    await websocket.send_json(
                        error(ErrorCode.BAD_MESSAGE, f"{mtype} needs a ptt session")
                    )
                elif mtype == "ptt.start":
                    await pipeline.on_ptt_start()
                else:
                    await pipeline.on_ptt_end()
                continue

            if mtype == "session.end":
                # Close the open echo turn cleanly before we close the socket.
                # (On a hard disconnect we cannot send this — the browser must
                # treat a closed socket as an implicit audio.end.)
                if pipeline is not None:
                    await pipeline.on_session_end()
                await websocket.close(code=CLOSE_NORMAL)
                break

            await websocket.send_json(
                error(ErrorCode.UNKNOWN_MESSAGE_TYPE, f"unknown type: {mtype}")
            )

    except WebSocketDisconnect:
        # Client vanished mid-read; nothing to send, just fall through to cleanup.
        pass
    finally:
        # Stop the logger however we got here (clean end, disconnect, or error).
        if log_task is not None:
            log_task.cancel()
            with suppress(asyncio.CancelledError):
                await log_task
        # Abandon recognition in flight: a result for a closed socket must
        # never be sent, and must not keep a task alive.
        if pipeline is not None:
            await pipeline.close()
        if session is not None:
            log.info(
                "session %s closed: %d frames total, %d late frames dropped",
                session.session_id,
                session.frame_count,
                session.late_frames_dropped,
            )
