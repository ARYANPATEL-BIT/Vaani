# Frontend viva guide

The guide follows the order in which you'll walk through the code:

1. **Level 1:** the `frontend/` folder. What every top-level file and folder is.
2. **Level 2:** inside `src/`. What each folder is for, and when it's used.
3. **Level 3:** file by file. What it does, plus the words in it that a teacher is most likely to point at, explained.
4. **Level 4:** the whole flow in one story, and likely questions.

Paths are relative to `frontend/`. Click a link to open the file.

---

# Level 1 - The `frontend/` folder

```
frontend/
|-- node_modules/        installed libraries (never edited, never committed)
|-- public/              files served as-is, untouched by the build
|   |-- audio-processor.js
|   |-- favicon.svg, icons.svg
|-- src/                 OUR code: all React components, hooks, logic, CSS
|-- scripts/             helper scripts run by hand (latency measurement)
|-- dist/                the production build output (generated, not committed)
|-- index.html           the one HTML page; React mounts into it
|-- package.json         project name, scripts, list of libraries
|-- package-lock.json    exact pinned versions of every library
|-- vite.config.js       config for Vite (the build tool)
|-- eslint.config.js     config for ESLint (the code checker)
|-- .env.example         template for environment settings
|-- .gitignore           files git must ignore
|-- loopback-tests.html  a browser page that runs the loopback math tests
|-- README.md            how to install and run
```

### `node_modules/`
- **What it is:** the folder where `npm install` downloads every library listed in `package.json`, plus the libraries those libraries need. About 112 top-level packages here.
- **Why so big:** our 4 libraries depend on others, which depend on others (the "dependency tree").
- **Never committed:** it's listed in `.gitignore`. Anyone can rebuild it exactly with `npm install`, using `package-lock.json`.
- **Never edited:** a change there is lost on the next install.
- **Words:** *npm* = Node Package Manager, the tool that installs JavaScript libraries. *Package* = one library. *Dependency* = a library our code needs.

### `package.json`  ([open](../../frontend/package.json))
The project's ID card.
- `"type": "module"`: files use modern `import`/`export` (ES modules), not old `require()`.
- **`scripts`**: shortcuts you run with `npm run <name>`:
  - `dev` -> `vite`: start the dev server at `http://localhost:5173` with hot reload.
  - `build` -> `vite build`: make the optimised production files in `dist/`.
  - `lint` -> `eslint .`: check the code for mistakes.
  - `test` -> runs 18 test files one after another with plain `node`. There's no test framework.
  - `preview` -> serve the built `dist/` locally.
