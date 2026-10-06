"""FastAPI application for the Vaani backend.

Builds the app with an "application factory" — `create_app()` returns a fresh
FastAPI instance rather than creating one at import time. That keeps tests
isolated (each test can build its own app) and keeps construction explicit.

Exposes one route today: GET /health, a liveness check that reports status and
version and DELIBERATELY exposes no configuration or secrets.
"""

import logging

from fastapi import FastAPI

from vaani import __version__
from vaani.asr import Recognizer, build_recognizer
from vaani.config import Settings, get_settings
from vaani.gateway import router as gateway_router
from vaani.providers.base import LLMProvider
from vaani.providers.chain import build_chain
from vaani.spend import RequestCap
from vaani.tts import Synthesizer, build_synthesizer
from vaani.vad import load_model


def _configure_logging() -> None:
    """Make the project's own INFO logs visible.

    Uvicorn only configures its own loggers, and Python's root logger defaults
    to WARNING with no handler — so our INFO lines (like the per-second frame
    count) would be dropped. We attach one handler to the top-level "vaani"
    logger and set it to INFO. `propagate` stays True so pytest's caplog, which
    listens at the root logger, still captures these records in tests. The
    guard makes this safe to call once per created app without stacking
    duplicate handlers.
    """
    logger = logging.getLogger("vaani")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(name)s: %(message)s"))
        logger.addHandler(handler)


def create_app(
    settings: Settings | None = None,
    recognizer: Recognizer | None = None,
    llm: LLMProvider | None = None,
    synthesizer: Synthesizer | None = None,
) -> FastAPI:
    """Build and return a configured FastAPI application.

    Reads settings once (cached) to title the app, registers routes, and hands
    back the instance. No global app object is created at import time.

    `settings` is normally left as None and pulled from `get_settings()`. Tests
    pass an explicit Settings object to, for example, shrink the gateway's
    frame-log interval without touching the environment.

    `recognizer`, `llm` and `synthesizer` are for tests only: stand-ins used
    instead of the real ones named in settings.
    """
    settings = settings or get_settings()
    _configure_logging()
    app = FastAPI(title=settings.app_name, version=__version__)
    # Stash settings so the WebSocket endpoint can read them off the app.
    app.state.settings = settings
    # Load the VAD model now, at startup, never per session or per frame.
    # load_model is cached, so every app built in this process (tests build
    # many) shares the one loaded copy; the load time is logged once.
    if settings.vad.enabled:
        app.state.vad_model = load_model(
            settings.vad.model_path, settings.vad.model_sha256
        )
    # Same for speech recognition: load (and warm up) once at startup, so a
    # bad model name or a missing GPU fails here, not on a user's first turn.
    # build_recognizer is cached too. A misconfiguration raises: the server
    # refuses to start rather than run without transcripts.
    if recognizer is not None:
        app.state.recognizer = recognizer
    elif settings.asr.enabled:
        app.state.recognizer = build_recognizer(
            settings.asr, settings.audio.sample_rate
        )
    # The language model chain, built once and shared by every session: its
    # HTTP clients keep connections (and their TLS handshakes) open between
    # turns. One RequestCap for the process, so the spend limit is global.
    # A provider without its API key raises here: the server refuses to start.
    if llm is not None:
        app.state.llm = llm
    elif settings.llm.enabled:
        cap = RequestCap(settings.llm.max_requests_per_process)
        app.state.llm = build_chain(settings, cap)

    # The voice, loaded (and warmed up) once at startup and shared, like
    # Whisper. A missing or wrong voice file raises: the server refuses to
    # start rather than reply in silence.
    if synthesizer is not None:
        app.state.synthesizer = synthesizer
    elif settings.tts.enabled:
        app.state.synthesizer = build_synthesizer(settings.tts)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe.

        Returns only a fixed status string and the app version. It reads
        nothing from Settings and touches no secret, so this endpoint can never
        leak configuration even if Settings later grows sensitive fields.
        """
        return {"status": "ok", "version": __version__}

    # The /ws/session WebSocket endpoint (session lifecycle + audio ingest).
    app.include_router(gateway_router)

    return app


# Module-level app for servers that expect an import path, e.g.
# `uvicorn vaani.app:app`. It is just the factory's output.
app = create_app()
