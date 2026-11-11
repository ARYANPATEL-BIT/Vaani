# Vaani stack: what we built, why, and what we rejected

This is the project-wide reference for "why this and not that". It describes the
code on `dev` at commit `27a34c5` (2026-10-15). Every claim points to a file and
line, or to a config key in `backend/config.toml`. Nothing planned is described as
if it exists; where something is planned or missing, it says so.

Each choice follows the rule in `STANDARD.md`: what it is, why we use it, and
exactly one alternative with why we did not pick it. Versions come only from
[`docs/versions.md`](../versions.md). The flow of a turn is in
[`PROJECT.md`](PROJECT.md); the full protocol is in [`docs/contracts.md`](../contracts.md).
Section 2 below can be read on its own.

A few words used throughout:

- **Frame**: a 20 ms slice of audio, sent as one WebSocket message.
- **Turn**: one thing the user says, plus the agent's reply to it. Each turn has a
  `turn_id`, made when the turn opens (`session.py:82-86`).
- **Barge-in**: the user interrupts the agent while it is thinking or speaking.
- **Cancellation token**: a flag (`asyncio.Event`) that a barge-in sets; every part
  of the reply checks it before it sends anything (`reply.py:20-24`).

## 1. The stack at a glance

| Layer | What we use | One-line why | File |
|---|---|---|---|
| Browser UI | React 19.3.0, react-router-dom 7.18.4, built with Vite 8.3.0 | Many pieces of live state (transcript, turn state, press state) re-render from data | `frontend/src/main.jsx`, `router.jsx` |
| Mic capture | Web Audio `AudioWorklet`, 16 kHz mono, 20 ms Int16 frames | Runs on the audio thread, so UI work cannot drop audio | `frontend/public/audio-processor.js:20`, `src/hooks/useAudioCapture.js:206-244` |
| Playback | Web Audio buffers scheduled on the `AudioContext` clock | The audio clock is steady; JavaScript timers are not | `src/hooks/usePlaybackQueue.js:113-150` |
| Transport | One WebSocket per session at `/ws/session`: JSON text for control, binary for audio | One ordered, two-way channel for everything | `backend/vaani/gateway.py:120` |
| Web server | FastAPI 0.141.1 on uvicorn 0.53.0 (`[standard]` extra) | Async: one process serves many sockets while it waits on the network | `backend/vaani/app.py:86` |
| Message shapes | Pydantic 2.13.5 models | Incoming JSON is validated by building the model | `backend/vaani/protocol.py:81-83` |
| Config | `config.toml` read by pydantic-settings 2.15.0; secrets only from the environment | No hardcoded values; no key in a committed file | `backend/vaani/config.py`, `config.toml:1-7` |
| Voice activity detection (VAD) | Silero VAD v6.2.3 (ONNX file) run with onnxruntime 1.30.0 on CPU | Small neural model, no PyTorch | `backend/vaani/vad.py:72-104` |
| End of turn | Our own endpointer: 700 ms of silence, counted in frames | No timers, no network in the hot path | `backend/vaani/endpoint.py`, `[endpoint].end_of_turn_silence_ms` |
| Push-to-talk | Our own press buffer, used instead of the endpointer | The stop press ends the turn with no wait | `backend/vaani/ptt.py` |
| Speech recognition (ASR) | faster-whisper 1.2.1 (CTranslate2 4.8.2); committed default `small` / `cpu` / `int8` | Faster than original Whisper, no PyTorch | `backend/vaani/asr/whisper.py`, `[asr.whisper]` |
| Language model (LLM) | Groq `openai/gpt-oss-20b` first, Gemini `gemini-3.5-flash-lite` as failover, over REST with httpx 0.28.1 | We own the HTTP stream, so a cancel really closes it | `backend/vaani/providers/chain.py`, `[llm].provider_order` |
| Spend guard | A per-process request counter, 200 requests | Checked before any paid request is sent | `backend/vaani/spend.py:33-45`, `[llm].max_requests_per_process` |
| Reply chunking | Our own clause chunker | Speech starts while the model is still writing | `backend/vaani/chunker.py`, `[chunker]` |
| Speech synthesis (TTS) | piper-tts 1.8.0 (espeak-ng + a VITS network on onnxruntime), local CPU | No network hop and no cost per chunk | `backend/vaani/tts/piper.py` |
| Clock line | Python `zoneinfo` with tzdata 2026.5 | The model gets the real date and time | `backend/vaani/reply.py:91,180`, `[llm].timezone` |
| Database | SQLite through Python's standard `sqlite3`, raw SQL, WAL mode | A file inside our process: no server, no new dependency | `backend/vaani/db.py`, `schema.sql` |
| Tests and lint | pytest 9.1.1, ruff 0.16.8; frontend `npm test` (plain Node scripts) | Every stage tested with fakes, no models or keys | `backend/tests/`, `frontend/package.json:10` |
| CI | GitHub Actions, uv 0.11.28, `uv sync --frozen` | Every PR checked the same way on a clean machine | `.github/workflows/ci.yml`, `asr-slow.yml` |
| External: Groq | Groq's OpenAI-compatible REST API; key in the `Authorization` header | Fastest first token we measured (p50 788 ms, `config.toml:221-226`) | `providers/groq.py:89`, `[llm.groq]` |
| External: Gemini | Gemini REST API with `alt=sse`; key in the `x-goog-api-key` header | Failover when Groq is rate-limited, slow or down | `providers/gemini.py:93-94`, `[llm.gemini]` |
| External: Hugging Face | Downloads only: the Whisper model on first use (not pinned), Piper voices from a pinned revision | No model is committed except Silero; each download is checked where a pin exists | `config.toml:145` (Whisper), `config.toml:279` and `backend/scripts/fetch_models.py` (voices) |

Python is 3.11 (`versions.md`). Licences that need care: piper-tts is
GPL-3.0-or-later, and both Hindi voices are CC BY-NC-SA 4.0 (non-commercial)
(`versions.md:107-110`, `config.toml:286-287`).

## 2. Our API: what the backend exposes and the browser uses

### 2a. HTTP routes

The app has one route of its own and one WebSocket. FastAPI also adds its
documentation routes by default, because `app.py:86` does not switch them off.