- **`dependencies`** (shipped to the user's browser):
  - `react`: the UI library (components, state).
  - `react-dom`: draws React components into the real web page (the DOM).
  - `react-router-dom`: maps URLs (`/talk`, `/login`) to pages.
  - `lucide-react`: the icon set.
- **`devDependencies`** (only used while developing, never shipped):
  - `vite` + `@vitejs/plugin-react`: build tool + JSX support.
  - `eslint`, `@eslint/js`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `globals`: the code checker and its rules.
  - `@types/react`, `@types/react-dom`: type hints for the editor's autocomplete.
- **Words:** *`^19.2.8`* (caret) = "19.2.8 or any newer 19.x". The exact version actually installed is fixed in the lock file.

### `package-lock.json`
- Records the **exact** version of every package in `node_modules`, including indirect ones. Everyone gets the same install, so "works on my machine" doesn't happen. Committed, never hand-edited.

### `index.html`  ([open](../../frontend/index.html))
- The **only** HTML page. This is a **Single Page Application (SPA)**: the browser loads this page once, and React swaps what's shown as the URL changes, with no page reloads.
- `<div id="root">`: the empty box React fills.
- `<script type="module" src="/src/main.jsx">`: starts our code.
- The inline `<script>` at the top picks the theme **before** React loads, so there's no white flash in dark mode.
- `<link rel="preconnect">`: opens the connection to Google Fonts early, so the fonts arrive sooner.
- `<meta name="viewport">`: makes the page fit phone screens.

### `public/`
- Files copied to the site **as-is**, at the root URL. `public/audio-processor.js` is served at `/audio-processor.js`.
- **Why the audio processor lives here:** `audioWorklet.addModule('/audio-processor.js')` needs a plain URL to a plain file. Vite doesn't bundle anything in `public/`.
- `favicon.svg` = the browser tab icon.

### `src/`
All our code. Level 2 covers it.

### `dist/`
- Output of `npm run build`: minified, bundled JS and CSS ready to host. Generated, so it's gitignored.
- **Words:** *bundle* = many source files merged into a few files; *minify* = remove spaces and shorten names to make files smaller.
- **`dist/assets/`**: everything our `src/` code imports, after Vite processes it:
  - `index-xxxx.js` / `index-xxxx.css`: the main app bundle (all of `src/` minus the landing page).
  - `LandingPage-xxxx.js` / `.css`: the landing page's separate chunk (because `router.jsx` loads it with `lazy`).
  - `.webp` / `.png`: the landing images from `src/landing/assets/`. `.woff2`: the fonts from `src/landing/fonts/`.
  - **The random part of each name (`-BRy6OLg1`) is a content hash**, a fingerprint of the file's contents. When a file changes, its name changes too. Browsers can cache these files forever, and a new build forces them to download the new version (*cache busting*).
  - Files in `dist/` but **outside** `assets/` (`audio-processor.js`, `favicon.svg`, `index.html`) are copied as-is from `public/`, so they keep their names and have no hash.

### `vite.config.js`
- Six lines: it turns on the React plugin (JSX + fast refresh). Everything else uses Vite's defaults.
- **Vite** (French for "fast"): the dev server and build tool. **HMR (Hot Module Replacement)** = when you save a file, only that part of the page updates, without a full reload.

### `eslint.config.js`
- ESLint reads code without running it and flags mistakes. Rules here:
  - `js.configs.recommended`: common JavaScript bugs (unused variables, and so on).
  - `react-hooks`: hook rules. Hooks must always be called in the same order, and `useEffect`/`useCallback` dependency lists must be complete.
  - `react-refresh`: keeps files compatible with HMR.
  - `globals.browser`: tells it `window`, `document` and so on exist.
  - `globalIgnores(['dist'])`: don't check the build output.

### `.env.example`
- A template. Copy it to **`.env.local`** (gitignored) and fill it in:
  - `VITE_API_BASE_URL=http://localhost:8000`: the backend's HTTP address.
  - `VITE_WS_SESSION_URL=ws://localhost:8000/ws/session`: the WebSocket address.
  - `VITE_GOOGLE_CLIENT_ID=`: the Google sign-in app ID (public, not secret).
- **Why the `VITE_` prefix:** Vite only exposes variables that start with `VITE_` to browser code, as a safety measure so other variables (like secrets) can't leak into the page.

### `.gitignore`
- Keeps `node_modules`, `dist`, `*.local` (your `.env.local`), logs and editor files out of git.

### `scripts/measure_talk_latency.js`
- A **Playwright** script (Playwright = a tool that drives a real browser from code). It opens `/talk`, fakes the mic with a speech clip, and measures **mic-stop to first audible sample**, our latency target (under 1000 ms).

### `loopback-tests.html`
- A plain page that runs the loopback-analysis tests in a browser. Open it at `localhost:5173/loopback-tests.html`.

---

# Level 2 - Inside `src/`: the folders and when they're used

```
src/
|-- main.jsx, App.jsx, router.jsx, config.js, index.css   <- startup + global settings
|-- talk/        the /talk conversation page ("Studio")      <- THE MAIN PAGE
|-- hooks/       reusable logic: mic, playback, transcript, turn state, recorders
|-- turnState/   the protocol rules shared with the backend (message types, error codes)
|-- ptt/         push-to-talk press logic
|-- login/       Google sign-in page (/login) and the /talk guard
|-- pages/       enrolment pages + loopback page + 404
|-- enrol/       enrolment logic (validation messages, verify state machine)
|-- api/         HTTP calls for enrolment
|-- telemetry/   latency numbers from the server
|-- loopback/    speaker-to-mic delay measurement math
|-- theme/       light / dark mode
|-- components/  sidebar layout used by enrol + loopback pages
|-- landing/     the public home page "/"
```

| Folder | When it runs | One-line use case |
|---|---|---|
| root files | every page load | boot React, pick the page from the URL, hold settings |
| `talk/` | user opens `/talk` | the live voice conversation screen |
| `hooks/` | inside pages | the "engine": mic to socket, socket to speaker, transcript |
| `turnState/` | every server message | know which messages exist; drop stale audio after a cut |
| `ptt/` | push-to-talk mode | open and close one press correctly |
| `login/` | `/login`, and the guard on `/talk` | sign in with Google, keep signed-out users out |
| `pages/` + `enrol/` + `api/` | `/enrol/...` | record a voice sample, validate it, approve the clone |
| `telemetry/` | during a session | show how long each stage took |
| `loopback/` | `/loopback` | measure the speaker to mic delay |
| `theme/` | page load + toggle | light/dark |
| `components/` | enrol/loopback pages | sidebar layout |
| `landing/` | `/` | marketing page; scripted demo, no mic, no network |

**A pattern to point out:** files with **no React** (like `turnFilter.js`, `pttPress.js`, `studioState.js`, `loginState.js`) hold pure logic so plain `node` can test them. React files (`.jsx`, `use*.js`) do the drawing and wiring.
- **`.js` vs `.jsx`:** `.jsx` files contain JSX (HTML-like tags in JavaScript); `.js` files are plain JavaScript.
- **`use...` name** = a React hook.
- **`*.test.js`** = a test file.
- **`*.css`** = styles for that folder's components.

---

# Level 3 - File by file, with the words to know

Format: **what it does**, then the **words a teacher might point at**.

## 3.1 Startup files

### [src/main.jsx](../../frontend/src/main.jsx) - the entry point
Finds `<div id="root">` and draws `<App/>` into it.
- **`createRoot`**: React 18+ way to attach React to a DOM element.
- **`render`**: draw this component tree.
- **`<StrictMode>`**: dev-only checks. React deliberately runs some functions **twice** to expose bugs. It has no effect in production.
- **`import './index.css'`**: Vite lets you import CSS from JS; it gets injected into the page.

### [src/App.jsx](../../frontend/src/App.jsx) - the root component
- **Component**: a function that returns what to draw.
- **`RouterProvider`**: gives the whole app access to the router.
- **`export default`**: the main thing this file exports. Imported without `{}`.

### [src/router.jsx](../../frontend/src/router.jsx) - the URL table
`/` landing, `/talk` studio (guarded), `/login`, `/loopback`, `/enrol...`, `*` 404.
- **`createBrowserRouter`**: builds a router that uses real URLs (`/talk`, not `#/talk`).
- **route**: a `{ path, element }` pair, meaning "at this URL, show this".
- **`element`**: the JSX to show.
- **`lazy`**: load this page's code only when someone visits it (**code splitting**). The landing page is its own download, so `/talk` stays fast.
- **`hydrateFallbackElement`**: what shows while that lazy code downloads (a black box, to avoid a white flash).
- **`children`** + layout route: a route with no path that wraps its children in `AppLayout` (the sidebar).
- **`path: '*'`**: matches anything not listed: the 404 page.

### [src/config.js](../../frontend/src/config.js) - all settings
- **`import.meta.env.VITE_...`**: reads a value from `.env.local` at build time.
- **`||` fallback**: if the env value is empty, use `'http://localhost:8000'`.
- **`16_000`**: underscores are just readable digits (= 16000).
- **sample rate 16 kHz**: 16,000 numbers per second describe the sound; that's what speech models expect.
- **frame 20 ms = 320 samples**: audio is sent in small chunks.
- **`PTT_END_FALLBACK_MS = 300`**: maximum wait for the last audio chunk after you release push-to-talk.
- **`GIS_SCRIPT_URL`**: Google Identity Services script address.

### `src/index.css`, `src/theme/colors.css`
Global styles. **CSS variable** (`--tk-bg`): a named value used everywhere; change it once and everything changes.

## 3.2 `talk/` - the conversation page

### [talk/StudioPage.jsx](../../frontend/src/talk/StudioPage.jsx) - the /talk page (most important page)
It connects the five hooks and routes every server message.
- **`useState`**: a value that re-draws the page when it changes (`selectedPersona`).
- **`useCallback`**: keeps the **same function** between re-draws unless the items in its `[ ]` list change. That list is the **dependency array**.
- **`useRef`**: a box (`.current`) that keeps a value **without** re-drawing (`startRef`, `cutsRef`).
- **`useEffect`**: run code **after** drawing (here: reset when the socket disconnects).
- **destructuring** `const { enqueue, flushPlayback } = usePlaybackQueue()`: pull named items out of an object.
- **`handleServerMessage`**: the "router" for server messages. It sends each message type to the right hook.
- **`handleConnect` / `handleSpeak` / `handleDisconnect`**: the button actions.
- **`persona`**: the agent's character (default, tutor, support).
- **`mode` `vad` / `ptt`**: hands-free vs push-to-talk.
- **barge-in / cut**: you talk over the agent and its reply is cancelled.
- **latch** (`latchedRef`): once CUT is shown it "sticks" until the next reply. One barge-in sends two messages, and the latch counts them as one cut.
- **`performance.now()`**: a precise millisecond clock (for timings).
- **`import.meta.env.DEV`**: true only in development; the preview code is removed from production.
- **props** (`<StudioDock onConnect={handleConnect} />`): passing values or functions into a child component.
- **`<dialog>` / `showModal()`**: a native popup window (the phone's script sheet).
- **`aria-label`**: a name for screen readers.

### [talk/studioState.js](../../frontend/src/talk/studioState.js) - which screen state to show
- **pure function**: output depends only on input, and nothing else is changed, so it's easy to test.
- **`viewFor()`**: picks one of standby / tuning / offair / ready / listening / thinking / speaking / cut.
- **`timecode()`**: seconds to `MM:SS.cc`. **`padStart(2,'0')`**: `5` becomes `"05"`.
- **`tail()`**: the last N characters of a long line, starting at a whole word, with an ellipsis.

### [talk/talkContent.js](../../frontend/src/talk/talkContent.js) - all words, colours, timings
- **`PAPER` / `INK`**: the light and dark palettes ("Ink mode" = dark mode).
- **`VIEWS`**: text and lamp for each screen state.

### [talk/StatusWord.jsx](../../frontend/src/talk/StatusWord.jsx) - the big READY./LISTENING. word
- **`role="status"`**: a **live region**. A screen reader announces it when it changes, politely, after it finishes its current sentence.

### [talk/LiveLine.jsx](../../frontend/src/talk/LiveLine.jsx) - the big live words
Red = you, ink = Vaani. Outlined = not final, solid = final.
- **`memo`**: skip re-drawing when the props haven't changed (performance).
- **`aria-hidden`**: hide from screen readers (the same words are in the Script list).
- **partial transcript**: the live guess of what you're saying; **final** = the committed text.

### [talk/ScriptColumn.jsx](../../frontend/src/talk/ScriptColumn.jsx) - the numbered transcript
- **`<ol>`**: ordered (numbered) list.
- **`role="log"`**: a live region for chat-style logs; a new line gets announced.

### [talk/StudioDock.jsx](../../frontend/src/talk/StudioDock.jsx) - bottom buttons + keyboard
- **`keydown` / `keyup`**: events when a key goes down or comes up. Space = hold to talk.
- **auto-repeat** (`event.repeat`): a held key fires keydown again and again; we ignore the repeats.
- **`preventDefault()`**: stop the browser's normal action (Space would scroll the page).
- **`isTypingTarget`**: don't steal Space while the user types in a field.
- **`counterRef`**: the tape counter text is written directly into the DOM, not through React.

### [talk/StudioHeader.jsx](../../frontend/src/talk/StudioHeader.jsx), [StudioSettings.jsx](../../frontend/src/talk/StudioSettings.jsx)
- **`locked` / `disabled`**: settings can't change once a session starts.
- **reply language** `any | en | hi`: which language the agent answers in.

### [talk/StudioErrorBanner.jsx](../../frontend/src/talk/StudioErrorBanner.jsx)
- **`role="alert"`**: a live region that is read out **immediately**.

### [talk/RailNav.jsx](../../frontend/src/talk/RailNav.jsx)
The left icon bar. **lucide** = the icon library. Sign out uses `useSignOut`.

### [talk/TapeBox.jsx](../../frontend/src/talk/TapeBox.jsx), [useStudioTape.js](../../frontend/src/talk/useStudioTape.js), [drawStudioTape.js](../../frontend/src/talk/drawStudioTape.js), [levelHistory.js](../../frontend/src/talk/levelHistory.js) - the moving waveform
- **`<canvas>`**: a pixel area you draw on with JavaScript.
- **`requestAnimationFrame` (rAF)**: "call my function before the next screen paint", about 60 times a second. It pauses in hidden tabs.
- **why refs, not state, here:** 60 React re-draws a second would slow the thread that also sends the mic audio.
- **RMS**: root-mean-square, a measure of average loudness: `sqrt(average of x squared)`.
- **ring buffer** (levelHistory): a fixed-size array where the newest value overwrites the oldest, so memory never grows.
- **typed array** (`Float32Array`): a fast array of numbers of one type.
- **playhead**: the "now" line on the tape.

### [talk/studioPreview.js](../../frontend/src/talk/studioPreview.js)
Dev-only fake states: `/talk?preview=speaking`. **tree-shaking / dead-code removal**: in production `DEV` is false, so Vite deletes this code.

## 3.3 `hooks/` - the engine

### [hooks/useAudioCapture.js](../../frontend/src/hooks/useAudioCapture.js) - mic to server, server to page (most important file)
- **hook**: a function starting with `use` that holds state/effects for a component.
- **`getUserMedia`**: the browser API that asks for mic permission and gives a **MediaStream**.
- **`echoCancellation` / `noiseSuppression` / `autoGainControl`**: the browser cleans the mic sound (removes the speaker's echo, background noise, and evens out the volume).
- **`AudioContext`**: the browser's audio engine. It works as a **graph** of connected **nodes**.
- **`latencyHint: 'interactive'`**: ask for the smallest audio delay.
- **`audioWorklet.addModule`**: load our processor code onto the audio thread.
- **`AudioWorkletNode`**: the node in the graph that runs that processor.
- **`createMediaStreamSource`**: turns the mic stream into a graph node.
- **`createGain` / mute node, gain 0**: a volume knob set to zero. The graph must end at the speakers to run, but we don't want to hear ourselves.
- **`WebSocket`**: one open two-way connection; either side can send at any time.
- **`binaryType = 'arraybuffer'`**: receive binary data as raw bytes (`ArrayBuffer`).
- **`onopen` / `onmessage` / `onerror` / `onclose`**: socket event handlers.
- **`readyState === WebSocket.OPEN`**: only send if the socket is open.
- **`JSON.stringify` / `JSON.parse`**: object to text, and text to object.
- **`session.start` / `session.started` / `session.end`**: open, confirm and close a conversation.
- **`audio.flush` / `flush.ack`**: the server says "stop playing"; we reply "done".
- **`turn.state`**: the server says idle / listening / thinking / speaking / cancelling.
- **`turn_id`**: the ID of one question-and-answer exchange.
- **`instanceof ArrayBuffer`**: checks if the message is binary audio (vs JSON text).
- **`isSessionReadyRef`**: don't send audio before the server confirms the session.
- **`isIntentionalStopRef`**: tells "user clicked End" apart from "connection dropped".
- **`NotAllowedError`**: the error name when the user blocks the mic.
- **`setInterval`**: run every 1000 ms (the frames-per-second counter).
- **`try / catch`**: catch an error instead of crashing.
- **teardown / cleanup**: release the mic, audio engine and socket when done.
- **FPS**: frames per second sent (about 50, since 1000 ms / 20 ms).

### [public/audio-processor.js](../../frontend/public/audio-processor.js) - cuts mic audio into 20 ms frames
- **`AudioWorkletProcessor`**: base class for code that runs on the **audio thread**.
- **thread**: a separate line of execution. The audio thread isn't slowed by page work, so no glitches.
- **`process(inputs)`**: the browser calls it with **128 samples** each time (a **render quantum**).
- **`registerProcessor`**: gives the processor a name (`'vaani-audio-processor'`).
- **sample**: one number describing the sound at one instant.
- **`Float32` -> `Int16`**: from decimals in -1..1 to whole numbers in -32768..32767. **PCM** = raw audio as numbers. **16-bit** = each number takes 2 bytes.
- **`0x7fff` / `0x8000`**: hexadecimal for 32767 / 32768.
- **clamp** (`Math.max(-1, Math.min(1, x))`): force a value into a range.
- **640 bytes** = 320 samples x 2 bytes.
- **`port.postMessage(buf, [buf])`**: send to the main thread; the second argument **transfers** the memory instead of copying it (**zero-copy**).
- **flush / `last-frame`**: on push-to-talk stop, send the leftover partial frame (padded with silence) and then a marker.

### [hooks/usePlaybackQueue.js](../../frontend/src/hooks/usePlaybackQueue.js) - plays the agent's voice without gaps
- **queue**: items processed in arrival order.
- **`AudioBuffer`**: a chunk of audio in memory. **`createBuffer(1, n, rate)`**: 1 channel (**mono**).
- **`AudioBufferSourceNode` / `source.start(when)`**: play this chunk at an exact time.
- **`ctx.currentTime`**: the audio hardware clock, in seconds. It never drifts, unlike `setTimeout`.
- **gapless scheduling**: `startAt = max(now, nextStartTime)`, then `nextStartTime += duration`.
- **`setValueAtTime` / `linearRampToValueAtTime`**: set or smoothly slide the volume at exact times. A **10 ms fade** avoids a **click/pop**.
- **`onended`**: fires when a chunk finishes playing.
- **`Set`**: a collection with no duplicates (the active sources).
- **resample**: convert between sample rates (Piper speaks at 22,050 Hz; the speakers run at 48,000 Hz).
- **autoplay policy / `resume()`**: browsers keep audio paused until the user clicks something.

### [hooks/useTranscript.js](../../frontend/src/hooks/useTranscript.js) - the conversation record
- **immutable**: never change the old array; make a new one (`[...prev, entry]`). React notices the change that way.
- **spread `...`**: copy items into a new array or object.
- **updater function** `setX(prev => ...)`: compute new state from the previous state.
- **why refs too:** StrictMode runs updaters twice in dev, which duplicated lines. Refs are read once.
- **interrupted**: a reply cut by barge-in is kept and marked, not deleted.
- **delta**: one small new piece of the streaming text.

### [hooks/useTurnState.js](../../frontend/src/hooks/useTurnState.js) - mirrors the server's state machine
- **state machine**: a fixed set of states plus rules for moving between them: `idle -> listening -> thinking -> speaking -> idle`, with `cancelling` on a cut.
- **`agentDraft`**: the reply text so far.

### [hooks/useLatencyTelemetry.js](../../frontend/src/hooks/useLatencyTelemetry.js)
- **telemetry**: measurements the server sends about itself. **span / stage**: one timed step (ASR, LLM, TTS).

### [hooks/useReferenceRecorder.js](../../frontend/src/hooks/useReferenceRecorder.js), [usePhraseRecorder.js](../../frontend/src/hooks/usePhraseRecorder.js)
- **`MediaRecorder`**: records a stream into a file-like **Blob** (compressed, e.g. WebM/Opus).
- **Blob**: a chunk of binary data in memory (the recording).
- **object URL** (`URL.createObjectURL`): a temporary link to a Blob so `<audio>` can play it. **revoke** = free it.
- **`AnalyserNode`**: gives live audio samples for the level meter.
- **reference recording**: 30-60 s of your voice, used to clone it.

### [hooks/useEnrolUpload.js](../../frontend/src/hooks/useEnrolUpload.js)
- **upload**: send the Blob to the server (`FormData`, built in `api/enrolApi.js`).
- **polling**: ask "done yet?" every 2 s.
- **in-flight**: a request that's been sent and not yet answered.

### [hooks/useVoiceVerify.js](../../frontend/src/hooks/useVoiceVerify.js)
- **`AbortController`**: a cancel button for a `fetch`. `abort()` stops the request when you leave the page.

## 3.4 `turnState/` and `ptt/` - protocol rules

### [turnState/turnContracts.js](../../frontend/src/turnState/turnContracts.js)
- **contract / protocol**: the agreed message formats between frontend and backend (`docs/contracts.md`).
- **error codes**: `ASR_FAILED` (speech-to-text failed), `LLM_FAILED` (the AI model failed), `TTS_FAILED` (text-to-speech failed), `INPUT_REJECTED` (guardrail blocked it), `BAD_FRAME_SIZE` (audio chunk isn't 640 bytes).
- **validator** (`validateTurnState`): checks a message has the right shape before use.
- **ASR / LLM / TTS**: Automatic Speech Recognition / Large Language Model / Text-To-Speech.
- **guardrail**: a safety check on input.

### [turnState/turnFilter.js](../../frontend/src/turnState/turnFilter.js)
- **factory function** (`createTurnFilter`): a function that builds and returns an object.
- **closure**: the returned functions remember `flushed` and `audioTurnId` privately.
- **stale**: old and no longer wanted (audio of a cut reply).

### [ptt/pttPress.js](../../frontend/src/ptt/pttPress.js)
- **push-to-talk**: hold to speak, release to finish.
- **states**: `idle -> holding -> stopping -> idle`.
- **fallback timer**: if the last frame doesn't arrive in 300 ms, finish anyway.
- **dependency injection** (`setTimer`, `send` passed in): give the function its tools from outside so tests can fake them.
- **getter** (`get state()`): a property computed when read.

## 3.5 `login/` - Google sign-in

### [login/GoogleButton.jsx](../../frontend/src/login/GoogleButton.jsx)
- **GIS (Google Identity Services)**: Google's script that draws the sign-in button.
- **client ID**: our app's public ID at Google.
- **credential / ID token / JWT**: a signed message from Google saying "this is user X". **JWT** = JSON Web Token.
- **callback**: a function we hand over to be called later (when the user picks an account).

### [login/LoginPage.jsx](../../frontend/src/login/LoginPage.jsx), [LoginPanel.jsx](../../frontend/src/login/LoginPanel.jsx), [StudioDoor.jsx](../../frontend/src/login/StudioDoor.jsx)
- **views**: off / checking / refused / error / onair.
- **`useNavigate`**: change page from code. **`replace: true`**: don't add a Back-button entry.

### [login/authApi.js](../../frontend/src/login/authApi.js)
- **`fetch`**: the browser's HTTP request function.
- **GET / POST**: read / send data.
- **`credentials: 'include'`**: send and accept cookies on a **cross-origin** request.
- **origin**: scheme + host + port. `localhost:5173` and `localhost:8000` are different origins.
- **CORS** (Cross-Origin Resource Sharing): the server's permission for another origin to call it.
- **status codes**: 200 OK, 204 OK with no body, 401 not signed in, 403 forbidden, 404 not found, 503 service unavailable.

### [login/loginState.js](../../frontend/src/login/loginState.js)
Turns status codes into views (pure function).

### [login/RequireSignIn.jsx](../../frontend/src/login/RequireSignIn.jsx)
- **route guard**: sends you to `/login` if you're not signed in. It's for the user's convenience: the real security is on the backend.
- **`children`**: whatever is placed inside `<RequireSignIn>...</RequireSignIn>`.
- **`alive` flag**: ignore a late answer after leaving the page.

### [login/useSignOut.js](../../frontend/src/login/useSignOut.js)
- **cookie**: a small value the browser auto-sends to the server. **httpOnly**: JavaScript can't read it, so it's safe from injected scripts; only the server can delete it.
- **session**: the server remembering you're signed in (via that cookie).

## 3.6 Enrolment: `pages/`, `enrol/`, `api/`

Flow: consent -> record -> validation -> verify.
- [pages/EnrolConsentPage.jsx](../../frontend/src/pages/EnrolConsentPage.jsx): **consent** = your spoken permission; **challenge phrase** = a random sentence to prove you're live (anti-spoofing).
- [pages/EnrolRecordPage.jsx](../../frontend/src/pages/EnrolRecordPage.jsx): **level meter**, **elapsed timer**, 30 s minimum / 60 s auto-stop.
- [pages/EnrolValidationPage.jsx](../../frontend/src/pages/EnrolValidationPage.jsx) + [enrol/enrolValidationContracts.js](../../frontend/src/enrol/enrolValidationContracts.js): **rejection reasons**: TOO_SHORT, TOO_QUIET, **CLIPPING** (too loud, the wave gets cut off flat), **LOW_SNR** (signal-to-noise ratio: too much background noise), EXCESSIVE_SILENCE, CHALLENGE_MISMATCH (speaker similarity below 0.80).
- [pages/EnrolVerifyPage.jsx](../../frontend/src/pages/EnrolVerifyPage.jsx) + [enrol/verifyState.js](../../frontend/src/enrol/verifyState.js): **reducer** (`verifyReducer(state, event)`) = a function that takes the current state plus an event and returns the next state. States: loading, ready, playing, error, approving, approved.
- [enrol/verifyDemo.js](../../frontend/src/enrol/verifyDemo.js): `?demo=` fake answers. A **440 Hz tone** (the musical note A) is a stand-in for a voice. **WAV** = a simple audio file format.
- [api/enrolApi.js](../../frontend/src/api/enrolApi.js): **timeout** via AbortController (30 s); **poll** every 2 s, up to 60 times; errors are returned as `{ok:false}` instead of thrown.

## 3.7 Smaller folders

- [loopback/loopbackAnalysis.js](../../frontend/src/loopback/loopbackAnalysis.js): **loopback** = play a sound from the speaker and record it with the mic. **sine tone** = a pure beep (1 kHz). **cross-correlation** = slide the known beep along the recording and find where it matches best; that offset is the delay. **normalised peak quality** = how confident the match is (0 to 1).
- [loopback/useLoopbackMeasurement.js](../../frontend/src/loopback/useLoopbackMeasurement.js): **ScriptProcessorNode** = an older, deprecated way to read audio samples (acceptable for a test tool).
- [telemetry/latencyTelemetry.js](../../frontend/src/telemetry/latencyTelemetry.js): **VAD** (voice activity detection: is someone speaking?), **endpointer** (decides you've finished talking), **first token** (the first word from the AI), **sanitize** (clean up bad numbers).
- [theme/theme.js](../../frontend/src/theme/theme.js): **`data-theme` attribute** on `<html>`; **`localStorage`** = small permanent storage in the browser; **`prefers-color-scheme`** = the OS dark-mode setting; **`matchMedia`** = check a CSS media query from JavaScript.
- [components/AppLayout.jsx](../../frontend/src/components/AppLayout.jsx): **`<Outlet/>`** = where the current child page is drawn inside the layout. [Sidebar.jsx](../../frontend/src/components/Sidebar.jsx): **`NavLink`** = a link that knows if it's the active page.
- `pages/NotFoundPage.jsx`: the **404** page.

## 3.8 `landing/` - the home page (visual only)

- **scripted demo**: the tape animation is fake and timed; no mic, no network.
- [useReducedMotion.js](../../frontend/src/landing/useReducedMotion.js): **`prefers-reduced-motion`** = the OS setting for less animation. **`useSyncExternalStore`** = read a value from outside React and re-draw when it changes.
- [useActiveStep.js](../../frontend/src/landing/useActiveStep.js): **IntersectionObserver** = the browser tells you when an element enters an area of the screen.
- [IdeaSection.jsx](../../frontend/src/landing/IdeaSection.jsx) / [LatencySection.jsx](../../frontend/src/landing/LatencySection.jsx) / [CutBand.jsx](../../frontend/src/landing/CutBand.jsx): **scroll-driven animation** (`view-timeline`, `animation-range`) = CSS animation tied to scroll position instead of time. **`clip-path`** = show only part of an element.
- [Ticker.jsx](../../frontend/src/landing/Ticker.jsx): **marquee** = scrolling text strip. The list is drawn twice, so the loop is seamless.
- [canvasSize.js](../../frontend/src/landing/canvasSize.js): **devicePixelRatio** = real pixels per CSS pixel (2 on retina). It's capped for speed.
- [Preloader.jsx](../../frontend/src/landing/Preloader.jsx): the loading screen, once per **session** (`sessionStorage`).
- [landingContent.js](../../frontend/src/landing/landingContent.js): all text. `new URL('./x.webp', import.meta.url)` = an image path that both Vite and Node understand. **webp** = a modern compressed image format. **woff2** (in `fonts/`) = a compressed web font format. **OFL** = the Open Font License.
- **`useIstClock`**: India time, via `new Date().toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata' })`.

---

# Level 4 - The whole flow in one story (say this out loud)

> I click **Talk**. `StudioPage.handleConnect` calls `startCapture` in **useAudioCapture**. It asks for the mic with **getUserMedia**, creates a 16 kHz **AudioContext**, and loads **audio-processor.js** as an **AudioWorklet** on the audio thread. The worklet gathers 128-sample chunks into **320-sample, 20 ms frames**, converts them to **Int16 PCM (640 bytes)**, and **transfers** them to the main thread. Meanwhile a **WebSocket** opens and sends **session.start**. Once the server replies **session.started**, every frame goes out with `socket.send`. The server replies with JSON (**transcript.partial/final**, **turn.state**, **agent.text**, **agent.done**, **error**), which `handleServerMessage` sends to **useTranscript** and **useTurnState**, and **binary audio**, which goes to **usePlaybackQueue**. That schedules each chunk on the **AudioContext clock** so playback has no gaps. If I talk over the agent, the server sends **audio.flush**: playback fades out in **10 ms**, **turnFilter** drops the late audio of that turn, we answer **flush.ack**, and the screen shows **CUT.**

### Questions to rehearse
1. **Why an AudioWorklet?** It runs on the audio thread, so page work can't cause glitches. ScriptProcessor is deprecated and runs on the main thread.
2. **Why 640 bytes?** 16000 x 0.02 = 320 samples, x 2 bytes.
3. **Why a WebSocket, not HTTP?** Continuous two-way streaming; the server pushes events without being asked.
4. **How is playback gapless?** It's scheduled on `AudioContext.currentTime`, not on timers.
5. **Why a 10 ms fade on flush?** Cutting audio instantly makes a click.
6. **Why so many refs?** Handlers created once must see current values, and refs don't re-draw 50 times a second.
7. **Backend down?** `onerror` -> banner "WebSocket connection failed", view `offair`.
8. **Mic denied?** `NotAllowedError` -> `micStatus 'denied'` -> banner with Retry.
9. **Is the login guard security?** No: the backend refuses the socket without the cookie.
10. **Why `credentials: 'include'`?** Cross-origin requests need it to send and store the cookie.
11. **How is it tested?** Pure logic files run with `npm test` (plain Node); UI states are checked with `?preview=`.
12. **Why the `VITE_` prefix?** Only those variables reach browser code, so other variables can't leak.
13. **What is node_modules, and why isn't it in git?** Installed libraries; rebuilt exactly from `package-lock.json` with `npm install`.
14. **dependencies vs devDependencies?** Shipped to the browser vs only used to build, check and test.
