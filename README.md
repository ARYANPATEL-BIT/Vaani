# Vaani

A real-time, interruptible voice agent, with a studio that turns written
context into a lip-synced video in the operator's cloned voice.

This repository has two halves:

- `backend/` — the Python (FastAPI) gateway. Owned by Aryan.
- `frontend/` — the React app. Owned by Samyak.

The full specification lives in `docs/`. Learning documents that explain each
piece of the project, from scratch, live in `docs/learning/`.

## Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — the package manager used for the
  backend. Install it once:
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows (PowerShell): `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **Node.js 20.19+, 22.13+ or 24+** and **npm** — runtime and package manager
  for the frontend. These are the Node versions that vite 8.3.0 and eslint
  10.11.0, pinned in `frontend/package-lock.json`, require.

## Running the backend

All backend commands run from the `backend/` directory.

```bash
cd backend

# Create the virtual environment and install the exact locked dependencies.
uv sync
# On a machine with an NVIDIA GPU, for asr.whisper.device = "cuda", use this
# instead, and ALWAYS pass --extra gpu (a plain `uv sync` removes the GPU libs):
#   uv sync --extra gpu

# Download the Piper voices named in config.toml (four voices, about 63 MB
# each) and check their sha256. Required before the first start: the server
# refuses to start if a voice file is missing. A file already present with
# the right hash is skipped.
uv run python scripts/fetch_models.py

# API keys. Copy the template and set both keys in .env (gitignored, never
# committed):
#   VAANI_GROQ_API_KEY    Groq, the primary provider
#   VAANI_GEMINI_API_KEY  Gemini, the failover
# Both are required: config.toml lists provider_order = ["groq", "gemini"],
# and the server refuses to start if a listed provider has no key.
# VAANI_SECRET_KEY is read but nothing uses it; leave it blank.
cp .env.example .env

# Start the API server. The first start also downloads the Whisper model
# named in config.toml ([asr.whisper] model = "small") from Hugging Face.
uv run uvicorn vaani.app:app --reload
```

At startup, `create_app` in `backend/vaani/app.py` loads, in this order: the
Silero VAD model (committed, sha256 checked), Whisper, the language model
provider chain (fails if a provider in `provider_order` has no API key), and
every persona's Piper voices (fails if a file is missing or its sha256 is
wrong). Any failure stops the server; nothing falls back. To run with only one
provider, remove the other from `[llm] provider_order` in `config.toml`; the
startup error says the same.

The server listens on <http://127.0.0.1:8000> by default. Check it is alive:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.1.0"}
```

## Running the frontend

All frontend commands run from the `frontend/` directory.

```bash
cd frontend

# Install dependencies.
npm install

# Start the Vite development server with HMR.
npm run dev
```

The app opens at <http://localhost:5173> by default.

To run lint and production build:

```bash
npm run lint     # run ESLint
npm run build    # produce production bundle in dist/
```

## Running the tests and lint

From `backend/`:

```bash
uv run pytest          # run the test suite
uv run ruff check .    # lint
uv run ruff format .   # auto-format (use --check in CI to only verify)
```

## Configuration

- Non-secret settings live in `backend/config.toml` (safe to commit and read).
- Secrets come **only** from environment variables, named in
  `backend/.env.example`. They are never written to `config.toml` or committed.
- Everything is loaded into one typed `Settings` object in
  `backend/vaani/config.py`.

## Continuous integration

`.github/workflows/ci.yml` runs ruff (lint + format check) and pytest on every
pull request into `dev` and `main`, using the committed lockfile so CI matches
local development exactly.