| Route | What it returns | Who calls it | Where |
|---|---|---|---|
| `GET /health` (and `HEAD`) | `{"status": "ok", "version": "0.1.0"}`. The version is the app's (`vaani/__init__.py:10`), not the protocol's. It reads no settings, so it can leak no config | A person checking the server is up (`README.md:69`), and `backend/tests/test_health.py`. **The frontend never calls it**: `API_BASE_URL` in `frontend/src/config.js:14` is defined but unused | `backend/vaani/app.py:141-149` |
| `GET /docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json` | FastAPI's generated API pages and schema | Nobody in our code; a developer in a browser | Added by FastAPI. Checked on a bare FastAPI 0.141.1 app, not by starting ours |
| `WS /ws/session` | The voice session (2b) | `useAudioCapture.js:248`, URL from `config.js:21-22` | `backend/vaani/gateway.py:120-319`, added by `app.py:152` |

### 2b. The WebSocket

A **WebSocket** is one network connection that stays open, so both sides can send a
message at any moment. HTTP, by contrast, is "the browser asks, the server answers".

- **One socket per session.** A session is one connection. Its state (the
  `Session` object, `session.py:31-68`) belongs to the one coroutine that serves
  that socket (`gateway.py:1-8`). Nothing is shared between sessions.
- **How it starts.** The user clicks Start. The browser opens the mic, opens the
  socket and, when it opens, sends `session.start` with the persona, the mode, the
  reply language (v0.10) and the audio format (`useAudioCapture.js:277-289`). The server
  checks it and answers `session.started` with a new `session_id` (`gateway.py:191-258`). The browser sends
  no audio until then (`useAudioCapture.js:408-412`).
