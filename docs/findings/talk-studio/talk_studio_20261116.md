# /talk "Studio" redesign: bundle, tape frame time, checks, latency handover (2026-11-16)

Branch: feat/landing-on-air (uncommitted). Machine: the developer's Mac, macOS 15
(Darwin 24.3.0). Build: `npm run build` (Vite 8.3.0). Browser: Playwright's headless
Chromium at DPR 1. No backend was running for any of this.

## 1. Latency: NOT MEASURED

Mic-stop to first audible sample was **not measured**, before or after. Running the
backend is outside this work; see section 5 for how to measure it.

## 2. Bundle size

/talk is not a lazy route: its code and CSS are in the app bundle (`index-*`), which
the enrol and loopback pages also download. "Before" is this branch just before the
Studio work (the On Air landing work already in place); "after" is the final build.

| File | Before | After |
|---|---|---|
| App JS `index-*.js` | 428.54 kB (gzip 129.75 kB) | 442.25 kB (gzip 135.64 kB) |
| App CSS `index-*.css` | 60.46 kB (gzip 12.43 kB) | 56.11 kB (gzip 11.64 kB) |
| Landing JS `LandingPage-*.js` | 31.45 kB (gzip 10.87 kB) | 30.90 kB (gzip 10.64 kB) |
| Landing CSS `LandingPage-*.css` | 21.68 kB (gzip 5.03 kB) | 21.68 kB (gzip 5.03 kB) |

The app CSS shrank because `ConversationPage.css`, `VoiceOrb.css` and
`TranscriptView.css` are no longer imported. The landing JS shrank because
`canvasSize.js` and `useReducedMotion.js` are now shared with /talk and moved into
the app bundle. Fonts: each woff2 file is still emitted once (the same hashed file
is referenced by both CSS files).

## 3. Tape frame time (levels at zero)

A fake server (Playwright `routeWebSocket`) answered `session.started`, so the tape
loop ran live; the fake mic was silent and no audio played, so both levels were 0.
Every `requestAnimationFrame` callback was timed for 5 s, on the production build.

| Viewport | Canvas (px) | Frames | Callback p50 / p95 / max | Frame gap p50 / p95 / max |
|---|---|---|---|---|
| 390 x 844 | 356 x 150 | 600 | 0.2 / 0.3 / 0.4 ms | 8.3 / 8.9 / 9.4 ms |
| 1440 x 900 | 806 x 232 | 601 | 0.2 / 0.4 / 0.5 ms | 8.3 / 9.0 / 9.3 ms |
| 1920 x 1080 | 1286 x 232 | 601 | 0.2 / 0.4 / 0.5 ms | 8.3 / 8.8 / 9.4 ms |

Not measured: DPR 2, a slowed CPU, a real phone, and the cost with loud levels.

## 4. Other checks (same session)

- States without a backend: READY (standby), TUNING (socket held open, never
  answered), OFF AIR (nothing on :8000; banner "Connection Dropped").
- A scripted fake server drove the real hooks through listening, thinking, speaking
  (4 s of 22,050 Hz PCM), a barge-in and the next turn: every view and the Script
  matched the design; Vaani's bars came from the real playback and stopped at the cut.
- No horizontal scroll at 360, 390, 768, 1440 and 1920 px; every visible button and
  link at least 44 x 44 px.
- Contrast (WCAG formula, palette values): text 15.34:1, muted 5.75:1, red text
  5.27:1 on paper; muted 6.89:1 and red 5.21:1 on ink; ink on the red buttons 5.21:1.
- Reduced motion: no CSS animation; the tape redraws twice a second.
- `?preview=` is absent from the production build (no sample text in `dist/`, and
  `/talk?preview=cut` shows READY).

## 5. Handover: measuring the latency before and after (for Aryan)

**What changed on the audio side.** Two read-only additions, nothing else:
- `useAudioCapture.js`: one line in the worklet's `onmessage`, after the
  push-to-talk check and before the send, `lastFrameRef.current = frameBuffer`
  (a reference, no copy), plus `readMicLevel()`, which computes the RMS of that
  frame and sets the ref back to null.
- `usePlaybackQueue.js`: `readPlaybackLevel()`, which reads `currentTime`, finds the
  source playing now and computes the RMS of about 20 ms of its samples.

**Why they should cost nothing.** On the audio path the only new work is one pointer
assignment per 20 ms frame. Both read functions are called only by the tape's
animation loop, never by `enqueue`, `flushPlayback` or the send logic, and the
audio graph is untouched. The loop's whole callback measured 0.2 ms (p50) above.
This is reasoning plus a frame-time number, not a latency measurement.

**Steps** (same machine, same backend process and settings, back to back):
1. Start the backend as usual (note the ASR device/model and LLM provider).
2. "Before" page: `git worktree add ../vaani-before dev`, then in
   `../vaani-before/frontend`: `npm ci` and `npm run dev -- --port 5174`.
3. "After" page: on feat/landing-on-air, in `frontend/`: `npm run dev -- --port 5173`.
4. In `frontend/scripts/measure_talk_latency.js` set `FIXTURE` to the absolute path
   of `docs/findings/persona-voices/persona_default_en_US-kristin-medium_ls1.0_20261008-150404.wav`.
5. Set `URL` to `http://localhost:5174/talk`, run the file with a Playwright
   run-code tool (e.g. Claude Code's Playwright MCP `browser_run_code` with
   `filename`), and save the result. Then set `URL` to port 5173 and run again.
6. Each run is 10 hands-free turns, about 10 paid LLM calls. Report n, P50 and P95
   (nearest rank) of `audibleMs` for both, and add them to this file.
