# 01 — Backend repository skeleton

## 1. In one minute

This turns an almost-empty repo into a running backend. It adds a Python
project under `backend/` managed by the **uv** package manager, a FastAPI app
whose one route `GET /health` returns `{"status":"ok","version":"0.1.0"}`, a
typed settings system (non-secret values from `config.toml`, secrets from
environment variables), tests, a linter, and CI on every pull request. It is
the foundation every later module builds on.

## 2. Files

| Path | What it is for |
|---|---|
| `.gitignore` | Untracked files: `.env`, virtual envs, caches, OS clutter |
| `README.md` | How to run the backend and tests from a clean clone |
| `frontend/README.md` | Placeholder; the React app is owned by Samyak |
| `.github/workflows/ci.yml` | CI: ruff + pytest on every PR into `dev`/`main` |
| `docs/versions.md` | Exact pinned version of every dependency |
| `backend/pyproject.toml` | Declares the package, dependencies, tool config |
| `backend/uv.lock` | Exact, reproducible dependency versions (committed) |
| `backend/.python-version` | Pins Python 3.11 for uv |
| `backend/config.toml` | Non-secret settings (app name, audio rate/frame) |
| `backend/.env.example` | Names of secret env vars, no values |
| `backend/vaani/__init__.py` | Package marker; holds `__version__` |
| `backend/vaani/config.py` | The typed `Settings` object and `get_settings()` |
| `backend/vaani/app.py` | `create_app()` factory and the `/health` route |
| `backend/vaani/protocol.py` | Docstring-only home for future WS messages |
| `backend/tests/test_health.py` | `/health` tests, incl. no-secret-leak |
| `backend/tests/test_config.py` | Settings-loading and secret-handling tests |

## 3. How it works

The main path is one `GET /health` request, from server start to response.

**Server start.** `uvicorn vaani.app:app` imports the object `app` from
`vaani/app.py`. The last line runs the factory once:

```python
# backend/vaani/app.py
app = create_app()
```

**Building the app.** `create_app()` reads settings once (only to title the
app) and registers the route:

```python
# backend/vaani/app.py
settings = get_settings()
app = FastAPI(title=settings.app_name, version=__version__)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
```

`@app.get("/health")` registers the function below it as the handler for that
path. The handler reads **no** settings — it returns a constant status and the
version — so it cannot leak configuration even if `Settings` later grows secret
fields. FastAPI turns the returned dict into a `200` JSON response.

**Loading settings** (behind `get_settings()`). `Settings()` declares its
sources in priority order — earlier wins:

```python
# backend/vaani/config.py
return (
    init_settings,
    env_settings,
    TomlConfigSettingsSource(settings_cls),
    file_secret_settings,
)
```

So a constructor value beats an environment variable, which beats
`config.toml`, which beats the field default. This is why a secret in the
environment always overrides the file, and why non-secret defaults live in the
committed file:

```python
# backend/vaani/config.py
app_name: str = "vaani"
audio: AudioSettings = AudioSettings()

secret_key: SecretStr | None = None
```

`secret_key` is never offered to the TOML source, so a secret can only arrive
from the environment. `SecretStr` also keeps its value out of logs and
`repr()`.

## 4. New concepts

- **uv** — a fast Python package manager. `uv sync` resolves the dependency
  tree in `pyproject.toml` and installs it into a local virtual environment.
- **Lockfile (`uv.lock`)** — records the *exact* version and checksum of every
  dependency resolution chose. Committed on purpose: from a clean clone it
  guarantees your machine and CI install identical versions, so "works on my
  machine" stops happening. CI enforces it with `uv sync --frozen`.
- **Application factory** — `create_app()` builds and returns a fresh app on
  each call instead of a module-level global. Tests build their own isolated
  app with their own settings, rather than sharing one baked in at import time.
- **Typed settings (pydantic-settings)** — gathers config from several sources
  (constructor, env, TOML file), validates it against type hints, and hands
  back one object. Replaces scattered, unvalidated `os.environ` reads.
- **ASGI server (uvicorn)** — the program that listens on the port, speaks
  HTTP/WebSocket, and calls our FastAPI app. The framework says *what* to
  answer; the server handles *the connection*.
