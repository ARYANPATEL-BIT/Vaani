# Vaani: the whole system, as it is on `dev`

This file describes the code on `dev` as it is today (after
`feat/database`). It is built from the code, not from older learning
documents. If this file and the code disagree, the code is right and this file
needs fixing. Every PR that changes the flow, the stack or the database updates
this file in the same PR.

## a. The project in 5 lines

1. Vaani is a voice agent: you speak Hindi, English or a mix of both (Hinglish) in a browser and it answers out loud.
2. The browser streams the microphone to a Python server over one WebSocket (a connection that stays open so both sides can send at any time).
3. The server detects speech, decides when you have finished, transcribes it, asks a hosted language model for a reply and speaks the reply with a local voice.
4. You can interrupt it (barge-in): once 200 ms of your speech is heard over it, it goes silent and listens to you. In push-to-talk mode (section d2) you press "speak" and "stop" instead, and a press interrupts it.
5. Every session and turn is recorded in a SQLite file (section f), for latency statistics; nothing reads it back into a conversation. The studio in the spec (cloned voice, lip-synced video) is not built yet.

## b. The stack

| Component | Library or model | What it does | Why this one | One alternative and why not |
|---|---|---|---|---|
| WebSocket server | FastAPI on uvicorn (`backend/vaani/app.py`, `gateway.py`) | Serves `/ws/session` and `/health`; one coroutine owns each connection | Async, so one process can read audio from many sockets while it waits on the network | Flask: synchronous, a poor fit for long-lived real-time sockets |
| Voice activity detection (VAD) | Silero VAD v6.2.3, ONNX file run with onnxruntime on CPU (`vad.py`) | Says, for each 20 ms frame, whether it holds speech, and turns that into `speech_started` / `speech_ended` | A small neural model, accurate on noise, no PyTorch needed | WebRTC VAD: fast, but marks much noise and music as speech |
| Endpointing | Our own rule, counted in frames (`endpoint.py`) | Decides the user's turn is over after 700 ms of silence following `speech_ended` | No timers and no I/O, so it is exact in tests and safe in the hot path | Semantic endpointing (a model reads the words): needs a transcript first and usually a network call, which is banned in the endpointing hot path |
| Push-to-talk turns (protocol v0.9) | Our own press buffer (`ptt.py`), used instead of endpointing when `session.start` says `"mode": "ptt"` | Keeps the frames between `ptt.start` and `ptt.end` and counts the voiced ones, so an empty press is dropped before Whisper | No wait at all: the stop press ends the turn | Drive the `Endpointer` with fake events: three special cases inside endpointing (ignore VAD's own end, no pre-roll, the cap's reopen) |
| Speech recognition (ASR) | faster-whisper (Whisper weights on CTranslate2); committed default `small` / `cpu` / `int8` (`asr/whisper.py`) | Turns each finished utterance into text, on its own thread pool | Several times faster than the original Whisper and needs no PyTorch | The original PyTorch Whisper: slower and pulls in PyTorch |
| LLM providers | Groq `openai/gpt-oss-20b` first, Gemini `gemini-3.5-flash-lite` as failover, both over REST with httpx (`providers/`) | Streams the reply text; fails over to the next provider only before the first word | Plain HTTP lets us close the stream ourselves on a barge-in; vendors stay config values | The vendors' Python SDKs: they hide the HTTP stream, so we could not be sure a cancel closes the connection |
| Chunking | Our own clause chunker (`chunker.py`) | Cuts the streaming reply into pieces to speak: the first piece at the earliest sentence or clause end, later ones at sentence ends | Speech starts while the model is still writing | Cut by time ("no token for N ms"): a model pauses mid-sentence for its own reasons and the cut would split a phrase |
| Speech synthesis (TTS) | Piper (espeak-ng plus a VITS network on onnxruntime), local CPU (`tts/piper.py`, `speaker.py`) | Turns each chunk into audio, on a shared thread pool | Local: no network round trip and no per-call cost on every chunk | A hosted voice (ElevenLabs, Sarvam): adds a network hop and a cost to every chunk |
| Voices | Piper voices from a pinned `piper-voices` revision; per persona, one Hindi and one English (`[tts.piper.voices]` in `config.toml`, `language.py`) | The reply's first chunk picks the voice by script: any Devanagari is Hindi, none is English; the voice is then kept for the whole reply | The script is what the voice has to read; checking it costs nothing | One multilingual voice (XTTS): a larger model meant for cloning, never measured on the reply path |
| Frontend audio capture | Web Audio `AudioWorklet` (`frontend/public/audio-processor.js`, `src/hooks/useAudioCapture.js`) | Takes the mic at 16 kHz, builds 20 ms frames of 16-bit PCM, sends them as binary WebSocket messages | Runs on the audio thread, so UI work cannot drop audio | `ScriptProcessorNode`: runs on the main UI thread, drops frames under load, and is deprecated |
| Frontend playback | Web Audio scheduling on the `AudioContext` clock (`src/hooks/usePlaybackQueue.js`) | Plays each received frame right after the previous one, at the rate `audio.start` declared | The audio clock is steady whatever JavaScript is doing, so there are no gaps | `setTimeout` timers: fire late when the page is busy, which makes audible gaps |
| Frontend enrolment (PR #41) | `MediaRecorder` and an `AnalyserNode` level meter (`src/pages/EnrolConsentPage.jsx`, `EnrolRecordPage.jsx`, `src/hooks/useReferenceRecorder.js`) | At `/enrol` the user consents; at `/enrol/record` they record a reference voice of 30 to 60 s. The clip stays in browser memory: nothing uploads it and no backend endpoint exists for it yet | `MediaRecorder` encodes the clip into a file (Opus/WebM, or what the browser supports) with no code of ours | Reuse the conversation's `AudioWorklet` capture: it gives raw 16 kHz PCM, which we would have to package into a file ourselves, for a cloning step whose input format is not decided |
| Database | SQLite 3.45 through Python's standard `sqlite3`, raw SQL, WAL mode (`backend/vaani/db.py`, `schema.sql`, `turn_log.py`) | Records one row per session and one per turn (text, outcome, provider, five timings); never audio, never read back into a conversation. One writer thread owns the connection; the event loop only queues rows. `scripts/turn_stats.py` prints count, p50 and p95 per stage | A single file inside our own process: no server, no new dependency | PostgreSQL: a server to install and run, and a driver dependency, for a few rows a minute on one machine |
| Testing | pytest with fakes for ASR, TTS and HTTP (`backend/tests/`); real Whisper only under `pytest -m slow`; frontend: plain Node test scripts (`npm test`) | Checks every stage without models, keys or network | The default run is fast and needs nothing downloaded | Real models in every test: a few hundred MB of download and seconds of CPU per test |
| CI | GitHub Actions: ruff and pytest on every PR into `dev` or `main` (`.github/workflows/ci.yml`), slow ASR tests in `asr-slow.yml` | Installs the exact locked versions (`uv sync --frozen`), fetches the default persona's voices, lints, tests | Every PR is checked the same way on a clean machine | Slow ASR tests in every PR: they run only when ASR code, config or dependencies change, because of the model download and CPU time |

There is no CI job for the frontend.

## c. One turn, end to end

From the user's voice in the mic to the agent's voice in the speaker. "Turn"
means one user utterance; its `turn_id` is made when speech starts, and the
transcript, the reply text and the reply audio all carry it.

0. **Server start.** File: `backend/vaani/app.py`. What: loads the Silero model (checks its sha256), loads and warms up Whisper, builds the provider chain (refuses to start if a listed provider has no API key) loads every persona's two Piper voices, and opens the SQLite database (`db.py`): a file that cannot be opened stops the server, naming `[db].enabled = false`; then starts the one database writer thread. When: once, when the server starts; every session shares these. Database query (`db.py`, `open_db`): `PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`, `PRAGMA user_version` (must be 0 or 1), then all of `vaani/schema.sql`: `CREATE TABLE IF NOT EXISTS sessions (...)`, `CREATE TABLE IF NOT EXISTS turns (...)`, `CREATE INDEX IF NOT EXISTS turns_by_session ON turns(session_id)`, `PRAGMA user_version = 1`.
1. **Connect.** File: `frontend/src/hooks/useAudioCapture.js`, called from `src/pages/ConversationPage.jsx`. What: asks for the mic with echo cancellation, noise suppression and auto gain on, opens an `AudioContext` at 16 kHz, loads the worklet, opens the WebSocket to `/ws/session` and sends `session.start` with the persona and the audio format. When: the user clicks Start Conversation. Database query: none.
2. **Session start.** File: `backend/vaani/gateway.py`. What: checks the audio format matches `config.toml` and the persona is a key of `[personas]`, then creates the `Session` (`session.py`), its `Telemetry` and its `TurnPipeline` (`turns.py`) with the persona's voices and its `TurnLog` (`turn_log.py`), and replies `session.started`. When: once per connection. Database query (queued by `TurnLog.__init__`, `turn_log.py`; run by the writer thread): `INSERT INTO sessions (id, started_at, persona, mode) VALUES (:id, :started_at, :persona, :mode)`.
3. **Capture.** File: `frontend/public/audio-processor.js`, then `useAudioCapture.js`. What: the worklet collects samples into 320-sample frames, converts them to 16-bit little-endian PCM (640 bytes) and hands each to the page, which sends it as a binary message. When: every 20 ms, from `session.started` until disconnect. Database query: none.
4. **Ingest.** File: `gateway.py`. What: checks a session exists and the frame is exactly the size config implies, counts it and passes it to `TurnPipeline.on_frame`. When: every frame. Database query: none.
5. **VAD.** File: `vad.py`, called from `turns.py`. What: converts the frame to floats, runs Silero each time 512 samples have built up, and applies hysteresis: 4 speech frames in a row give `speech_started`, 10 silent frames give `speech_ended`. When: every frame, on the event loop. Database query: none.
6. **Turn opens.** Files: `endpoint.py`, `turns.py`, `session.py`, `turn_state.py`. What: on `speech_started` while the agent is idle, the endpointer opens an utterance (with 300 ms of audio from before speech began, so the first syllable is kept), the session makes a new `turn_id`, and the state machine moves to `listening` and sends `turn.state`. When: the first frame VAD calls speech. Database query: none.
7. **Endpointing.** File: `endpoint.py`, then `turns.py`. What: after `speech_ended` it waits 700 ms of silence, counted in frames; speech resuming cancels the wait. Too little voiced audio is discarded as a cough; 30 s forces an end. When the turn ends, `turns.py` records the `turn_ended` and `speech_end` spans (`speech_end` is when VAD's `speech_ended` fired: the start of the row's two end-to-end timings), moves to `thinking` and asks ASR for the final transcript. When: every frame while an utterance is open. Database query: none.
8. **Transcription.** Files: `asr/runner.py`, `asr/whisper.py`. What: the runner queues the job and a background task runs it; Whisper decodes on its own thread pool (forced to Hindi, with a romanized Hinglish prompt, one decode, no retries). It sends `transcript.final`, or `ASR_FAILED` after `timeout_s`, and hands the text back to `turns.py`. Partial transcripts are off in config. When: right after the turn ends, off the frame loop. Database query: none.
9. **Reply starts.** Files: `turns.py`, `reply.py`. What: joins any words carried from an interrupted turn (section d) with the new transcript and starts a background reply with its own cancellation token (an `asyncio.Event` that a barge-in sets). When: as soon as the transcript arrives. Database query: none.
10. **Guardrail and prompt.** File: `persona.py`, called from `reply.py`. What: checks the raw transcript against the `[guardrail]` patterns (a match sends `INPUT_REJECTED` and goes idle), then builds the request: persona system prompt, the session's history, this transcript. When: once per reply, before any network call. Database query: none.
11. **Language model.** Files: `providers/chain.py`, `gemini.py`, `groq.py`, `streaming.py`, `spend.py`. What: the request cap is checked before each paid request; the chain streams from Groq, and fails over to Gemini only on a rate limit, timeout or outage, and only before the first word. Each piece of text is sent to the browser as `agent.text`. When: during `thinking`, as the model writes. Database query: none.
12. **Chunking.** File: `chunker.py`, called from `reply.py`. What: the first chunk is cut at the earliest sentence end or comma (or a conjunction once it has 8 characters, or the last space at 60); later chunks wait for a sentence end. When: on every piece of text. Database query: none.
13. **Synthesis.** Files: `speaker.py`, `language.py`, `tts/piper.py`. What: the first chunk picks the Hindi or English voice by script and locks it for the reply; Piper synthesises the chunk on a thread. On the first audio the state moves to `speaking` and `audio.start` declares the voice's sample rate; the audio goes out as binary frames of 20 ms at that rate. The cancellation token is checked before every send. When: each chunk, while the model is still writing. Database query: none.
14. **Playback.** Files: `ConversationPage.jsx`, `usePlaybackQueue.js`, `useTranscript.js`, `TranscriptView.jsx`. What: `audio.start` sets the playback rate; each frame becomes an audio buffer scheduled right after the previous one on the `AudioContext` clock; the browser resamples to the speaker's rate. The reply text appears as `agent.text` arrives. When: as frames arrive. Database query: none.
15. **Turn ends.** Files: `reply.py`, `speaker.py`, `session.py`, `turn_state.py`, `turn_log.py`. What: sends `agent.done` and `audio.end`, stays `speaking` until the audio should have finished playing (an estimate), then stores the exchange in history and moves to `idle`. When: after the last chunk. Database query (on the move to `idle`, `TurnLog.state_changed`, called inside `TurnStateMachine.move_to`; run later by the writer thread): `INSERT INTO turns (id, session_id, turn_index, outcome, user_text, user_script, reply_script, reply_generated, reply_heard, llm_provider, llm_model, error_code, end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, end_to_first_audio_ms) VALUES (:id, :session_id, ...)`, with outcome `replied`, the five timings from this turn's spans.

16. **Session ends.** Files: `gateway.py`, `turns.py` (`close`), `turn_log.py` (`session_closed`). What: the gateway decides the end reason (`client_end` after `session.end`, `disconnect` when the socket just closes, `error` if the session loop raised); `close` stops every reply, then a turn still live is recorded as `closed`. When: once, when the connection ends. Database query: (only if a turn was live) the `INSERT INTO turns` of step 15 with outcome `closed`; then `UPDATE sessions SET ended_at = :ended_at, end_reason = :end_reason WHERE id = :id`. At server shutdown the writer gets `[db].close_timeout_s` (2 s) to finish its queue, then logs how many rows were not written.

Failures end the same way: an `error` message (`ASR_FAILED`, `LLM_FAILED`,
`TTS_FAILED` or `INPUT_REJECTED`), then `turn.state idle`. The browser shows the
code in a banner. The move to `idle` queues the same `INSERT INTO turns` as step 15, with outcome `failed` and `error_code` set (or `empty` when there was nothing to answer: too short, or the recogniser heard no words).

## d. Barge-in, end to end

The user talks while the agent is `thinking` or `speaking`.

1. **Routing.** File: `turns.py`. What: while the agent is busy, every frame goes to the barge-in judge instead of the endpointer. When: every frame during `thinking` or `speaking`. Database query: none.
2. **Judging.** File: `barge_in.py`. What: after `speech_started`, it counts frames whose speech probability reaches `[barge_in].threshold`, starting from VAD's 4; at `min_speech_ms` (200 ms) it is an interruption. A `speech_ended` first means it was a noise and the reply goes on. All frames since speech began are held. When: every frame of that speech. Database query: none.
3. **Stop.** Files: `barge_in.py`, `reply.py`, `session.py`. What: records the `barge_in` span, sets the reply's cancellation token (no more audio can be sent after this line), marks the turn flushed and sends `audio.flush` as the first message out. When: the frame that decides it. Database query: none.
4. **Upstream stops.** Files: `providers/streaming.py`, `speaker.py`, `tts/piper.py`, `asr/runner.py`. What: the model's HTTP stream is closed at once, even mid-wait; the speaker sends nothing more; a Piper synthesis already running finishes on its thread and its audio is thrown away. A transcript still being made is kept and carried into the next reply. When: right after the token is set. Database query: none.
5. **Browser stops.** Files: `useAudioCapture.js`, `usePlaybackQueue.js`, `ConversationPage.jsx`. What: on `audio.flush` it fades every scheduled sound to zero in 10 ms, stops them, resets the queue, replies `flush.ack` and marks the agent's text as interrupted. When: when `audio.flush` arrives. Database query: none.
6. **What was heard.** File: `barge_in.py` (`heard_text`), using `speaker.py`'s play-out estimates. What: estimates how much of the reply had played and records only that part in history. If nothing was heard, the user's words are carried and answered together with what they say next. When: during the stop, before the new turn opens. Database query: none.
7. **New turn.** Files: `turns.py`, `turn_state.py`. What: moves to `cancelling`, then `listening` with a new `turn_id`, and replays the held frames into the endpointer, so the new turn starts at the user's first sound. From here it is a normal turn (section c, step 7). If the new speech is too short to be a turn but words were carried, those words are answered. When: straight after the stop. Database query (on the move to `cancelling`, `TurnLog.state_changed`): `INSERT INTO turns (id, session_id, turn_index, outcome, user_text, user_script, reply_script, reply_generated, reply_heard, llm_provider, llm_model, error_code, end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, end_to_first_audio_ms) VALUES (:id, :session_id, ...)` for the CUT turn, with outcome `cut`, `reply_heard` = the heard part (NULL if nothing was heard), and only the timings stamped before the cut.
8. **Ack.** File: `session.py`. What: `flush.ack` is matched to the flushed turn and the round trip is logged (`flush_acked` span). When: when the ack arrives, usually after the new turn is current. Database query: none.

## d2. Push-to-talk (protocol v0.9)

Sections c and d are the hands-free mode (`"vad"`). A session can instead be
push-to-talk (`"ptt"`). The protocol details are in `contracts.md` section 2.8.

**The mode switch.** File: `gateway.py`, then `session.py` and `turns.py`. What: `session.start` may carry `"mode": "ptt"` (default `"vad"`). The gateway stores it on the `Session` and `session.started` sends it back. `TurnPipeline` then builds a `PttBuffer` (`ptt.py`) in place of the `Endpointer`, so endpointing and the speech-judged barge-in never run in that session. A second `session.start` changes nothing. `ptt.start` or `ptt.end` in a vad session gets `BAD_MESSAGE`. When: once, at `session.start`. Database query: the `INSERT INTO sessions` of section c step 2, with `mode` = `'ptt'`.

One ptt turn (where it differs from section c):

1. **Speak pressed.** Files: browser (not built yet), `gateway.py`, `turns.py` (`on_ptt_start`), `vad.py`, `ptt.py`. What: the browser sends `ptt.start` and only then starts sending mic frames. The server opens a turn (`listening`, new `turn_id`), wipes Silero's memory of the previous press (`VadStream.reset`) and opens the press. A second `ptt.start` while pressed is ignored. When: on the press. Database query: none.
2. **While pressed.** Files: `turns.py` (`on_frame`), `vad.py`, `ptt.py`. What: every frame runs through Silero; `PttBuffer` keeps it and counts it voiced if its speech probability reaches `[vad].threshold`. Silence does not end the turn. A press that reaches `max_utterance_ms` (30 s) ends as if stop were pressed. Frames with no press open are dropped. When: every frame of the press. Database query: none.
3. **Stop pressed.** Files: browser, `gateway.py`, `turns.py` (`on_ptt_end`, `_release`), `ptt.py`. What: the browser sends its last frame, then `ptt.end`. The press closes at once. Fewer voiced frames than `[endpoint].min_utterance_ms` means an empty press: `_discard_turn`, then `idle` with no transcription. Otherwise `_end_turn` records `turn_ended` and moves to `thinking`, and steps 8 to 15 of section c run unchanged. `ptt.end` with no press open is ignored. When: on the stop press. Database query: for an empty press, on the move to `idle`, `INSERT INTO turns (id, session_id, turn_index, outcome, user_text, user_script, reply_script, reply_generated, reply_heard, llm_provider, llm_model, error_code, end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, end_to_first_audio_ms) VALUES (:id, :session_id, ...)` with outcome `empty` and no timings; otherwise none here (section c step 15 writes the row; `end_to_asr_ms` and `end_to_first_audio_ms` start at this `ptt.end`).
4. **Socket closed mid-press.** File: `turns.py` (`close`), `ptt.py`. What: the press's audio is thrown away and logged; nothing is transcribed. When: on disconnect. Database query (`TurnLog.session_closed`): `INSERT INTO turns (id, session_id, turn_index, outcome, user_text, user_script, reply_script, reply_generated, reply_heard, llm_provider, llm_model, error_code, end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, end_to_first_audio_ms) VALUES (:id, :session_id, ...)` with outcome `closed`, then `UPDATE sessions SET ended_at = :ended_at, end_reason = :end_reason WHERE id = :id`.

One ptt interruption:

1. **Speak pressed while the agent is busy.** Files: `turns.py` (`on_ptt_start`, `_interrupt`). What: in `thinking` or `speaking`, `ptt.start` is a barge-in at once, with no speech judging. When: on the press. Database query: none.
2. **Stop the reply.** Files: `barge_in.py` (`stop_reply`), `reply.py`, `session.py`. What: exactly steps 3, 4 and 6 of section d: the reply's token is set, `audio.flush` is the first message out, the model stream closes, synthesis in flight is discarded, history keeps what was heard (or the words are carried). When: straight after the press. Database query: none.
3. **New turn.** Files: `turns.py`, `turn_state.py`, `vad.py`, `ptt.py`. What: `cancelling`, then `listening` with a new `turn_id`; VAD is reset and the press opens. From here it is a ptt turn (above, step 2). An empty press after a cut that the user heard none of answers the cut question (`thinking`, later `idle`), as in hands-free mode. When: straight after the stop. Database query (on the move to `cancelling`): `INSERT INTO turns (id, session_id, turn_index, outcome, user_text, user_script, reply_script, reply_generated, reply_heard, llm_provider, llm_model, error_code, end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms, end_to_first_audio_ms) VALUES (:id, :session_id, ...)` for the cut turn, outcome `cut`, as in section d step 7.

## e. Where the conversation context lives today

- **Where:** `Session.history` in `backend/vaani/session.py`: a list in the server's memory, one per WebSocket connection. Nothing is shared between sessions. The database (section f) keeps a RECORD of every turn on disk, but nothing ever reads it back into a conversation: the context is this list only.
- **What is kept:** the last `history_turns` exchanges (6 in `config.toml`). One exchange is the user's transcript plus what the user heard of the reply: the whole reply if it played to the end, the heard part if it was cut. It is re-sent to the model with every new turn (`persona.py`), after the persona's system prompt. The persona is fixed at `session.start`.
- **Also in memory:** words carried from an interrupted turn (`TurnPipeline` in `turns.py`), until the next reply uses them. The browser's transcript is React state (`useTranscript.js`), cleared on every connect.
- **What is lost, and when:**
  - Exchanges older than the last 6: dropped on the next new exchange, not summarised.
  - A turn that failed (`ASR_FAILED`, `LLM_FAILED`, `TTS_FAILED`) or was blocked (`INPUT_REJECTED`): never stored.
  - Everything: when the socket closes (session end, page closed, network drop) or the server restarts. Reconnecting starts a new, empty session. Its turns stay in the database as rows, unused by the agent.
  - The paid request counter (`spend.py`) is per process: it resets when the server restarts.

## f. Database

SQLite, one file: `[db].path` in `config.toml` (`backend/data/vaani.db`, gitignored).
WAL mode (a write is appended to a side file, so a reader can read while the server
writes). Schema in `backend/vaani/schema.sql`, version 1 in `PRAGMA user_version`.
Every write runs on ONE writer thread (`DbWriter`, `db.py`), in the order queued; the
event loop only queues. A failed write logs a warning (statement and error, never the
row's text) and the writer goes on. `[db].enabled = false` runs without it.

Tables: `sessions` (id, started_at, ended_at, persona, mode, end_reason) and `turns`
(id, session_id, turn_index, outcome, user_text, user_script, reply_script,
reply_generated, reply_heard, llm_provider, llm_model, error_code, and five timings in
ms: end_to_asr_ms, asr_ms, llm_first_token_ms, tts_first_chunk_ms,
end_to_first_audio_ms). Column meanings are in the comments of `schema.sql`.

| Table | Query | Sent from which file | When | Why this query and not another |
|---|---|---|---|---|
| (file) | `PRAGMA journal_mode = WAL`; `PRAGMA foreign_keys = ON`; `PRAGMA user_version` | `db.py` `open_db` | Server start | WAL so `turn_stats.py` can read during writes; foreign keys are off by default in SQLite; the version decides whether the schema is created (0), current (1) or refused |
| sessions, turns | `schema.sql`: `CREATE TABLE IF NOT EXISTS ...`, `CREATE INDEX IF NOT EXISTS turns_by_session ...`, `PRAGMA user_version = 1` | `db.py` `open_db` | Server start | `IF NOT EXISTS` makes every start after the first a no-op; there are no migrations yet |
| sessions | `INSERT INTO sessions (id, started_at, persona, mode) VALUES (...)` | `turn_log.py` `TurnLog.__init__` | `session.start` | One row per connection, written first so its turns can reference it |
| turns | `INSERT INTO turns (id, session_id, turn_index, outcome, ..., end_to_first_audio_ms) VALUES (...)` | `turn_log.py` `TurnLog.state_changed` / `session_closed` | A turn ends: move to `idle` or `cancelling`, or the socket closes mid-turn | Built when the turn is over, so it is never between end of speech and first audio; one INSERT of a finished row, never updated |
| sessions | `UPDATE sessions SET ended_at = :ended_at, end_reason = :end_reason WHERE id = :id` | `turn_log.py` `TurnLog.session_closed` | The connection ends | The end is only known then; one UPDATE of the row inserted at start |
| turns, sessions | `SELECT t.outcome, t.end_to_asr_ms, ... FROM turns t JOIN sessions s ON s.id = t.session_id WHERE ...` (optional `date(s.started_at, 'localtime') = :date`, `t.session_id = :session`, `s.mode = :mode`) | `backend/scripts/turn_stats.py` | Run by hand | Read-only (`mode=ro`); percentiles are computed in Python with the same nearest-rank p95 as `telemetry.py` |

## g. Where the details live

- The WebSocket protocol (every message, field, error code and version): [`docs/contracts.md`](../contracts.md).
- The latency numbers and the budget: [`docs/findings/perf-1-latency-budget.md`](../findings/perf-1-latency-budget.md).
- Every runtime setting, with the reason for its value: `backend/config.toml`.
- How each step was built and why: the per-PR documents in `backend-learning/` and `frontend-learning/`.

## Known gaps on `dev`

- Groq's free tier is shared by everyone using the key; past its limit it answers HTTP 429 and the chain fails over to Gemini. For `openai/gpt-oss-20b` the limits are 1000 requests a day and 8000 tokens a minute; how many turns a minute that allows was not measured (`backend-learning/15c-groq-primary.md`).
- The browser plays any frame that arrives after `audio.flush`; it does not track flushed `turn_id`s as `contracts.md` asks. Today the server sends nothing after the flush, so this has not shown up.
- The backend sends no `telemetry` message, so the frontend's latency panel has nothing to show.
- Seen in the live demo (2026-10-08/09), not measured in a run file: long sentences hit the 5 s ASR timeout (15 s was used, as a local `.env` override only); noise or echo caused false barge-ins that produced short made-up Hindi transcripts.
- After `ASR_FAILED` the pill and the orb stayed on "thinking" (live demo 2026-10-08/09; not reproduced since).
- The orb says "Tap connect to start talking" while connected: it is the subtitle of the connected `idle` state (`frontend/src/components/VoiceOrb/VoiceOrb.jsx`).
- `TTS_FAILED` wipes the reply text already shown: on any `error`, `ConversationPage.jsx` calls `clearActivePartial` (`useTranscript.js`), which drops the streamed reply, and no `agent.done` follows a `TTS_FAILED` to keep it.
- Push-to-talk (v0.9) has no frontend yet: there is no speak/stop button and no mode choice in the UI, so it runs only in `backend/tests/test_ptt.py`. Stop press to first audible sample was not measured.
- Files over the ~300-line limit: `backend/vaani/turns.py` (411), `config.py` (366), `protocol.py` (338), `gateway.py` (319), `reply.py` (309). `turns.py` is to be split in a follow-up PR.
- Database timings: "end of speech" in hands-free mode is VAD's `speech_ended`, which lags the last sound (`perf-1-latency-budget.md`); "first audio" is the first frame sent, not heard. No `measure_turn.py` run has checked the rows against a real turn (`backend-learning/18-database.md`).
- The database writer's queue is unbounded: a stalled disk would hold rows in memory. A row whose write fails is lost (logged as a warning).
- The "hmm after a barge-in" discard works only under a test override (`min_utterance_ms=300` in `test_barge_in.py`); at the default (40) a barge-in's turn always has enough voiced frames, so the "hmm" is answered (`backend-learning/14-tuning.md`).
