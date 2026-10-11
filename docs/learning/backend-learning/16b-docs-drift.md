# 16b - Docs drift: documents and code drift apart, and how we catch it

Branch `docs/drift` (from `dev`, uncommitted). Also records PR #42, `fix/ws-url`. No
behaviour change and no protocol version change.

## 1. What

This branch changes documents and comments only. It fixes the places where a document
said something the code does not do: the root `README.md`, `frontend/README.md`,
`docs/versions.md`, the stack and vendor lines in `CLAUDE.md`, a stale note in
`docs/contracts.md` section 2.2, the known gaps and the stack table in
`docs/learning/PROJECT.md`, and comments in `backend/vaani/telemetry.py`,
`backend/vaani/app.py` and `frontend/src/router.jsx`. It also explains PR #42, which fixed
the same kind of problem in frontend code.

## 2. Why

"Drift" is when a document and the code it describes stop agreeing. A wrong document
costs more than a missing one, because you trust it. Nothing was measured here. Each case
below was found by reading the document next to the code:

- The README said "No secret is required to run today". In fact the server refuses to
  start without **either** API key. This was checked on 2026-10-11 by blanking each key in
  turn: startup raised `AuthenticationError` naming the missing variable. The README also
  never said that `scripts/fetch_models.py` must run first, and without the voices
  startup fails too.
- `versions.md` was last regenerated around day 10. Since then piper-tts and lucide-react
  were added, react moved to 19.3.0, and httpx became a runtime dependency.
- Comments counted things that had changed: "seven spans are actually emitted" (twelve
  span names now have a caller), "one route" in `app.py` (two), "only two routes" in
  `router.jsx` (five).
- `contracts.md` 2.2 still described a frontend sample-rate bug that PR #32 had fixed.
- `CLAUDE.md` listed PostgreSQL and the phase 2 vendors in the stack as if they were
  built. Today, the planned database is SQLite, and phase 2 is not decided.
- PR #42: `frontend/src/config.js` had a constant `WS_URL` that defaulted to `/ws/audio`,
  a path the backend never served, and nothing imported it. The socket really used
  `WS_SESSION_URL` (`/ws/session`). But `.env.example` and the frontend README told you
  to set `VITE_WS_URL`, which no code read. Setting it changed nothing, silently.

## 3. How

A document is a **copy** of a fact. When the original changes, nothing updates the copy.
So the first step is to know where each fact really lives, its **source of truth**:

- Library versions: the **lock files**, `backend/uv.lock` and
  `frontend/package-lock.json`. A lock file is written by the package manager and records
  the exact version of every package it installed, so every machine and CI install the
  same thing.
- What startup needs: `create_app` in `backend/vaani/app.py`. It loads the VAD model,
  then Whisper, then the provider chain (`providers/chain.py`, which refuses a listed
  provider without a key), then the voices (`tts/piper.py`, which refuses a missing file).
- Settings: `backend/config.toml`. Protocol versions: `docs/contracts.md`. Routes: the
  table in `frontend/src/router.jsx` and the routes in `backend/vaani/gateway.py`.

The fixes then follow five rules:

1. **Read the code, then write the document.** The README's setup steps now follow
   `create_app`'s order and say what fails if a step is skipped.
2. **Regenerate, do not edit.** `versions.md` was rebuilt from the two lock files, read as
   data, not from this laptop. Lines like "local runtime v25.8.1" were facts about one
   machine and were dropped.
3. **Search for claims that can go stale.** Every comment with a count ("seven",
   "only two", "one route") or a number with a unit was checked against the code or
   `config.toml`. Most were right (for example 700 ms of silence = 35 frames in
   `endpoint.py`). Only the three counts above were wrong.
4. **Point at the code instead of restating it.** A comment that lists the routes that the
   table 20 lines below already lists will drift again. So the counts were removed, not
   corrected. The telemetry comment now names the exception (`playback_start` has no
   caller), which only changes if the design changes.
5. **Run what can be run.** The "both keys are required" claim was run, not just read.

PR #42 used the same idea in code: it deleted the dead constant (nothing imported it, so
nothing changed) and made `.env.example` and the README name the variable the code
actually reads.

## 4. When

Drift gets in at any PR that changes a fact without changing its copies. The common
moments are adding a dependency (`uv add`, `npm install`), adding a config key, a route or
a startup check, and fixing a bug that a document still describes.

What catches it today:

- **CI's `uv sync --frozen`** fails a PR if `pyproject.toml` and `uv.lock` disagree. It
  checks those two files only, not `versions.md`.
- **Review against `STANDARD.md`**: PROJECT.md is updated in the same PR, and "if a
  document and the code disagree, the code is right".
- **`contracts.md` is the only place a protocol version is decided.**
- **`CLAUDE.md` now separates "today" from "planned"**, so a planned item cannot be read as
  built.
- **Count-free comments** leave less to go stale.

Nothing automated checks the READMEs, `versions.md` or comments. That is still a person,
at review.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Rebuild `versions.md` from the **lock files** | Read the local environment (`uv pip list`, `npm ls`, `node --version`) | The environment describes one machine, and one that has not run `uv sync` lately lists old versions. That is how "local Node v25.8.1" got in. The lock file is what every machine and CI install. |
| **Remove** counts from comments and point at the code | Correct the counts | A corrected count is right only until the next route or span, and nothing would flag it. What we lose: the reader has to look at the table to know how many there are. |
| README says what startup **checks** (both keys, voices, the Whisper download) | A short quick start that calls secrets "optional" | "Optional" is not what the code does: a newcomer hits `AuthenticationError` on the first run. The cost is a longer README. |
| Manual sweep at review | A CI test that compares a document with the code (for example `versions.md` with the lock files) | Not built: it needs a script per kind of document. It is a fair next step. Until then, only a person catches drift. |
| PR #42: **delete** the dead `WS_URL` | Keep it and fix its default to `/ws/session` | Two constants for one URL means the next reader has to work out which one is used. Nothing imported it. |
| `CLAUDE.md`: a **today** line and a **planned** line | One stack line | One line made PostgreSQL and the phase 2 vendors read as decided, and the planned database is SQLite. |

## 6. Known issues

- Nothing automated catches drift in the READMEs, `versions.md` or comments.
- Licences in `versions.md` come from installed package metadata and the lock's `license`
  field, not each project's licence file. piper-tts (GPL) and av's FFmpeg (LGPL) are not
  checked for our distribution case.
- The Whisper model revision is not pinned. `config.toml` names only `small`.
- The missing-voice startup failure was confirmed by reading `tts/piper.py`, not by
  running it. The two missing-key failures were run.
- The project-structure tree in `frontend/README.md` still lists only two pages. It was
  out of this branch's scope. Older learning documents (`01` to `15b`) are left as they
  are, as `STANDARD.md` asks.
