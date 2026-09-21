"""FastAPI application for the Vaani backend.

Builds the app with an "application factory" — `create_app()` returns a fresh
FastAPI instance rather than creating one at import time. That keeps tests
isolated (each test can build its own app) and keeps construction explicit.

Exposes one route today: GET /health, a liveness check that reports status and
version and DELIBERATELY exposes no configuration or secrets.
"""

from fastapi import FastAPI

from vaani import __version__
from vaani.config import get_settings


def create_app() -> FastAPI:
    """Build and return a configured FastAPI application.

    Reads settings once (cached) to title the app, registers routes, and hands
    back the instance. No global app object is created at import time.
    """
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe.

        Returns only a fixed status string and the app version. It reads
        nothing from Settings and touches no secret, so this endpoint can never
        leak configuration even if Settings later grows sensitive fields.
        """
        return {"status": "ok", "version": __version__}

    return app


# Module-level app for servers that expect an import path, e.g.
# `uvicorn vaani.app:app`. It is just the factory's output.
app = create_app()