- **Sample rate / frame duration** — audio measurements per second (16000 Hz)
  and the length of one processed audio chunk (20 ms). Stored as config now so
  no future module hardcodes them.

## 5. Why this and not that

| Choice | Picked | Alternatives | Why not them |
|---|---|---|---|
| Package manager | uv | pip+venv; Poetry; conda | pip needs bolt-ons for a real lockfile; Poetry is heavier/slower; conda is for binary deps we don't have |
| Web framework | FastAPI | Flask; Django | Flask is synchronous (bad for real-time audio/WebSockets); Django is a heavyweight we'd use 5% of |
| Config file format | TOML | YAML; JSON | YAML needs a 3rd-party parser (breaks the 6-dep limit); JSON has no comments. TOML is read by stdlib `tomllib`, zero deps |
| App construction | Factory | Module-level global app | A global is built once at import and shared by all tests; a factory gives each test a fresh, configurable app |
| Settings source | env for secrets, `config.toml` for the rest | secrets in a committed file | git keeps history forever — a committed secret is leaked forever |

## 6. When things go wrong

| What fails | What the code does |
|---|---|
| Unknown path requested | FastAPI returns 404 (its routing, not our code) |
| `config.toml` missing | TOML source contributes nothing; field defaults apply (16000/20); app still starts |
| `config.toml` malformed | `tomllib` raises during `Settings()`; app fails fast at startup with the error in the log |
| Wrong type in config | pydantic raises `ValidationError` at startup, naming the bad field |
| Secret not set | Field defaults to `None`; nothing needs it yet, so the app is healthy |
| `uv.lock` out of date in CI | `uv sync --frozen` fails the job (a dependency change forgot to relock) |

## 7. Questions you could be asked

1. **Where is the code that answers `/health`?** The `health()` function inside
   `create_app()` in `backend/vaani/app.py`.
2. **Where do secrets come from?** Environment variables only. The field is
   `secret_key` in `backend/vaani/config.py`; the source order that lets env win
   is the tuple returned by `settings_customise_sources` in the same file.
3. **What happens if `config.toml` is missing?** The TOML source contributes
   nothing, the field defaults (16000/20) apply, and the app still starts.
4. **What happens if `config.toml` has a syntax error?** `tomllib` raises during
   `Settings()` construction — the app fails to start loudly. That is deliberate
   fail-fast behaviour, not a bug.
5. **Can `/health` ever leak a secret?** No. The handler reads no settings at
   all — just a constant status and `__version__`. `test_health.py` sets a
   secret in the environment and asserts it never appears in the response.
6. **Why not YAML?** YAML needs a third-party parser (PyYAML), which would break
   the "only six dependencies" rule. TOML is read by stdlib `tomllib` — zero
   extra deps.
7. **Why an application factory instead of a global app?** A global is built
   once at import and shared by every test; a factory gives each test a fresh,
   independently-configured app. We keep one global `app` only so uvicorn has an
   import target.
8. **What does `uv sync --frozen` do in CI, and why?** It installs the exact
   versions in `uv.lock` and *fails* if the lockfile doesn't match
   `pyproject.toml` — catching a dependency change that forgot to relock.
9. **Trace loading `sample_rate`.** `Settings()` checks sources in order: if
   `VAANI_AUDIO__SAMPLE_RATE` is set it wins; else `[audio] sample_rate` from
   `config.toml`; else the field default `16000`.
10. **(Hardest) If `/health` reads no settings, how do you actually know it
    can't leak config — couldn't a later edit break that?** Two defences: the
    handler returns a literal dict with no `Settings` reference, and
    `test_health_does_not_leak_a_secret` fails CI if a secret ever appears in
    the response body. The guarantee is enforced by a test, not just by reading
    the current code.

## 8. Check yourself

Answer out loud, document closed:

1. Trace a `GET /health` request from `uvicorn vaani.app:app` to the JSON body.
2. Why TOML instead of YAML, and what would break if we switched?
3. What does the lockfile guarantee, and how does CI enforce it?
