# 20 - Voice check screen, hidden nav items, phone layout

Branch `feat/enrol-verify-ui` (stacked on `feat/enrol-api-wiring`), uncommitted. Frontend only.

## 1. What

Three changes. (a) The sidebar now shows only Conversation and History; Studio, Enrol,
Identity, Spend & Quota and Settings are hidden, but their pages still open by URL.
(b) A new screen, `/enrol/verify`, comes after validation accepts a recording: it plays a
test sentence in the cloned voice and asks "Yes, use this voice" or "No, record again".
(c) Below 640 px wide the sidebar becomes a bar along the bottom, and the pages fit a phone.

## 2. Why

- Week 4 Tuesday's task is "play the test sentence, approve or re-record".
- The validation page used to say "your voice profile is now active" the moment the
  recording passed validation, before anyone heard the clone. Nothing had been approved.
  Now it says the voice is not active until approved, and leads to the verify screen.
- At 360 px the 68 px rail took a fifth of the screen, and Conversation, Enrol consent
  and Validation scrolled sideways. Checked in Chromium at 360, 390, 768, 1024 and
  1280 px: after this change none of the 7 pages scrolls sideways (not a run file; a
  manual check this session).
- Nothing was measured for latency: this is not on the conversation path.

## 3. How

**Four ideas first.**
- A *state machine* is a fixed list of states plus a rule for each event: "in state X,
  event E leads to state Y". Any event without a rule is ignored. Its value here: there is
  exactly one road into "approved", so no bug elsewhere can show a voice as active early.
- An *AbortController* is a browser object with an `abort()` method and a `signal`. You hand
  the signal to `fetch`; calling `abort()` makes the browser drop that HTTP request.
- An HTML *audio element* (`<audio>`) plays a sound file from a URL and fires events such as
  "ended" when the sound finishes. An *object URL* is a temporary `blob:` address for bytes
  held in memory, so `<audio>` can play audio we downloaded ourselves.
- A *media query* (`@media (max-width: 640px) { ... }`) is a CSS block whose rules apply
  only while the condition is true, here "the window is at most 640 px wide".

**Hidden nav.** `components/Sidebar.jsx` gives each hidden item `hidden: true` and draws only
the others. The routes in `router.jsx` are untouched, so `/enrol`, `/enrol/record`,
`/enrol/validation`, `/enrol/verify` and `/loopback` still open when typed.

**Verify flow, step by step.**
1. `pages/EnrolRecordPage.jsx` now puts the server's enrolment id into router state when
   validation accepts; `pages/EnrolValidationPage.jsx` passes it on with "Continue to voice
   check".
2. `pages/EnrolVerifyPage.jsx` draws the screen. It holds no logic of its own.
3. `hooks/useVoiceVerify.js` asks the server to render the sentence
   (`renderVerificationSample` in `api/enrolApi.js`), turns the reply into an object URL,
   and later sends the approval (`approveVoice`). Each request has its own AbortController;
   leaving the page aborts them and frees the object URL.
4. `enrol/verifyState.js` is the state machine: loading, ready, playing, error, approving,
   approved. "Yes" unlocks only after the "ended" event of one full play. "approved" is
   reached only from "approving" on the server's `{ "status": "approved" }`.
5. "No, record again" goes to `/enrol/record`; that page mounts with a fresh recorder.
6. `/enrol/verify?demo=ok`, `load-error` or `approve-error` swaps the server for
   `enrol/verifyDemo.js`, which waits 0.8 s and plays a 1.5 s test tone. The page says
   "Demo mode" on screen.

The two endpoints do not exist yet; their assumed URLs and replies are written at the top
of the verification block in `api/enrolApi.js`, for Aryan to confirm.

**Phone layout.** `components/AppLayout.css` has one new media query. Under 640 px the page
column and the sidebar stack vertically, the sidebar is laid out as a row, the logo,
Operator and Logout rows are hidden, and each remaining button is at least 44 x 44 px (the
usual minimum for a fingertip). Heights use `100dvh`, the height actually visible on a
phone; plain `100vh` includes the strip behind the address bar. Each page's CSS gets a small
640 px block: less padding, the consent stepper listed top to bottom, the validation title
and status pill stacked. The conversation container clips the orb's wave ribbons, which
reached past the screen edge. Colours come only from theme tokens, so dark mode works as is.

## 4. When

The verify screen runs once per enrolment, after validation accepts. The render request is
sent when the screen mounts (and again on "Try loading the sample again"); the approval
request only on "Yes". The media queries are re-checked by the browser whenever the window
width changes, including a phone rotating.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| A pure reducer function (`verifyState.js`) driven by `useReducer` | Several `useState` flags (`isPlaying`, `hasPlayed`, `isApproving`...) | Flags can contradict each other (playing and approving at once), and the "never active before the server says so" rule would be spread over many lines instead of one; the reducer also runs in plain node tests |
| Download the sample as bytes, play it through an object URL | Server returns a JSON link and `<audio>` fetches it itself | The browser's own fetch for `<audio>` cannot be aborted with our controller or given a timeout, and its failure arrives as a vague media error, not an HTTP status we can explain |
| One `<aside>` restyled by a media query into a bottom bar | A second, phone-only nav component | Two components would duplicate the item list and the theme toggle, and could drift apart |
| `hidden: true` flag on nav items | Deleting the items | Bringing a screen back would mean rewriting its entry; the flag is one word |
| Our own Play/Stop button | The browser's built-in `<audio controls>` | Built-in controls let the user seek to the end, which would fire "ended" without hearing the sample |

## 6. Known issues

- The render and approve endpoints are guesses; nothing on the backend serves them yet.
- `api/enrolApi.js` is now 409 lines; `EnrolConsentPage.css` 549, `EnrolRecordPage.css`
  563, `EnrolRecordPage.jsx` 550, `EnrolValidationPage.css` 462, `EnrolValidationPage.jsx`
  374, `LoopbackPage.css` 389, `ConversationPage.css` 506: all over ~300, none split here.
- Tested: the state machine (24 checks in `enrol/verifyState.test.js`). Not unit-tested:
  the hook, the page and the API calls; they were only clicked through in Chromium in demo
  mode and with the backend down. No real phone or Safari was tried.
- If the user leaves during "approving", the request is aborted, but the server may
  already have saved the approval; the screen will not know.