- **How it ends.** Three ways, recorded as the session's `end_reason`:
  `client_end` (the browser sent `session.end`; the server closes with code 1000,
  `gateway.py:283-291`), `disconnect` (the socket just closed), or `error` (the
  server's loop raised, `gateway.py:300-302`). In every case the `finally` block stops
  the reply, abandons transcription and records the end (`gateway.py:303-312`,
  `turns.py:229-246`).
- **Why one socket and not several** (for example one for audio and one for
  control): the protocol depends on order. `ptt.end` must arrive after the last
  frame of the press; `audio.start` must come before its frames; `audio.flush` must
  be the first thing after a cut. Messages on one WebSocket arrive in the order they
  were sent (`contracts.md` 2.8). Two sockets give no order between them.

### 2c. Every message in protocol v0.10

Control messages are JSON text with a `type` field. Audio is raw binary. The
models are in `backend/vaani/protocol.py`; the browser side is in
`frontend/src/hooks/useAudioCapture.js` and `src/pages/ConversationPage.jsx`.

**Client to server**

| Message | Fields | When the browser sends it | What the server does |
|---|---|---|---|
| `session.start` | `persona`; `mode`: `"vad"` or `"ptt"`, default `"vad"` (`protocol.py:155`); `reply_language` (v0.10): `"any"`, `"en"` or `"hi"`, default `"any"` (`protocol.py:133,158`); `audio`: `sample_rate`, `channels`, `frame_ms` (`protocol.py:139-159`). `protocol.py:152` gives `persona` a default of `"default"`; `contracts.md` 2.3 shows it in the payload and does not say it is optional | Once, when the socket opens, built by `buildSessionStart` (`turnContracts.js:180`, called at `useAudioCapture.js:277-289`); `reply_language` is the page's "Reply" picker (`ConversationPage.jsx:296-312`) | Malformed, or an unknown `mode` or `reply_language`: `BAD_MESSAGE`. A session already open: the same `session.started` again, nothing changes. Audio not 16000 / 1 / 20: `UNSUPPORTED_FORMAT`. Persona not in `[personas]`: `BAD_MESSAGE`. Otherwise it makes the session (with its reply language, `session.py`), its pipeline and its database row, then answers `session.started` (`gateway.py:191-258`). The reply language is not stored in the database |
| audio frame (binary) | 640 bytes: 320 samples of 16-bit little-endian PCM, mono, 16 kHz, 20 ms. The size is computed from config (`gateway.py:63-73`) | Every 20 ms after `session.started` (`audio-processor.js:20,51`; `useAudioCapture.js:389-418`). In a ptt session, only during a press (`useAudioCapture.js:404-406`) | No session: `SESSION_NOT_STARTED`. Wrong size: `BAD_FRAME_SIZE`, frame dropped. Otherwise counted and passed to the turn pipeline: VAD, then the endpointer or barge-in judge (vad) or the press buffer (ptt) (`gateway.py:147-166`, `turns.py:162-194`) |
| `ptt.start` | `type` only (`protocol.py:156-160`) | Speak pressed: button or Space (`pttPress.js:76-82`, called from `useAudioCapture.js:457-474`) | In a vad session: `BAD_MESSAGE` (`gateway.py:273-276`). A press already open: ignored. Agent thinking or speaking: a barge-in at once. Otherwise: a new turn, `listening`. Then VAD memory is reset and the press opens (`turns.py:196-215`) |
| `ptt.end` | `type` only (`protocol.py:163-167`) | Stop pressed, after the worklet hands over its last frame, or after 300 ms (`pttPress.js:59-63,85-102`; `config.js:46`) | No press open: ignored. Too little voiced audio: the turn is dropped, `idle`, no transcription. Otherwise the turn ends now: `thinking`, then transcription (`turns.py:217-223,358-365`; `ptt.py:78-113`) |
| `flush.ack` | `turn_id`, `client_ts` (the browser's `performance.now()`) (`protocol.py:170-181`) | Right after the browser has stopped playback for an `audio.flush` (`useAudioCapture.js:312-340`) | Malformed: `BAD_MESSAGE`. Otherwise it times the round trip on the server's own clock and logs it; `client_ts` is logged, never subtracted. An ack for a turn not waiting for one is logged and ignored (`gateway.py:258-269`, `session.py:140-172`) |
| `session.end` | `type` only (`protocol.py:149-153`) | The user stops the conversation, if the session is ready (`useAudioCapture.js:111-125`) | `end_reason = client_end`, closes the socket with code 1000, then cleans up (`gateway.py:283-291`) |
| any other `type` | | Not sent by our browser. `dev.flush` (removed in v0.7) is one | `UNKNOWN_MESSAGE_TYPE` (`gateway.py:293-295`). Before `session.start`, any control message except `session.start` gets `SESSION_NOT_STARTED` instead (`gateway.py:252-256`) |

**Server to client**

| Message | Fields | When the server sends it | What the browser does |
|---|---|---|---|
| `session.started` | `session_id`, `mode`, `reply_language` (v0.10) (`protocol.py:200-206`) | After an accepted `session.start`, and again for any repeat, with the FIRST session's values (`gateway.py:201-207,254-258`) | Marks the session ready, so frames start to flow. The server's `mode` and `reply_language` are the ones used and shown; no `reply_language` (an older server) reads as `"any"` (`useAudioCapture.js:311-321`, `turnContracts.js:192`) |
| `turn.state` | `turn_id` (null only in `idle`), `state`: `idle`, `listening`, `thinking`, `speaking`, `cancelling` (`protocol.py:111-123,256-261`) | On every state change. The only way to change state is `TurnStateMachine.move_to` (`turn_state.py:68-81`); the legal moves are listed in `turn_state.py:31-44` | Shows the state (`useTurnState.js:39-51`). Remembers the agent's turn while it is busy, for a ptt local stop; clears the error banner on `listening` (`useAudioCapture.js:347-359`). On `cancelling`, marks the reply interrupted (`ConversationPage.jsx:123-128`) |
| `transcript.partial` | `turn_id`, `text` (`protocol.py:231-237`) | **Never today**: `[asr].partial_interval_ms = 0` turns partials off (`config.toml:135`) | Would replace the partial line (`ConversationPage.jsx:116-117`) |
| `transcript.final` | `turn_id`, `text`, `duration_ms`, `language` (`protocol.py:240-253`) | Once per turn, when Whisper has finished (`asr/runner.py:230-232`). A turn cut by a barge-in still gets it, possibly after the next turn's `listening` (`contracts.md` 2.4) | Adds the user's line (`ConversationPage.jsx:118-119`). Never dropped (`turnFilter.js:13-16`) |
| `agent.text` | `turn_id`, `delta` (`protocol.py:264-269`) | Each piece of text as the model streams it, while the state is still `thinking` (`reply.py:205`) | Appends it (`ConversationPage.jsx:132-134`). Dropped if the turn was flushed (`turnFilter.js:43-49`) |
| `agent.done` | `turn_id`, `text` (the whole reply) (`protocol.py:272-277`) | The reply is complete, before `audio.end` (`reply.py:262`) | Commits the reply line (`ConversationPage.jsx:135-137`). Dropped if flushed |
| `audio.start` | `turn_id`, `sample_rate` (`protocol.py:203-211`) | Before the reply's first frame, right after `turn.state speaking` (`speaker.py:205-210`). 22050 for every voice today (`config.toml:263-264`) | Sets the playback rate (`ConversationPage.jsx:111-113`, `usePlaybackQueue.js:211-215`). The filter records whose frames follow (`turnFilter.js:43-47`) |
| audio frame (binary) | 16-bit little-endian PCM, mono, at `audio.start`'s rate, 20 ms: 882 bytes at 22050 Hz (`speaker.py:192-194`) | As each chunk is synthesised; the token is checked before every send (`speaker.py:160-167`) | Scheduled right after the previous one on the audio clock (`usePlaybackQueue.js:113-150`). Dropped if its turn was flushed (`useAudioCapture.js:284-293`) |
| `audio.end` | `turn_id` (`protocol.py:214-218`) | After the last frame of a finished reply (`speaker.py:169-173` via `reply.py:264`), or before `TTS_FAILED` if audio had started (`reply.py:243`) | Nothing: the scheduled audio plays out. No handler in `ConversationPage.jsx:107-156`. Dropped if flushed |
| `audio.flush` | `turn_id` (`protocol.py:221-228`) | A barge-in, as the first message out (`barge_in.py:181-182`, `session.py:105-138`) | Marks the turn flushed, fades all audio to zero in 10 ms and stops it (`usePlaybackQueue.js:157-192`), sends `flush.ack`, marks the reply interrupted (`useAudioCapture.js:312-340`, `ConversationPage.jsx:142-144`) |
| `error` | `code`, `message`; no `turn_id` (`protocol.py:195-200`) | See 2d | Banner "CODE: text" (`useAudioCapture.js:341-346`). Keeps any streamed reply text as a line (`ConversationPage.jsx:150-153`) |
| `telemetry` | In `contracts.md` 2.6 (v0.5) | **Never sent.** `protocol.py` has no model for it (`protocol.py:50-51`) | The browser would accept it (`useLatencyTelemetry.js:46`) but never receives one |

### 2d. Error codes

Every error is non-fatal: the socket stays open (`protocol.py:195-196`). No error
carries a `turn_id`, so the browser cannot tell which turn an error is about.

| Code | When it happens | Sent from | What state the turn ends in |
|---|---|---|---|
| `SESSION_NOT_STARTED` | Audio, or any control message but `session.start`, before a session exists | `gateway.py:150-154,252-256` | No turn exists |
| `UNSUPPORTED_FORMAT` | `session.start`'s audio is not 16000 / 1 / 20 | `gateway.py:203-209` | No session is made |
| `BAD_FRAME_SIZE` | A binary frame is not 640 bytes | `gateway.py:155-162` | The frame is dropped; the turn goes on |
| `BAD_MESSAGE` | Not JSON, no `type`, a malformed `session.start` or `flush.ack`, an unknown persona, mode or (v0.10) reply language, or `ptt.start` / `ptt.end` in a vad session | `gateway.py:175-184,189-195,210-216,259-265,273-276` | The message is dropped; nothing else changes |
| `UNKNOWN_MESSAGE_TYPE` | A `type` the server does not handle | `gateway.py:293-295` | The message is dropped |
| `ASR_FAILED` | Whisper raised, or took longer than `[asr].timeout_s` (5 s) | `asr/runner.py:248-265` | No `transcript.final`. The reply gets no text, so `idle` (`turns.py:417-424`). Database row: `failed`, `error_code = ASR_FAILED` (`turn_log.py:146-147`). For a cut turn, nothing is carried |
| `LLM_FAILED` | Every provider failed, a non-failover provider error (bad key, bad request), the spend cap, or an empty reply | `reply.py:228-236,251-258` | No `agent.done`; `idle` (`reply.py:272-283`). Text already streamed stays on screen. No spoken apology |
| `INPUT_REJECTED` | The transcript matched a `[guardrail].patterns` regex. The model is never called | `reply.py:170-175` | `idle`. The message is vague on purpose: "that turn wasn't processed" (`reply.py:61-63`) |
| `TTS_FAILED` | Piper raised while speaking a chunk | `reply.py:237-247` | `audio.end` if audio had started, then `error`, then `idle`; no `agent.done` |

If a barge-in lands while an error is being sent, the error still goes out but the
move to `idle` does not: the barge-in owns the state from then on (`reply.py:280-283`).

### 2e. The design decisions behind the protocol

| Choice | What we do | Why | The one alternative | Why not the alternative |
|---|---|---|---|---|
| A connection that stays open | WebSocket | Audio flows both ways all the time, and the server must be able to speak first (`turn.state`, `audio.flush`) | HTTP polling: the browser asks "anything new?" every N ms | Every answer waits up to one polling interval, and each poll is a new request. Mic audio would need a separate upload request every 20 ms |
| Server push on the same connection as the upload | One WebSocket for both directions | One ordered channel (2b) | Server-sent events (SSE): a one-way stream from server to browser, plus HTTP POSTs for the mic | Two channels with no order between them: `ptt.end` could overtake the last frame of the press |
| Our own media path | Raw frames over the WebSocket to our own server | We see and time every frame; VAD, endpointing and barge-in are ours | WebRTC: the browser's real-time media stack (Opus audio, jitter buffer), usually through a media server | A media server and connection setup (ICE, STUN, TURN) to run, and audio we would have to decode back to PCM for Silero and Whisper. The browser's echo cancellation we already get from `getUserMedia` (`useAudioCapture.js:206-215`) |
| Two kinds of message | JSON text for control, raw binary for audio | Audio is already bytes; JSON is easy to read and validate | Everything as JSON, audio as base64 text | Base64 makes audio about 33% bigger and costs an encode and decode on every frame, 50 times a second (`backend-learning/02-ws-gateway.md:151`) |
| Audio format | 20 ms frames of 16 kHz, 16-bit PCM, uncompressed: 32,000 bytes a second | Silero and Whisper both take 16 kHz PCM (`vad.py:42-43`, `asr/whisper.py:45`); no codec on either side | Opus, a compressed voice codec | An encoder in the browser and a decoder dependency on the server, on every frame, before VAD can run. It would save bandwidth by an amount we have not measured; on one machine bandwidth was never the problem |
| `turn_id` on every turn message | Transcripts, `agent.*`, `audio.*` and `turn.state` all carry it | After a barge-in, messages of the old turn and the new turn are in flight together; the id says which is which | One implicit "current turn" on each side | A late `transcript.final` or `flush.ack` of a cut turn would be taken for the new turn (`contracts.md` 2.4, 2.7) |
| The browser drops messages of flushed turns | A set of flushed `turn_id`s; binary frames belong to the latest `audio.start`'s turn (`turnFilter.js:22-49`) | In ptt mode the browser cuts the turn itself, one round trip before the server knows; frames still on the wire for it must not play. The server already sends nothing after its own flush (`session.py:124-129`) | One true/false "flushed" flag (the old code) | Any `audio.start` cleared it, so an old turn could not be told from a new one (`PROJECT.md` section b) |
| `audio.flush` first in a barge-in | Token set, then `audio.flush`, then `cancelling`, then `listening` (`barge_in.py:178-182`, `turns.py:293-313`) | The user judges the interruption by when the speaker goes quiet (`contracts.md` 2.7) | Stop the model stream and synthesis first, then tell the browser (the spec PDF's order, `contracts.md:299-301`) | The speaker keeps playing while the server tidies up |
| Start and end pairs | `session.start`/`session.end`, `audio.start`/`audio.end`, `ptt.start`/`ptt.end` | Each pair brackets a span, so both sides know what is open; one naming rule for all three | One toggle message (for example `ptt` with `pressed: true/false`) | A lost or repeated toggle flips the meaning; a repeated `ptt.start` is simply ignored (`turns.py:202-205`) |
| Mode fixed per session | `mode` only in `session.start`; a second `session.start` changes nothing (`gateway.py:196-202`) | The pipeline is built once from the mode: a press buffer or an endpointer, never both (`turns.py:95-120`) | A message to switch mode mid-session | Rules needed for an open press, an open utterance and VAD's memory at the switch. Reconnecting does the same job |
| Reply language fixed per session (v0.10) | `reply_language` only in `session.start`, kept on the `Session`; a second `session.start` changes nothing. `"en"`/`"hi"` add one line after the clock line (`persona.py:51-76`) and pick the voice for every reply (`speaker.py:200-216`) | One choice for a whole conversation, read once by `reply.py` (`reply.py:90-96`): the prompt, the voice and the history stay in one language | Send it on every turn (a field the server reads per reply) | A language switch mid-conversation leaves history in the other language, which pulls the model back to it, and a turn already being answered would need a rule for which value it uses. Reconnecting does the same job |
| Versioning | `contracts.md` is the source of truth; v0.10 now; only the PR that changes it bumps it (`contracts.md:38-40`). Wording fixes are "editorial, no version change" (`contracts.md:387,389,391,392`) | One place to read; the history table says what each version added | A version field on the wire, checked at `session.start` | Two developers, one repo, deployed together. **Cost:** nothing at runtime checks the version. `/health` reports the app version `0.1.0`, not the protocol's |

### 2f. Two walkthroughs, message by message

Arrows: `->` browser to server, `<-` server to browser. T1 and T2 are turn ids.

**A normal push-to-talk turn**

1. `-> session.start` (persona, mode `ptt`, reply_language `any`, audio 16000/1/20)
2. `<- session.started` (session_id, mode `ptt`, reply_language `any`)
3. The user presses Speak. `-> ptt.start`
4. `<- turn.state listening` (T1)
5. `-> audio frames`, every 20 ms, only while pressed
6. The user presses Stop. `-> last audio frame` (padded with silence), then `-> ptt.end`
7. `<- turn.state thinking` (T1)
8. `<- transcript.final` (T1)
9. `<- agent.text` (T1), several, while still `thinking`
10. `<- turn.state speaking` (T1), at the first chunk's audio
11. `<- audio.start` (T1, sample_rate 22050)
12. `<- audio frames`, mixed with more `<- agent.text`
13. `<- agent.done` (T1)
14. `<- audio.end` (T1)
15. `<- turn.state idle` (turn_id null), when the server estimates the audio has played

A hands-free turn is the same from step 4, except that there is no `ptt.start` or
`ptt.end`: frames always flow, speech opens the turn and 700 ms of silence ends it.

**An interruption (hands-free)**

1. The agent is speaking T1: `<- audio frames` (T1)
2. `-> audio frames`: the user starts talking (mic frames flow all the time)
3. No message: the server judges 200 ms of speech (`[barge_in].min_speech_ms`)
4. `<- audio.flush` (T1), first
5. `<- turn.state cancelling` (T1)
6. `<- turn.state listening` (T2), whose audio starts at the user's first sound
7. `-> flush.ack` (T1), once the browser has stopped playback; T2 is already current
8. `-> audio frames` go on; after 700 ms of silence the turn continues from step 7 of
   the walkthrough above: `<- turn.state thinking` (T2), `<- transcript.final` (T2) ...

If T1 was cut while `thinking`, there is no audio to flush but `audio.flush` is still
sent, and T1's own `transcript.final` may arrive after step 6. In ptt mode, step 3 is
`-> ptt.start`, and the browser stops playback before sending it.

## 3. Local models and libraries

| Choice | What it is | Why we use it | The one alternative | Why not the alternative |
|---|---|---|---|---|
| Silero VAD v6.2.3 | A small neural network that gives each 32 ms of audio a speech probability. We run it every time 512 samples have built up (`vad.py:16-21`) | Accurate on noise; tiny; runs on CPU in about 1 ms a frame (`turns.py:16`) | WebRTC VAD | Fast, but marks much noise and music as speech (`PROJECT.md` section b) |
| Loading Silero with onnxruntime directly | We read the ONNX file, check its sha256 and call it in about 15 lines (`vad.py:72-104,204-217`) | No PyTorch. Silero's memory is kept per session in our `VadStream`, so one model is shared safely (`vad.py:142-149`) | The `silero-vad` pip package | It requires torch (about 200 MB, or about 2 GB as the CUDA build on Linux), and it keeps its memory inside the model object, so a shared model would mix users (`backend-learning/08-vad.md:28,53`) |
| VAD settings | `threshold = 0.5`; speech starts after 4 speech frames (80 ms), ends after 10 silent frames (200 ms) (`config.toml:51-59`) | One cough frame does not start speech; a short pause between words does not end it | Decide per frame with no hysteresis | Every click starts a turn and every short pause ends one |
| faster-whisper 1.2.1 | Whisper's weights run by CTranslate2, a C++ engine | Several times faster than the original Whisper and no PyTorch; it releases Python's lock while it works, so frames keep flowing (`asr/whisper.py:9-13`) | The original PyTorch Whisper (`openai-whisper`) | Slower, and pulls in PyTorch (`PROJECT.md` section b) |
| Piper (piper-tts 1.8.0) | espeak-ng turns letters into sounds, then a VITS network makes the audio, on CPU (`tts/piper.py:3-5`) | Local: no network hop and no cost on every chunk. A short first chunk took 36 ms p50 (`docs/findings/tts-day12/measure_tts_20261006-111202.txt`) | A hosted voice, Sarvam Bulbul, named as the intended alternative in `tts/base.py:4-5` | A network round trip and a cost on every chunk, and an API key on the reply path |
| FastAPI 0.141.1 + uvicorn 0.53.0 | An async web framework and the server that runs it | One process reads many sockets while it waits on the network; WebSocket support built in | Flask | Synchronous: one request per worker, a poor fit for long-lived real-time sockets (`backend-learning/01-repo-setup.md:119`) |
| httpx 0.28.1 | An async HTTP client | We send the request and read the stream ourselves, and close it the moment the token is set (`providers/streaming.py:43-77`) | The vendors' Python SDKs | They hide the HTTP stream, so we could not be sure a cancel closes the connection; and a vendor SDK is banned outside `providers/` (`CLAUDE.md`) |
| tzdata 2026.5 | The IANA time zone database, for Python's `zoneinfo` | The clock line in every prompt names `Asia/Kolkata` (`[llm].timezone`); Windows has no zone database of its own (`pyproject.toml:23`) | A fixed offset (+05:30) in config | Wrong twice a year for any zone with daylight saving, and it prints no zone name (`PROJECT.md` section b) |
| React 19.3.0 | A UI library: the page is drawn from state | Transcript, turn state, mode and press state all change many times a second | Plain JavaScript with hand-written DOM updates | Every state change would need its own DOM code. No learning document recorded this choice; this reason is ours |
| Vite 8.3.0 | Build tool and dev server | Fast start, little configuration | Webpack | Slower to configure and to run (`frontend-learning/01-frontend-setup.md:116`) |
| `AudioWorklet` | Code that runs on the browser's audio thread | Mic frames are built there, so UI work cannot drop audio (`audio-processor.js`) | `ScriptProcessorNode` | Runs on the main UI thread, drops frames under load, and is deprecated (`PROJECT.md` section b) |

**Whisper settings** (`[asr]`, `[asr.whisper]`, `asr/whisper.py`)

| Setting | Value | Why | The one alternative | Why not |
|---|---|---|---|---|
| `model` / `device` / `compute_type` | `small` / `cpu` / `int8` (`config.toml:146-148`) | Runs on any laptop and in CI; CPU by default is a project rule | `large-v3` / `cuda` / `float16` | Needs a GPU. It is the only setting that handles Hinglish, so it is used as a local `.env` override only (`config.toml:138-144`) |
| `language` | `"hi"` (`config.toml:156`) | Auto-detection flips between hi, ur and la for one speaker; `"en"` translates Hindi into English (`config.toml:153-155`) | Auto-detect | The flips above |
| `initial_prompt` | One romanized Hinglish sentence (`config.toml:160`) | Nudges Whisper to keep English words in Latin letters | No prompt | English words come back in other scripts more often (`config.toml:158-159`) |
| `beam_size` | 5 (`config.toml:163`) | faster-whisper's default | 1 (greedy) | Not measured either way |
| `temperature` | `[0.0]`: one decode, no retries (`config.toml:168`) | The default retries turned one clip into a 62 s stall (`config.toml:165-167`) | The default retry ladder 0.2 ... 1.0 | A wrong transcript can be recovered from; a 62 s stall loses the turn |
| `vad_filter` | Always on, a constant (`asr/whisper.py:40-43`) | Without it Whisper invents words into silence: 5 s of silence took 13 s | Off | The invented words and the stall |
| `task` | Always `transcribe` (`asr/whisper.py:37-39`) | `translate` outputs English and loses the words said | `translate` | Never a valid choice here |
| `max_concurrent` | 2 (`config.toml:124`) | Our own pool of 2 threads; one decode per session at a time (`asr/runner.py:13-17`) | asyncio's shared default thread pool | Its size is not ours, and other work queues on it (`asr/whisper.py:112-113`) |
| `timeout_s` | 5.0 (`config.toml:129`) | Bounds how long a turn waits for its transcript | No timeout | A stuck decode would leave the user waiting for ever |

**The Piper voices** (`[tts.piper.voices]`, `config.toml:295-322`). Each persona has
one Hindi and one English voice; the first chunk of a reply picks one by its script
(any Devanagari: Hindi) and keeps it for the whole reply (`speaker.py:187-203`).

| Persona | Hindi voice | English voice | Note |
|---|---|---|---|
| `default` | `hi_IN-priyamvada-medium` (female) | `en_US-kristin-medium` (female) | |
| `tutor` | `hi_IN-pratham-medium` (male) | `en_US-norman-medium` (male) | The tutor prompt speaks as a man |
| `support` | the default's voices | the default's voices | `length_scale = 1.15`: about 15% slower |

All four output 22050 Hz, read from the voice file, never assumed (`tts/piper.py:110`).
The voice files are fetched from a pinned revision and checked by sha256 at fetch and
at load (`config.toml:275-283`, `tts/piper.py:69-83`).

## 4. The database

### Why SQLite, and why plain SQL

| Choice | What it is | Why | The one alternative | Why not the alternative |
|---|---|---|---|---|
| SQLite | A database that is one file, run as a library inside our own process (`db.py:3-5`) | No server to install; one machine; a few rows a minute | PostgreSQL | A server to install, run and secure, plus a driver dependency, for that load (`backend-learning/18-database.md:97`) |
| Python's standard `sqlite3`, raw SQL | We write the SQL strings ourselves (`db.py:43-60`) | No new dependency; the real SQL is readable in one file | An ORM such as SQLAlchemy (Python classes mapped to tables) | A dependency and a layer that writes the SQL for you, for a handful of statements (`18-database.md:98`) |
| WAL mode | "Write-ahead log": a write is appended to a side file instead of rewriting the main file (`db.py:13-16`) | `turn_stats.py` can read while the server writes; a crash mid-write leaves the database as it was | SQLite's default rollback journal | Readers and the writer block each other (`18-database.md:99`) |
| `PRAGMA user_version` | A number SQLite keeps in the file's header; ours is the schema version, 1 (`schema.sql:5-8`) | Free: it exists in every SQLite file | A `schema_version` table | A table must itself be created and read with SQL (`18-database.md:100`) |
| `STRICT` tables | SQLite refuses a value of the wrong type (`schema.sql:10-11`) | A plain SQLite table would store text in a number column without complaint | Plain tables | Bad data would be stored silently and found later in the statistics |
| One writer thread | `DbWriter` owns the connection; the event loop only puts statements on a queue (`db.py:115-168`) | A slow disk never delays a frame; rows land in order, so a session's row is written before its turns' rows | `asyncio.to_thread` for every write | Two writes could run at once and fight over SQLite's single write lock; a turn row could land before its session row (`18-database.md:101`) |

A **thread** is a second line of execution in the same program. The event loop is
the one thread serving every socket, so it must never wait on a disk.

### Every SQL statement the code runs

S1 to S7 run once, at server start, in `open_db` (`db.py:75-112`, called from
`app.py:74-76`). S8 to S10 are queued on the event loop and run later by the writer
thread (`db.py:157-168`). S11 runs only when someone runs `scripts/turn_stats.py`.

**S1** (`db.py:86`)

```sql
PRAGMA journal_mode = WAL
```

What: switches the file to WAL mode and returns the mode now in force; the code
refuses to start unless it says `wal` (`db.py:86-88`). Alternative: leave the default
rollback journal. Why not: see the WAL row above.

**S2** (`db.py:91`)

```sql
PRAGMA foreign_keys = ON
```

What: makes SQLite check `turns.session_id REFERENCES sessions(id)`. It is off by
default and must be set on each connection (`db.py:89-90`). Alternative: leave it
off. Why not: a turn row could point at a session that does not exist, and nothing
would say so.

**S3** (`db.py:92`, read again at `db.py:99`)

```sql
PRAGMA user_version
```

What: reads the schema version. 0 is a new file, 1 is current, anything else stops
the server: "this code knows 1 and has no migrations" (`db.py:92-97`). After S4 to S7
it is read again to check `schema.sql` set 1 (`db.py:99-103`). Alternative: a
`schema_version` table. Why not: see the table above.

**S4** (`schema.sql:13-22`)

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,   -- session_id, as sent in session.started
    started_at  TEXT NOT NULL,      -- UTC wall clock, 'YYYY-MM-DD HH:MM:SS.SSS'
    ended_at    TEXT,               -- same format; NULL while live, or if the server died
    persona     TEXT NOT NULL,      -- a key of [personas]
    mode        TEXT NOT NULL CHECK (mode IN ('vad', 'ptt')),
    -- client_end: session.end; disconnect: socket closed without it;
    -- error: the server's session loop raised. NULL while live.
    end_reason  TEXT CHECK (end_reason IN ('client_end', 'disconnect', 'error'))
) STRICT;
```

What: one row per connection. `IF NOT EXISTS` makes every start after the first do
nothing. `CHECK` limits `mode` and `end_reason` to the values the code uses.
Alternative: no `CHECK`, values checked only in Python. Why not: a typo in the code
would be stored and only show up later as a strange group in the statistics.

**S5** (`schema.sql:24-55`)

```sql
CREATE TABLE IF NOT EXISTS turns (
    id                     TEXT PRIMARY KEY,  -- turn_id
    session_id             TEXT NOT NULL REFERENCES sessions(id),
    turn_index             INTEGER NOT NULL,  -- 1, 2, 3 ... within the session
    -- replied: the reply played to the end (or was sent, if text only).
    -- cut: a barge-in stopped it (by speech or by a ptt press).
    -- empty: nothing to answer (too short, an empty press, no words heard).
    -- failed: error_code says why. closed: the socket closed mid-turn.
    outcome                TEXT NOT NULL
                           CHECK (outcome IN ('replied', 'cut', 'empty', 'failed', 'closed')),
    -- What the model was asked to answer: this turn's transcript, after any
    -- words carried from a cut turn. NULL: no reply started.
    user_text              TEXT,
    -- Script of user_text and of the reply's first chunk, by vaani/language.py:
    -- 'hi' = has Devanagari, 'en' = none. A script, not a language: romanized
    -- Hinglish is 'en'. NULL when there is no text (or no speech, for replies).
    user_script            TEXT CHECK (user_script IN ('hi', 'en')),
    reply_script           TEXT CHECK (reply_script IN ('hi', 'en')),
    reply_generated        TEXT,  -- every delta the model sent, up to a cut
    reply_heard            TEXT,  -- what went into history; NULL if nothing did
    llm_provider           TEXT,  -- [llm].provider_order name that answered
    llm_model              TEXT,  -- the model the provider reported
    error_code             TEXT,  -- ASR_FAILED, LLM_FAILED, TTS_FAILED, INPUT_REJECTED
    -- Milliseconds between two perf_counter spans (vaani/telemetry.py).
    -- NULL: one of the two never happened (not measured).
    end_to_asr_ms          REAL,  -- speech_end -> asr_final
    asr_ms                 REAL,  -- asr_start -> asr_final
    llm_first_token_ms     REAL,  -- llm_request -> llm_first_token
    tts_first_chunk_ms     REAL,  -- tts_start -> tts_first_audio
    end_to_first_audio_ms  REAL,  -- speech_end -> tts_first_audio
    UNIQUE (session_id, turn_index)
) STRICT;
```

What: one row per turn, with five timings as columns. Alternative: one row per
stage (a `stages` table: turn id, stage name, milliseconds). Why not: every turn
would need several inserts, and every statistic a `GROUP BY` or pivot. With five
fixed stages, columns are simpler to write and to read. A new stage costs a schema
change and a version bump (`schema.sql:8`).

**S6** (`schema.sql:57`)

```sql
CREATE INDEX IF NOT EXISTS turns_by_session ON turns(session_id);
```

What: an index, a sorted lookup structure, so finding one session's turns does not
scan the whole table. Alternative: no separate index. Honest note: SQLite already
builds an index for the `UNIQUE (session_id, turn_index)` constraint, and its first
column is `session_id`, so that index can serve the same lookups. This is SQLite's
general behaviour; we did not check it on our file with `EXPLAIN QUERY PLAN`, and no
query was timed with or without `turns_by_session`.

**S7** (`schema.sql:59`)

```sql
PRAGMA user_version = 1;
```

What: stamps the file as schema version 1. Alternative: a version row in a table.
Why not: see S3.

**S8** (`db.py:43-46`, queued by `turn_log.py:88-95`)

```sql
INSERT INTO sessions (id, started_at, persona, mode) VALUES (:id, :started_at, :persona, :mode)
```

When: at `session.start`, when the pipeline builds the turn log (`turns.py:148-152`).
Only for sessions that can reply. `ended_at` and `end_reason` stay NULL until S10.
Alternative: `INSERT OR REPLACE`. Why not: it would silently replace a row if an id
ever repeated; a plain `INSERT` fails and the writer logs it (`db.py:165-168`).

**S9** (`db.py:50-60`, queued by `turn_log.py:137-174`). The code builds the
placeholder list from the column list (`db.py:56-60`); the full string is:

```sql
INSERT INTO turns (id, session_id, turn_index, outcome, user_text, user_script, reply_script, reply_generated, reply_heard, llm_provider, llm_model, error_code, end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, end_to_first_audio_ms) VALUES (:id, :session_id, :turn_index, :outcome, :user_text, :user_script, :reply_script, :reply_generated, :reply_heard, :llm_provider, :llm_model, :error_code, :end_to_asr_ms, :asr_ms, :llm_first_token_ms, :tts_first_chunk_ms, :end_to_first_audio_ms)
```

When: the moment a turn is over, which is always a state move: to `idle` (outcome
`replied`, `failed` or `empty`) or to `cancelling` (outcome `cut`)
(`turn_log.py:97-115`, hooked into `turn_state.py:78-80`). A turn still live when the
socket closes is written with outcome `closed` (`turn_log.py:117-122`). Alternative:
insert the row when the turn opens and `UPDATE` it as each stage finishes. Why not:
writes would happen between the end of speech and the first audio, the measured path;
and a crash would leave half-filled rows. Ours is built after the first audio, so it
is never on that path (`turn_log.py:11-12`).

**S10** (`db.py:47-49`, queued by `turn_log.py:123-129`)

```sql
UPDATE sessions SET ended_at = :ended_at, end_reason = :end_reason WHERE id = :id
```

When: once, when the connection ends, after any `closed` turn row. Alternative: write
the whole session row only at the end. Why not: its turns would reference a row that
does not exist yet, which S2 makes an error; and a server crash would lose the session
entirely.

**S11** (`scripts/turn_stats.py:47-65`). The `WHERE` part is added only for the
filters given. With all three:

```sql
SELECT t.outcome, t.end_to_asr_ms, t.asr_ms, t.llm_first_token_ms, t.tts_first_chunk_ms, t.end_to_first_audio_ms FROM turns t JOIN sessions s ON s.id = t.session_id WHERE date(s.started_at, 'localtime') = :date AND t.session_id = :session AND s.mode = :mode
```

When: run by hand. The file is opened read-only (`mode=ro`, `turn_stats.py:72-73`).
`'localtime'` turns the stored UTC time into this machine's date. The p50 and p95 are
then computed in Python (`turn_stats.py:88-90`). Alternative: compute them in SQL.
Why not: SQLite has no percentile function we can count on, so it would take window
functions to imitate the nearest-rank rule, a second copy of the p95 rule that already
lives in `telemetry.py:93` and that `turn_stats.py` imports.

### What the database deliberately does not do

- **It never reads history back into a conversation.** The model's context is
  `Session.history`, a list in memory, last 6 exchanges (`session.py:59-62`,
  `[llm].history_turns`). Only `turn_stats.py` reads the file (`schema.sql:2-3`).
  Why: no disk read on the turn path, and a new session always starts clean.
- **It stores no audio** (`config.toml:358-360`). Why: 30 s of audio is about 1 MB
  (`config.toml:89-90`); text and numbers are enough for latency statistics; and audio
  is the most personal data. The file holds what users said, so `backend/data/` is
  gitignored (`config.toml:365-366`).
- **No migrations, no deletes, no retention limit.** A file with another schema
  version stops the server (`db.py:93-97`). Rows are only ever inserted, and one
  `UPDATE` per session.
- **It never stops a turn.** A failed write is logged (the error, never the row) and
  lost (`db.py:165-168`); building a row cannot raise into the turn
  (`turn_log.py:105-115`).

## 5. Why this whole stack and not another one

Free-only is a hard constraint for this project. Numbers for the other stacks were
not measured by us; where a cell says "not measured", it means exactly that.

| | Ours | Pipecat or LiveKit Agents (voice agent frameworks) | All hosted: Deepgram ASR + ElevenLabs TTS | Fully local, with a local LLM |
|---|---|---|---|---|
| Control over turn-taking | Full: our endpointer, barge-in judge, state machine and push-to-talk (`endpoint.py`, `barge_in.py`, `turn_state.py`, `ptt.py`) | The framework's own turn and interruption logic; we would configure it rather than own it | As ours, if we keep our gateway; only the ASR and TTS stages change | As ours |
| Cost | Free: VAD, ASR and TTS run locally; the LLM runs on Groq's free tier, with Gemini as failover; a cap of 200 requests per process (`spend.py`) | The frameworks are open source; cost depends on the services plugged in | Paid per use beyond any trial credit: breaks free-only | Free in money |
| Latency | Last measured whole turn, last voice to first audio frame sent: **p50 3958 ms**, 12 turns, cuda/large-v3, Groq `qwen/qwen3.8-27b` (`docs/findings/groq-primary/compare_primaries_20261008-110611.txt`). Of that, 3080 ms is up to `transcript.final`. Today's Groq model is `openai/gpt-oss-20b`, about 330 ms slower to first token (`config.toml:221-225`); the whole turn has not been re-measured with it | Not measured | Not measured. Streaming recognition could remove the wait for a whole-utterance decode, at the cost of a network hop per stage | Not measured. The model's first token would depend on our own hardware |
| Hardware | CPU by default; Hinglish needs `large-v3` on a GPU (`config.toml:138-144`) | Depends on the services used | Little: a browser and a small server | A GPU-class machine for the LLM, shared with Whisper `large-v3` on a laptop |
| What I learn | WebSockets, async code, cancellation, state machines, VAD, SQL: each built and explainable | How to configure a framework; the hard parts live inside it | How to call APIs; less of the pipeline is ours | As ours, plus serving a model |

Also: a framework or a vendor SDK would bring vendor code into the turn path, which
`CLAUDE.md` forbids outside `providers/`, `asr/` and `tts/`.

## 6. Known costs of these choices

These are the prices we pay for the choices above. Open problems and their
measurements are listed in [`PROJECT.md`, "Known gaps on dev"](PROJECT.md#known-gaps-on-dev);
they are not repeated here.

| Cost | Comes from | Number or source |
|---|---|---|
| Recognition starts only after the turn ends, on the whole utterance | Whisper has no streaming mode (`asr/base.py:12-13`) | Whisper decode p50 2066 ms on cuda/large-v3 inside a measured turn (`compare_primaries_20261008-110611.txt`); 1330 ms p50 on cpu/small on short clips (`docs/findings/perf-1-latency-budget.md:19`) |
| About 900 ms of silence before a hands-free turn even ends | VAD's 200 ms plus the endpointer's 700 ms (`config.toml:67-72`) | 704 ms p50 for the endpointer wait (`perf-1-latency-budget.md:107`) |
| A decode cannot be stopped once CTranslate2 is inside it | CTranslate2 (`asr/whisper.py:15-17`) | `timeout_s` bounds the wait, not the thread (`config.toml:126-128`); the session's next decode waits for the old one (`asr/runner.py:187-196`) |
| A cancelled chunk of speech runs to its end on its thread | Piper synthesises a sentence at once (`tts/piper.py:12-17`) | Its audio is thrown away, never sent |
| The Hindi voice cannot read Latin script | Piper's Hindi voices read Latin letters with English spelling rules (`config.toml:417-421`) | Replies must be all Devanagari; English needs a second voice per persona; Latin words are logged (`speaker.py:121-133`) |
| cpu/small cannot transcribe Hinglish | The committed CPU default (`config.toml:138-141`) | Hinglish needs a local GPU override |
| "What the user heard" and "playback finished" are estimates | The server cannot hear the browser (`barge_in.py:135-137`, `speaker.py:11-16`) | Not measured against a real browser |
| Nothing checks the protocol version at runtime | Versioning lives in documents only (2e) | |
| Errors do not say which turn they belong to | `error` has no `turn_id` (`protocol.py:195-200`) | A late `ASR_FAILED` of a cut turn shows as a banner (`PROJECT.md` known gaps) |
| Everything lives in one process | History, request cap and pipelines are in memory (`session.py:59-62`, `spend.py:22-27`) | A restart forgets conversations and resets the cap |
| Licences | piper-tts GPL-3.0-or-later; Hindi voices non-commercial | `versions.md:107-110`, `config.toml:286-287`; not checked for our distribution case |

## 7. Likely viva questions

1. **Why a WebSocket and not plain HTTP?** Audio flows both ways all the time and the
   server must speak first (`audio.flush`, `turn.state`). HTTP is request then answer;
   polling adds a wait to every message (2e).
2. **Why is audio binary and not JSON?** Base64 makes it about 33% bigger and costs an
   encode and decode 50 times a second. Control stays JSON because it is small and
   easy to validate (2e).
3. **Why is `audio.flush` sent before `turn.state cancelling`?** The user judges the
   interruption by when the speaker goes quiet, so silence goes first; the token is
   set even before that, so no frame can follow (`barge_in.py:178-182`).
4. **What happens to frames of a turn after it is flushed?** The server sends none: the
   token is checked before every send (`speaker.py:160-164`). The browser drops any
   that still arrive, by `turn_id` (`turnFilter.js:38-49`).
5. **Binary frames carry no `turn_id`. How does the browser know whose they are?**
   They belong to the turn of the latest `audio.start` (`turnFilter.js:43-47`).
6. **What if the browser sends `ptt.start` in a hands-free session?** `BAD_MESSAGE`,
   and the session carries on in hands-free mode (`gateway.py:273-276`).
7. **Why is `ptt.end` sent only after the worklet's last frame?** The end of the speech
   is still inside the worklet. Messages on one socket keep their order, so sending
   `ptt.end` after the last frame means the server has the whole press (`pttPress.js`,
   `contracts.md` 2.8). If the worklet stalls, it is sent after 300 ms anyway.
8. **Where is the protocol version checked at runtime?** Nowhere. `contracts.md` is the
   source of truth; nothing on the wire carries the version (2e).
9. **What happens if Groq is down?** Before the first word, a rate limit, timeout or
   outage fails over to Gemini; after the first word, the error is raised and the
   user gets `LLM_FAILED` (`providers/chain.py:1-17,48`).
10. **What if Whisper takes longer than 5 s?** `ASR_FAILED`, then `idle`. The decode
    keeps its thread until it finishes, and the session's next decode waits for it
    (`asr/runner.py:187-196`).
11. **Why SQLite and not Postgres?** One machine, a few rows a minute: a server to run
    and a driver to add would buy nothing (section 4).
12. **Why is a turn's row written at the end and not as it goes?** So no write ever
    happens between the end of speech and the first audio, and no row is half-filled
    (S9).
13. **Why compute p95 in Python?** SQLite has no percentile function we can rely on,
    and the p95 rule already exists once in `telemetry.py:93` (S11).
14. **Why not Pipecat or LiveKit Agents?** Turn-taking would be the framework's, not
    ours, and we must be able to explain and time every step (section 5).
15. **Why Piper and not a hosted voice?** No network hop and no cost on every chunk;
    the price is the Hindi voice's trouble with Latin script (sections 3 and 6).
