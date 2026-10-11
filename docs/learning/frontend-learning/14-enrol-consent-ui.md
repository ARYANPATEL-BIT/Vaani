# 14 — Enrolment Consent UI: Spoken Consent and Live Challenge Phrase

**Branch:** `feat/enrol-consent-ui`

## 1. What

This PR implements the enrolment consent and verification screen at `/enrol`. It adds a
stepped recording flow capturing an explicit spoken consent statement followed by a live
challenge phrase in strict order. A new `usePhraseRecorder` hook manages audio capture,
level meters, wall-clock timers, and in-browser previews for both short utterances.

## 2. Why

The build plan (Week 3 Day 4) and project specifications (US-006, SEC-6) require that voice
enrolment be gated by recorded consent and a retained live challenge to prevent replay
attacks and unconsented cloning. Automated speaker verification of the challenge is
scheduled for future scope, but the recorded controls are required now. No latency numbers
were measured for this UI workflow as it runs client-side prior to server session creation.

## 3. How

**Consent screen (`EnrolConsentPage.jsx`)** coordinates the multi-step verification
lifecycle. It presents a visual stepper tracking Spoken Consent, Live Challenge Phrase,
and Reference Audio. In step one, the user reads aloud a standardized operator consent
statement and records it. In step two, the challenge phrase is revealed and recorded. The
challenge phrase is strictly hidden until consent recording completes. Re-recording consent
resets and locks the challenge step to enforce strict sequence, while re-recording the
challenge preserves the consent recording. Once both recordings are completed, the user can
preview both audio tracks and proceed to `/enrol/record`.

**Phrase recording hook (`usePhraseRecorder.js`)** manages recording lifecycle for short
utterances with a 2-second minimum threshold and a 15-second auto-stop limit. It uses
`getUserMedia` and `MediaRecorder` for capture, `Date.now()` deltas for elapsed timing, and
an `AnalyserNode` RMS loop for live level metering. Captured audio is kept in browser memory
as a Blob with an object URL. Media tracks, AudioContext nodes, and timers are released on
stop, re-record, or unmount.

**Testing (`usePhraseRecorder.test.js`, `enrolConsent.test.js`)** validates state machine
transitions, duration boundaries, error recovery, step sequencing, and challenge phrase
visibility restrictions using pure Node.js test runners without hardware dependencies.

## 4. When

The consent UI activates when the user navigates to `/enrol`. Spoken consent recording runs
only when explicitly triggered by the user. The challenge phrase is revealed only when the
user transitions to step two. Level-meter rendering runs via `requestAnimationFrame` during
active recording. All audio streams and timers are torn down on session completion, retry,
or component unmount.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Separate `usePhraseRecorder` hook | Parameterising `useReferenceRecorder` | Short phrases require distinct duration boundaries (2s–15s vs 30s–60s) and independent concurrent state instances |
| Strict DOM conditional rendering | Hiding the challenge phrase with CSS | CSS hiding keeps the challenge phrase in the DOM where browser tools could inspect it prematurely |
| Stepped in-page recording cards | Dedicated URL routes for each utterance | In-page steps avoid multiple route hops and keep state cleanup centralized within one view |
| Client-side test challenge phrase | Mocking an unbuilt backend challenge API | The voice enrolment API is planned for Week 4; mocking a backend contract creates false architectural assumptions |

## 6. Known issues

- Automated tests do not exercise real browser microphone hardware or `MediaRecorder`
  APIs because Node.js test environments lack Web Audio APIs.
- Backend challenge issuance and consent storage endpoints (`POST /enrolments`) are not
  yet implemented and will be integrated in Week 4.
- Captured audio blobs remain in client memory only; closing the browser tab discards
  the recorded samples.
- The `<audio>` preview controls lack text transcript captions for accessibility.
