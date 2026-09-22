"""The /ws/session WebSocket endpoint: session lifecycle and ingest validation.

One coroutine runs per connection (FastAPI gives us that for free), and that
coroutine owns the whole session. It accepts the socket, reads messages in a
loop, validates each one at the moment it arrives, and cleans up in a `finally`
block however the connection ends. A separate background task logs the
per-interval frame count so the read loop — the start of the latency-critical
audio path — is never blocked by logging.

What this file does NOT do yet: echo audio, run VAD, or call any provider.
Today it only proves the transport and the session state machine work.
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
from vaani.protocol import ErrorCode, SessionStart, error, session_started
from vaani.session import Session

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


async def _log_frames(session: Session, interval_s: float) -> None:
    """Background task: every `interval_s`, log how many valid frames arrived.

    It reads and resets the session's interval counter. Because everything runs
    on one event loop (no real threads), the read-and-reset cannot interleave
    with the read loop's increment, so no lock is needed. Cancellation (on
    disconnect) surfaces as CancelledError out of `sleep`, which ends the task.
    """
    while True:
        await asyncio.sleep(interval_s)
        count = session.take_interval_count()
        log.info(
            "session %s: %d frames in last %.3fs", session.session_id, count, interval_s
        )


@router.websocket("/ws/session")
async def session_endpoint(websocket: WebSocket) -> None:
    """Handle one WebSocket connection for its entire lifetime."""
    settings: Settings = websocket.app.state.settings
    audio_cfg = settings.audio
    expected = expected_frame_bytes(audio_cfg)
    interval_s = settings.gateway.frame_log_interval_s

    await websocket.accept()

    session: Session | None = None
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
                    await websocket.send_json(session_started(session.session_id))
                    continue
                if not _audio_matches(start.audio, audio_cfg):
                    await websocket.send_json(
                        error(
                            ErrorCode.UNSUPPORTED_FORMAT, "audio settings not supported"
                        )
                    )
                    continue
                session = Session(session_id=uuid.uuid4().hex, persona=start.persona)
                log_task = asyncio.create_task(_log_frames(session, interval_s))
                await websocket.send_json(session_started(session.session_id))
                continue

            # Every other control message requires a live session first.
            if session is None:
                await websocket.send_json(
                    error(ErrorCode.SESSION_NOT_STARTED, "send session.start first")
                )
                continue

            if mtype == "session.end":
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
        if session is not None:
            log.info(
                "session %s closed: %d frames total",
                session.session_id,
                session.frame_count,
            )
