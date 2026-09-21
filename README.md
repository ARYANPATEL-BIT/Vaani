# Vaani

A real-time, interruptible voice agent, with a studio that turns written
context into a lip-synced video in the operator's cloned voice.

This repository has two halves:

- `backend/` — the Python (FastAPI) gateway. Owned by Aryan.
- `frontend/` — the React app. Owned by Samyak. (Placeholder for now.)

The full specification lives in `docs/`. Learning documents that explain each
piece of the backend, from scratch, live in `docs/learning/`.

## Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — the package manager used for the
  backend. Install it once:
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows (PowerShell): `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

## Running the backend

All backend commands run from the `backend/` directory.

```bash
cd backend

# Create the virtual environment and install the exact locked dependencies.
uv sync

# (Optional) provide secrets. Copy the template and fill in values as needed.
# .env is gitignored and never committed. No secret is required to run today.
cp .env.example .env

# Start the API server.
uv run uvicorn vaani.app:app --reload
```

The server listens on <http://127.0.0.1:8000> by default. Check it is alive:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.1.0"}
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
