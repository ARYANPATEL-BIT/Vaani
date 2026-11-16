# 22. The conversation page, redesigned ("Studio")

Branch: `feat/landing-on-air` (on top of the On Air landing work, uncommitted).

## 1. What

The voice app at `/talk` is restyled from the "Studio" design (`docs/design/talk-studio/`): an
icon rail, a radio-dial persona picker, a giant status word (READY, TUNING, LISTENING, THINKING,
SPEAKING, CUT, OFF AIR), the words being said in big type, a live tape of both voices, a numbered
Script and a bottom dock. It is a visual change: the conversation logic is the same. All new code
is in `frontend/src/talk/`; two hooks gained one read-only function each.

## 2. Why

The old page (an orb and a chat list) did not show the thing Vaani is about: who is talking,
and the moment you cut in. The new page shows both voices on one tape and marks every cut.
**Latency was NOT MEASURED** before or after (no backend in this work); the handover with exact
steps is in `docs/findings/talk-studio/talk_studio_20261116.md`. Measured there instead: the tape
costs 0.2 ms per frame (p95 0.4 ms); the app bundle grew from 428.54 to 442.25 kB of JS.

## 3. How

**Where things live.** `talk/StudioPage.jsx` owns the hooks and puts the parts together:
`RailNav`, `StudioHeader` (+ `StudioSettings`), `StatusWord`, `LiveLine`, `TapeBox`, `ScriptColumn`,
`StudioDock`, `StudioErrorBanner`. Every word, colour and size is in `talkContent.js`. Pure logic
with Node tests: `studioState.js` (which view to show) and `levelHistory.js` (the tape's memory).
`router.jsx` now serves `/talk` outside the sidebar layout; enrol and loopback keep the sidebar.

**Reading hooks without changing them.** A *hook* is a function a component calls to get state
and actions (`useAudioCapture` gives `wsStatus`, `startCapture`, ...). The page keeps the old page's
four handlers with the same statements in the same order. Its one addition, `onServerMessage`,
calls the old `handleServerMessage` first and then only *looks* at the message: the session start
time, a barge-in (`turn.state cancelling` or `audio.flush`) for CUT, and telemetry.

**Which view.** `studioState.js` `viewFor` maps `wsStatus` and `turnState` to a view. CUT is a
*latch*: set by a barge-in, held while the state is `cancelling` or `listening` (the server always
goes cancelling, then listening: `backend/vaani/turn_state.py`), cleared at the next `thinking`,
`speaking` or `idle`.

**Reading by ref, and why it keeps audio fast.** A *ref* is a box (`ref.current`) whose contents
React does not watch: changing it re-renders nothing. *State* is the opposite: every change
re-renders. The tape changes 60 times a second, on the same main thread that sends mic frames
and schedules playback, so it never touches state. `useStudioTape.js` runs one
`requestAnimationFrame` loop (the browser calls it before each repaint). Each frame it computes
the session time, and every 75 ms it calls `readMicLevel()` and `readPlaybackLevel()`, which return
a plain number. It draws, and writes the counter's text straight into its DOM node.
The loop stops when the session ends, the page unmounts or the tab is hidden.

**The two hook additions** (the full diffs are in the findings file). *RMS* (root mean square)
is a sound's average loudness: square each sample, average, take the root.
- `useAudioCapture.js`: one assignment keeps a reference to the frame about to be sent;
  `readMicLevel()` computes its RMS later, from the loop, and clears the reference.
- `usePlaybackQueue.js`: `readPlaybackLevel()` reads the audio clock, finds the buffer playing
  now and computes the RMS of 20 ms of it. It reads only; the audio graph is unchanged.

**The tape** (`drawStudioTape.js`, using the landing's `canvasSize.js`). A *canvas* is a
rectangle of pixels that code paints. A *ring buffer* (`levelHistory.js`) keeps the last 30 s of
samples in fixed arrays, overwriting the oldest. One second is always 66 px wide, so a narrow
phone shows fewer seconds rather than squashed bars. Each bar is drawn at the second it was
sampled: Vaani grey on track 01, you red on track 02. Red lines mark cuts; the playhead walks to
75% of the width and then the tape scrolls.

**Outlined words** (`LiveLine.jsx`). CSS `-webkit-text-stroke` draws only each letter's outline,
and a transparent fill leaves it hollow. Outlined means "not final": your interim transcript, and
Vaani's text that has arrived before any of its audio has played. From `speaking` on, Vaani's
line is solid: the audio carries no word timings, so the page cannot know which words were heard.

**The cut slice.** `clip-path: inset(...)` hides everything outside a rectangle. The cut reply
is drawn twice: one copy shows its top half, one its bottom half, nudged apart, with a red rule
between. It is kept to one line, right-to-left overflow, so a long reply loses its start, not
the end where it was cut.

**Phone layout** (`studioParts.css`). A *media query* applies CSS only at some widths. Under
768 px the rail and the Script column are hidden, three recent turns sit under a smaller tape,
and the settings and full Script open in `<dialog>`: a built-in modal that traps focus and closes
on Esc. The big type uses `cqw`: 1% of the stage's own width (a *container query unit*).

**Accessibility.** The status word is a polite *live region* (a screen reader announces changes).
The Script is a real `<ol>` in `role="log"`. Space (push-to-talk, hold to talk) and Esc (end) are
ignored while typing, and Esc yields to an open dialog. Every target is at least 44 px; contrast
is at least 5.2:1.

**If something fails.** No backend: OFF AIR plus the old error banner (same texts and buttons).
A level read throws: the loop stops and the tape freezes, but audio and the conversation go on,
because the loop is never called from the audio code. No canvas size yet: that frame is skipped.

**Dev preview.** `/talk?preview=listening|thinking|speaking|cut` shows sample data in `npm run dev`
(`studioPreview.js`). Vite turns `import.meta.env.DEV` into `false` in a build, so it is removed.

## 4. When

The page loads with the app bundle. The tape loop runs only during a live session with the tab
visible (twice a second under reduced motion). Levels are sampled every 75 ms; the counter
updates every frame; the words and the Script update when a server message arrives.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Canvas tape, one rAF loop, levels read by function | A DOM or SVG bar per sample | Hundreds of style updates a second on the thread that sends mic frames |
| `readMicLevel` / `readPlaybackLevel` (read-only) | An `AnalyserNode` in the playback graph | Changes the audio graph on the conversation path, which this work was not to touch (decided before building) |
| Outlined only before the first audio | Guessing played words from a speaking rate | Would show a precision the app does not have |
| CUT latch in `onServerMessage` | Setting it in a `useEffect` | An effect runs after the render, so CUT would show one render late, at the cost of an extra render |
| CSS media query + `<dialog>` sheets | A JS width hook rendering two trees | A re-render on resize and two copies of the logic |
| `-webkit-text-stroke` for outlines | SVG `<text>` with a stroke | SVG text does not wrap; long lines would need manual breaking |
| Two clipped copies for the slice | One copy with a strike-through | A strike-through crosses words; it does not look cut in two |

## 6. Known issues

- Latency (mic-stop to first audible sample) NOT MEASURED; see the findings file's handover.
- Never run against the real backend: states were driven by a scripted fake server and the
  preview; no Safari, Firefox, real phone or touch; DPR 1 only.
- Logout is not in the rail (it was a label with no action). There is no Mute.
- The old `ConversationPage`, `VoiceOrb`, `TranscriptView` and `PttButton` files, and the already
  unused `TopBar`, `StylePicker`, `StateStepper`, `WaveformHero`, `LatencyCard`, `ControlDock` and
  `Transcript` components, were deleted in this PR. `useAudioCapture.js` is 540 lines.
- "First sound · last turn" always shows "---": the backend sends no telemetry.
