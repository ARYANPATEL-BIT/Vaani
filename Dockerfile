# Dockerfile - Vaani phase 1 as ONE web service (feat/render-deploy).
#
# Two stages. The first builds the browser app with Node; the second is the
# image that runs: Python, the backend, two Piper voices, and the built app,
# which FastAPI serves from the same origin as /auth, /health and /ws/session.
# Only the second stage ships; Node and node_modules are left behind.
# Walkthrough: docs/learning/backend-learning/24-render-deploy.md

# --- Stage 1: build the browser app -----------------------------------------
FROM node:24-slim AS frontend
# Render passes the service's environment variables to the build as build
# args with the same names, read with ARG (it must come after FROM). A Google
# client ID is public - it is in every sign-in page - so a build arg is fine.
ARG VITE_GOOGLE_CLIENT_ID
WORKDIR /app/frontend
# The lockfile alone first, so the npm ci layer is reused while only the
# source changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Vite reads VITE_* from the environment; the ARG above is one during RUN.
RUN npm run build

# --- Stage 2: the backend that serves it ------------------------------------
FROM python:3.11-slim-bookworm
# uv, pinned to the version the project uses locally.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv
WORKDIR /app/backend
# Compile .py files once at build time, not on the first cold start. No
# download cache: it would stay in the image layer (about 540 MB measured),
# and every build of this image starts from scratch anyway.
ENV UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1
# Dependencies first, from the lockfile exactly (--frozen), without the dev
# tools or the gpu extra; this layer is reused until uv.lock changes.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev

# What this image IS, so it belongs here rather than in the host's settings:
# speech recognition on Groq (the image has no Whisper model, and a
# faster-whisper start would download one into a 512 MB box), and only the
# default persona, whose two voices are the only ones fetched below. Auth is
# NOT set here: config.toml has it on, and nothing in the image turns it off.
# One ONNX Runtime thread per synthesis: the container sees every host core,
# but Render free grants 0.1 of a CPU, and one thread per core would only
# fight over that share (gate run 1: 70 s and 119 s to warm up two voices).
ENV VAANI_ASR__ENGINE=groq \
    VAANI_SERVED_PERSONAS='["default"]' \
    VAANI_TTS__PIPER__INTRA_OP_THREADS=1
# The two voices, from the piper-voices revision pinned in config.toml, each
# checked against its sha256 there (the script deletes a mismatch and fails
# the build). silero_vad.onnx and every .onnx.json are in git, copied above.
RUN .venv/bin/python scripts/fetch_models.py default

# The built app at /app/frontend/dist, which is config.toml's
# [frontend] dist_dir ("../frontend/dist") seen from /app/backend.
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Run as an ordinary user, not root. It owns data/ only: the SQLite file is
# created there at startup, and is lost whenever the container stops.
RUN useradd --create-home vaani && mkdir -p data && chown vaani data
USER vaani

# sh -c so ${PORT} (set by Render; 8000 elsewhere) is expanded. exec makes
# uvicorn replace the shell, so the stop signal reaches uvicorn itself and the
# database writer closes cleanly instead of being killed.
CMD ["sh", "-c", "exec .venv/bin/uvicorn vaani.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
