# 24 - Render deploy: the whole app in one container, on a free 512 MB host

Branch `feat/render-deploy` (from `dev`, uncommitted). Protocol v0.12 (`contracts.md`).

## 1. What

Vaani can now run with the laptop off, as one **Docker image** (a sealed bundle of an
operating system, Python, our code and its files) on Render's free plan. `Dockerfile` builds
it, `render.yaml` describes the Render service, and FastAPI now also serves the built browser
app, so page, sign-in and WebSocket share one address. Two settings make it fit: a server can
serve only some personas (`served_personas`; another persona gets the new error
`PERSONA_NOT_SERVED`), and Piper's thread count is now configurable.

## 2. Why

Render free gives a container 512 MB of RAM and **0.1 of a CPU** (a tenth of one core's time).
With all four voices the server peaked at 609 MB on the laptop; each Piper voice holds about
100 MB (`docs/findings/render-deploy/notes_20261125.txt`, part 1). Serving only `default`
loads two voices. Then the image ran under the same limits (`docker run --memory=512m
--cpus=0.1`), three times. **RSS** is the memory a process really holds in RAM; **RTF** (real-time
factor) is synthesis time divided by the length of the audio made, so 1.0 means a chunk takes
as long to make as to play.

| Gate run (`docs/findings/render-deploy/`) | Startup | Peak RSS | RTF per chunk | Mic stop to first audio |
|---|---|---|---|---|
| 1, ONNX Runtime default threads (`gate_20261125-195010.txt`) | 204.5 s | 324 MB | none: the first turn's transcription timed out | none |
| 2, Piper on 1 thread (`gate_20261125-195919.txt`) | 26.1 s | 453 MB | 0.96 to 1.10 | p50 2486 ms |
| 3, 1 thread + `MALLOC_ARENA_MAX=2`, shipped (`gate_20261125-200939.txt`) | 29.4 s | 382 MB | 0.78 to 1.12 | p50 2354 ms |

Memory fits. The CPU does not: on the laptop Piper's RTF is 0.03 to 0.05 (notes, part 2), and
no setting gets a tenth of a core near that. So Render free is a **fallback** for showing the
app with the laptop off: first audio about 2.4 s after you stop, likely gaps between chunks
(not listened to). The real-time demo, under 1,000 ms, stays on a machine with real CPU.

## 3. How

1. **Build, stage 1 (`Dockerfile`).** A **multi-stage build** uses one throwaway image to make
   files and copies only the result into the final one. A Node image runs `npm ci` and
   `npm run build` (Vite) to make `frontend/dist`. `VITE_GOOGLE_CLIENT_ID` comes in as a
   **build arg** (a value given to the build, not to the running app): Render passes each
   dashboard variable to the build under the same name, and the client ID is public.
2. **Build, stage 2.** A slim Python 3.11 image gets uv, installs exactly what `uv.lock` pins
   (no dev tools, no GPU extra, no download cache left in the image), fixes three settings as
   environment variables (Groq speech to text, `served_personas = ["default"]`, one Piper
   thread), runs `scripts/fetch_models.py default` (two voices from the pinned revision; a
   wrong sha256 fails the build), copies in `dist`, and switches to an ordinary user. Auth is
   not touched: `config.toml` has it on and nothing in the image turns it off.
3. **What the build may see (`.dockerignore`).** A whitelist: everything is ignored, then only
   `backend/` and `frontend/` come back, minus `.env` files, the database, every `.wav`, the
   voice weights and local installs. Something new at the repo root stays out by default.
4. **Start.** The command expands `$PORT` (Render's port) and uses `exec`, so uvicorn replaces
   the shell and receives the stop signal itself; the database writer then closes cleanly.
5. **Which voices load.** `config.py` `_served_are_personas` fills in `served_personas` (unset:
   every persona, so local is unchanged) and stops startup on a name that is not a persona.
   `app.py` hands Piper a copy of `[tts]` holding only those personas' voices.
6. **Threads.** ONNX Runtime (the engine that runs Piper's network) starts one thread per CPU
   core it can SEE, and a container sees all the host's cores (24 on the laptop) while being
   allowed 0.1 of one. Those threads queue for the same tiny share: run 1's two voices took
   70 and 119 s to warm up. `tts/piper.py` `_load` now builds the session itself with
   `[tts.piper] intra_op_threads` (0 = the old default; the image sets 1): 9 to 10 s.
7. **Memory pools.** glibc, the C library under Python on Linux, keeps separate memory pools
   ("arenas") for threads, which hold freed memory. `MALLOC_ARENA_MAX=2` (in `render.yaml`)
   caps them at two: peak 382 MB instead of 453 MB (runs 3 and 2).
8. **One origin.** A **single-page app** has one HTML page; the browser's router draws `/login`
   or `/talk` from it. `app.py` `_serve_frontend` adds one catch-all `GET` route after every
   API route, only when `frontend/dist` exists: a real file is sent as is, anything else gets
   `index.html`, and an unknown `/auth/...`, `/ws/...` or `/health/...` stays a 404. A path is
   resolved and must stay inside `dist`, so `..` cannot read other files.
9. **A persona that is not served.** `gateway.py` answers `session.start` with
   `PERSONA_NOT_SERVED`, naming what is served. No session starts and the socket stays open.
10. **Render (`render.yaml`).** One free Docker service. Auth is pinned on, any verified Google
    account allowed, cookie HTTPS-only. Secrets are `sync: false` (typed in the dashboard,
    never in the file); the session secret is `generateValue` (Render makes it once).
    **Health check**: Render calls `/health` and only routes traffic once it answers. A new
    deploy has 15 minutes; each check gets 5 s; `/health` answered in at most 148 ms during
    turns (run 3).
11. **Disk.** The container's disk is **ephemeral**: wiped whenever the instance stops. The
    database file is created again, empty, at every start (`db.py` `open_db`).

## 4. When

- **Build:** every deploy. Builds the page, installs the backend, downloads two voices.
- **Startup:** every deploy, restart, and **cold start**: Render free stops an idle service
  after about 15 minutes, and the next visitor waits while it starts (29.4 s measured locally,
  plus Render's own time, not measured).
- **Every `GET` that is not an API route:** the page or one of its files.
- **Each `session.start`:** the served-persona check. **Each chunk:** one RTF log line.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| One container for page and API | A static site plus an API service | Two origins: the `SameSite=Lax` cookie and the WebSocket Origin check would need cross-site rules, and there would be two deploys |
| `served_personas`, voices loaded at startup | Load a voice on its first use | The first reply in that voice would wait 9 to 10 s on 0.1 CPU, and all four could still end up loaded: 609 MB |
| Filter the voices in `app.py` | A `personas` argument on `build_synthesizers` | Changes its signature for two scripts and the Piper tests that never need it |
| New code `PERSONA_NOT_SERVED` (v0.12) | Reuse `BAD_MESSAGE` | The browser explains `BAD_MESSAGE` as "malformed request"; a client could not tell a typo from a deployment choice |
| Voices downloaded during the build | Downloaded at startup | Every cold start would pull 127 MB before answering, on 0.1 CPU |
| One catch-all route | FastAPI's `StaticFiles(html=True)` | It returns 404 for `/talk`: it has no fallback to `index.html` |
| One ONNX Runtime thread in the image | Its default, one per visible core | Run 1: 204.5 s to start and a transcription timeout |
| `MALLOC_ARENA_MAX=2` | glibc's default pools | 453 MB peak after two turns, 59 MB under the 512 MB limit |
| `generateValue` for the session secret | `sync: false`, typed by hand | A person would see, copy and paste a key that signs every cookie |

## 6. Known issues

- RTF 0.78 to 1.12 (run 3): replies probably come with gaps between chunks. Not listened to.
- All numbers are `docker --cpus=0.1` on the laptop, not Render; a real Render run is not measured.
- The database is wiped on every stop, and spend caps restart at 0 with every new process;
  Groq's free-tier limit on the shared key is the real ceiling.
- The browser still offers tutor and support (hardcoded list); on Render they get
  `PERSONA_NOT_SERVED` in the error banner. Memory grew 129 MB over two turns in run 2, not explained.
