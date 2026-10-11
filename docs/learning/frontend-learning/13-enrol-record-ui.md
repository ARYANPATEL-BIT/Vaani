# 13 — Enrolment Screens: Consent and Reference-Voice Recording

**Branch:** `feat/enrol-record-ui`

## 1. What

This PR adds two new frontend screens for Vaani's enrolment flow: a consent screen at
`/enrol` and a reference-voice recording screen at `/enrol/record`. Together they let
a user record a 30–60 second voice sample entirely in the browser before any backend
voice-cloning step exists. A new `useReferenceRecorder` hook drives all recording
logic, timer, and level-meter behaviour.

## 2. Why

The four-week build plan (Week 3 Day 3) requires a UI path where a user can record
a reference voice before the Friday barge-in session. Without this screen, there is
no way to capture the sample the backend will eventually use. No latency or accuracy
numbers exist for this feature yet (not measured at this stage).

## 3. How

**Consent screen (`EnrolConsentPage`)** explains why the recording is needed, lists
four guidance points (quiet room, natural speech, 30–60 s, browser-local only), and
requires a checkbox acknowledgement before enabling the Continue button. It has no
network calls. Clicking Continue navigates to `/enrol/record`; Cancel goes back to `/`.

**Recording screen (`EnrolRecordPage`)** uses `useReferenceRecorder` for all state.
It shows: an elapsed timer (`mm:ss` from real wall-clock `Date.now()` deltas ticked
every 500 ms), a progress bar with a 30-second minimum marker, a 20-bar level meter
fed by a real `AnalyserNode` RMS loop, an animated microphone visual, and a status
badge. Controls surface the correct action for each state: Start, Stop, or Record
Again. An `<audio>` element previews the captured blob after a valid recording.

**`useReferenceRecorder` hook** owns the state machine:
`idle → requesting → recording → completed | too_short | failed`.
It calls `getUserMedia` only when the user explicitly starts. `MediaRecorder` collects
chunks every 250 ms. A `setInterval` at 500 ms ticks the elapsed display. An
`AnalyserNode` (fftSize 256) drives a `requestAnimationFrame` loop that computes RMS
from `getFloatTimeDomainData` and scales it to a 0–1 level value. A `setTimeout` at
60 seconds calls `stopRecording` automatically. On stop, if `elapsed < 30` the state
becomes `too_short`; otherwise the blob is wrapped in an object URL and state becomes
`completed`. Every stop path releases the media stream, closes the AudioContext, and
cancels the RAF loop and interval.

**Router (`router.jsx`)** activates the two new routes (`/enrol`, `/enrol/record`).
**Sidebar (`Sidebar.jsx`)** adds an "Enrol" link (UserCheck icon) so both screens are
reachable from navigation.

**Tests (`useReferenceRecorder.test.js`)** exercise the pure state-machine logic and
helper functions (16 groups, 40 assertions) with no browser APIs. The test is wired
into `npm test` alongside the two existing suites.

## 4. When

The consent screen renders when the user navigates to `/enrol`. The recording hook
activates `getUserMedia` only when the user clicks Start Recording. The level-meter
RAF loop runs only while `state === 'recording'` and stops immediately on stop or
error. The 60-second auto-stop fires exactly once per session; it is cancelled if the
user stops manually first. All resources are released on component unmount via
`useEffect` cleanup.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| `MediaRecorder` API for capture | Web Audio `ScriptProcessor` + manual encoding | ScriptProcessor is deprecated; MediaRecorder is the current standard and handles encoding automatically |
| `AnalyserNode` RMS for level meter | CSS animation / fake decorative meter | The task explicitly requires measurements from real microphone audio, not a decorative animation |
| Wall-clock `Date.now()` for elapsed timer | Counting `setInterval` ticks | Interval ticks drift under CPU load; `Date.now()` always reflects real elapsed time |
| In-memory `Blob` + object URL for preview | Recording directly to a `<audio>` element via `MediaRecorder` | Storing as a blob gives a stable object URL for the preview `<audio>` and is ready for later upload |

## 6. Known issues

- Browser microphone checks are manual only; no automated test exercises `getUserMedia`
  or `MediaRecorder` because those APIs are not available in Node.js.
- The `<audio>` preview element has no captions (`jsx-a11y/media-has-caption`); the
  rule is not installed in the project's ESLint config so it does not flag, but the
  accessibility gap remains.
- `/enrol/record` can be navigated to directly (no hard redirect guard); a user who
  skips the consent screen will see the recording UI without having acknowledged the
  consent text.
- Audio preview playback rate may differ across browsers depending on the MIME type
  and codec chosen by `MediaRecorder.isTypeSupported` selection order.
- Resource cleanup relies on component unmount; if the browser tab is closed mid-
  recording, the microphone is released by the browser but the object URL is not
  explicitly revoked.
