"""The voice studio's FastAPI app: one process, its own port, same origin.

Routes (docs/contracts.md section 4):
  GET    /studio/health     liveness and GPU memory; no sign-in, no user data
  GET    /studio/voice      is my voice enrolled? the consent text and limits
  DELETE /studio/voice      delete my voice and everything made from it (ETH-4)
  POST   /studio/challenge  enrol.py
  POST   /studio/enrol      enrol.py
  POST   /studio/generate   generate.py

create_app builds the parts the routes share (access.Studio). Tests pass
fakes for the three models; the real ones are built here otherwise:
  * the challenge recogniser: the backend's own WhisperRecognizer, given the
    studio's [whisper] settings (small, CPU) instead of the voice agent's;
  * the speaker encoder: Chatterbox's voice encoder on CPU, loaded now;
  * the cloner: Chatterbox Multilingual, built now but loaded on first use.
"""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.routing import APIRouter
from vaani.asr.base import Recognizer
from vaani.auth import check_settings
from vaani.config import AuthSettings, get_settings

from voice_studio.access import (
    Reader,
    Studio,
    StudioError,
    Writer,
    studio_error_response,
    studio_of,
)
from voice_studio.config import StudioSettings, get_studio_settings
from voice_studio.enrol import CHECK_RATE
from voice_studio.enrol import router as enrol_router
from voice_studio.generate import DAY_S
from voice_studio.generate import router as generate_router
from voice_studio.store import Store

router = APIRouter(prefix="/studio")


class StudioConfigError(Exception):
    """The studio cannot start as configured; the message says what to set."""


def _configure_logging() -> None:
    """INFO logs from the studio and from the vaani code it runs (Whisper)."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(name)s: %(message)s"))
    for name in ("voice_studio", "vaani"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            logger.addHandler(handler)
        # A library in the model stack installs a handler on the root logger;
        # without this every line would be printed twice.
        logger.propagate = False
    # Chatterbox logs an emoji at INFO on every sentence ("EOS token
    # detected"). On a Windows console that is a UnicodeEncodeError, and the
    # console must stay ASCII anyway (CLAUDE.md). Its warnings still show.
    logging.getLogger("chatterbox").setLevel(logging.WARNING)


def create_app(
    cfg: StudioSettings | None = None,
    auth: AuthSettings | None = None,
    cloner: object | None = None,
    encoder: object | None = None,
    recognizer: Recognizer | None = None,
) -> FastAPI:
    _configure_logging()
    cfg = cfg or get_studio_settings()
    backend = get_settings() if auth is None or recognizer is None else None
    auth = auth or backend.auth
    if not auth.enabled:
        # Voices are stored per signed-in user (ETH-1): without sign-in there
        # is no user to enrol, so refuse to start rather than guess one.
        raise StudioConfigError(
            "[auth] enabled is false; the voice studio needs sign-in. "
            "Unset VAANI_AUTH__ENABLED or set it to true."
        )
    check_settings(auth)  # vaani/auth.py: names a missing variable, never a value

    if recognizer is None:
        from vaani.asr.whisper import WhisperRecognizer

        asr = backend.asr.model_copy(
            update={
                "language": cfg.challenge_language,
                "initial_prompt": "",
                "max_concurrent": 1,
                "whisper": cfg.whisper,
            }
        )
        recognizer = WhisperRecognizer(asr, sample_rate=CHECK_RATE)
    if encoder is None or cloner is None:
        # Imported only here: this is what pulls in torch and chatterbox.
        from voice_studio.model import Cloner, SpeakerEncoder

        encoder = encoder or SpeakerEncoder(cfg)
        cloner = cloner or Cloner(cfg)

    app = FastAPI(title="vaani-studio")
    app.state.studio = Studio(
        cfg=cfg,
        auth=auth,
        store=Store(cfg.data_path()),
        cloner=cloner,
        encoder=encoder,
        recognizer=recognizer,
    )
    app.add_exception_handler(StudioError, studio_error_response)
    app.include_router(router)
    app.include_router(enrol_router)
    app.include_router(generate_router)
    return app


@router.get("/health")
async def health(request: Request) -> dict:
    return {"status": "ok", **studio_of(request).cloner.stats()}


@router.get("/voice")
async def voice(request: Request, user: Reader) -> dict:
    studio = studio_of(request)
    cfg = studio.cfg
    consent = studio.store.consent(user.uid)
    used = studio.store.generations_since(user.uid, time.time() - DAY_S)
    return {
        "enrolled": consent is not None,
        "enrolled_at": consent["consented_at"] if consent else None,
        "consent_text": cfg.consent_text,
        "limits": {
            "sample_min_s": cfg.sample_min_s,
            "sample_max_s": cfg.sample_max_s,
            "challenge_max_s": cfg.challenge_max_s,
            "max_script_chars": cfg.max_script_chars,
            "generations_left_today": max(0, cfg.max_generations_per_day - used),
        },
    }


@router.delete("/voice")
async def delete_voice(request: Request, user: Writer) -> dict:
    studio = studio_of(request)
    if studio.busy:
        # A running generation would write its file AFTER the delete and
        # leave derived audio behind (store.save_generation makes the folder).
        raise StudioError(
            409, "STUDIO_BUSY", "A generation is running. Delete again in a moment."
        )
    studio.challenges.pop(user.uid, None)
    existed = studio.store.delete(user.uid)
    logging.getLogger("voice_studio").info("voice deleted for %s", user.uid)
    return {"deleted": existed}
