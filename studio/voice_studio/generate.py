"""POST /studio/generate: a typed script, spoken in the user's enrolled voice.

The order of the checks matters. Everything that can refuse the request
cheaply runs BEFORE the model is touched:

  1. consent exists (ETH-3: no consent record, no synthesis);
  2. the script splits into sentences within the length caps (script.py);
  3. the user's daily cap is not used up (counted from provenance.jsonl);
  4. no other generation holds the model right now (one at a time).

Then the model runs on a worker thread, one sentence at a time. While it
runs, this coroutine checks every disconnect_poll_s whether the browser has
gone (tab closed, request aborted). If it has, it sets the `stop` event, the
cancellation token the worker reads between sentences, and the GPU is freed
after the current sentence instead of after the whole script.

The finished file is saved in the user's folder with a provenance note in
its WAV comment and a line in provenance.jsonl (ETH-5), then returned. Its
audio also carries Chatterbox's Perth watermark, added inside the model.
"""

import asyncio
import hashlib
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from time import perf_counter

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from voice_studio.access import StudioError, Writer, studio_of
from voice_studio.model_errors import GpuBusy, ModelError
from voice_studio.script import ScriptError, join, plan

log = logging.getLogger("voice_studio.generate")
router = APIRouter(prefix="/studio")

DAY_S = 24 * 3600


class GenerateBody(BaseModel):
    script: str


@router.post("/generate")
async def generate(body: GenerateBody, request: Request, user: Writer) -> FileResponse:
    studio = studio_of(request)
    cfg = studio.cfg

    if studio.store.consent(user.uid) is None:
        raise StudioError(
            403, "STUDIO_NOT_ENROLLED", "Enrol your voice first, with consent."
        )
    try:
        sentences = plan(body.script, cfg.max_script_chars, cfg.max_sentence_chars)
    except ScriptError as exc:
        raise StudioError(422, exc.code, exc.message) from exc
    # The cap is checked before the model is dispatched, as a spend cap is.
    used = studio.store.generations_since(user.uid, time.time() - DAY_S)
    if used >= cfg.max_generations_per_day:
        raise StudioError(
            429,
            "STUDIO_CAP_REACHED",
            f"You have made {used} generations in the last 24 hours, the limit. "
            "Try again later.",
        )
    if studio.busy:
        raise StudioError(
            409, "STUDIO_BUSY", "Another generation is running. Try again in a moment."
        )
    studio.busy = True  # no await since the check above: see access.Studio

    stop = threading.Event()
    started = perf_counter()
    try:
        work = asyncio.ensure_future(
            asyncio.to_thread(
                studio.cloner.synthesize,
                studio.store.reference_path(user.uid),
                sentences,
                stop,
            )
        )
        while not work.done():
            await asyncio.wait({work}, timeout=cfg.disconnect_poll_s)
            if not work.done() and await request.is_disconnected():
                stop.set()  # the worker stops before its next sentence
        waves = work.result()
    except GpuBusy as exc:
        raise StudioError(
            503,
            "STUDIO_GPU_BUSY",
            "The GPU is out of memory (the voice agent's speech recogniser may be "
            "using it). Stop the voice agent or wait, then try again.",
        ) from exc
    except ModelError as exc:
        raise StudioError(503, "STUDIO_MODEL_UNAVAILABLE", str(exc)) from exc
    except Exception as exc:
        log.exception("generation failed for %s", user.uid)
        raise StudioError(
            500, "STUDIO_FAILED", f"Generation failed ({type(exc).__name__})."
        ) from exc
    finally:
        # Our own task cancelled (server shutdown): tell the worker to stop.
        stop.set()
        studio.busy = False
    if waves is None:
        # The browser left; nobody will read a response or a file.
        log.info("generation for %s stopped: client disconnected", user.uid)
        raise StudioError(499, "STUDIO_CANCELLED", "The request was cancelled.")

    rate = studio.cloner.sample_rate
    audio = join(waves, rate, cfg.sentence_gap_ms)
    seconds = len(audio) / rate
    spent = perf_counter() - started
    generation_id = uuid.uuid4().hex[:12]
    created = datetime.now(UTC).isoformat(timespec="seconds")
    script_hash = hashlib.sha256(body.script.strip().encode()).hexdigest()
    note = (
        f"Synthetic speech: Vaani voice studio, {cfg.hf_repo} {cfg.t3_model}, "
        f"generation {generation_id}, {created}, script sha256 {script_hash}"
    )
    path = studio.store.save_generation(user.uid, generation_id, audio, rate, note)
    studio.store.log_generation(
        {
            "user": user.uid,
            "time": time.time(),
            "created": created,
            "generation": generation_id,
            "script_sha256": script_hash,
            "sentences": len(sentences),
            "languages": sorted({lang for _, lang in sentences}),
            "audio_s": round(seconds, 2),
            "generate_s": round(spent, 2),
        }
    )
    log.info(
        "generated %s for %s: %d sentences, %.1f s audio in %.1f s",
        generation_id,
        user.uid,
        len(sentences),
        seconds,
        spent,
    )
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"vaani-{generation_id}.wav",
        headers={"X-Generation-Id": generation_id},
    )
