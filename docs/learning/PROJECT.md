# Vaani: the whole system, as it is on `dev`

This file describes the code on `dev` as it is today (after
`fix/groq-primary-complete`). It is built from the code, not from older learning
documents. If this file and the code disagree, the code is right and this file
needs fixing. Every PR that changes the flow, the stack or the database updates
this file in the same PR.

## a. The project in 5 lines

1. Vaani is a voice agent: you speak Hindi, English or a mix of both (Hinglish) in a browser and it answers out loud.
2. The browser streams the microphone to a Python server over one WebSocket (a connection that stays open so both sides can send at any time).
3. The server detects speech, decides when you have finished, transcribes it, asks a hosted language model for a reply and speaks the reply with a local voice.
4. You can interrupt it (barge-in): once 200 ms of your speech is heard over it, it goes silent and listens to you.
5. The studio in the spec (cloned voice, lip-synced video) and the database are not built yet.

## b. The stack

| Component | Library or model | What it does | Why this one | One alternative and why not |
|---|---|---|---|---|
| WebSocket server | FastAPI on uvicorn (`backend/vaani/app.py`, `gateway.py`) | Serves `/ws/session` and `/health`; one coroutine owns each connection | Async, so one process can read audio from many sockets while it waits on the network | Flask: synchronous, a poor fit for long-lived real-time sockets |
| Voice activity detection (VAD) | Silero VAD v6.2.3, ONNX file run with onnxruntime on CPU (`vad.py`) | Says, for each 20 ms frame, whether it holds speech, and turns that into `speech_started` / `speech_ended` | A small neural model, accurate on noise, no PyTorch needed | WebRTC VAD: fast, but marks much noise and music as speech |
| Endpointing | Our own rule, counted in frames (`endpoint.py`) | Decides the user's turn is over after 700 ms of silence following `speech_ended` | No timers and no I/O, so it is exact in tests and safe in the hot path | Semantic endpointing (a model reads the words): needs a transcript first and usually a network call, which is banned in the endpointing hot path |
| Speech recognition (ASR) | faster-whisper (Whisper weights on CTranslate2); committed default `small` / `cpu` / `int8` (`asr/whisper.py`) | Turns each finished utterance into text, on its own thread pool | Several times faster than the original Whisper and needs no PyTorch | The original PyTorch Whisper: slower and pulls in PyTorch |
| LLM providers | Groq `openai/gpt-oss-20b` first, Gemini `gemini-3.5-flash-lite` as failover, both over REST with httpx (`providers/`) | Streams the reply text; fails over to the next provider only before the first word | Plain HTTP lets us close the stream ourselves on a barge-in; vendors stay config values | The vendors' Python SDKs: they hide the HTTP stream, so we could not be sure a cancel closes the connection |
| Chunking | Our own clause chunker (`chunker.py`) | Cuts the streaming reply into pieces to speak: the first piece at the earliest sentence or clause end, later ones at sentence ends | Speech starts while the model is still writing | Cut by time ("no token for N ms"): a model pauses mid-sentence for its own reasons and the cut would split a phrase |
| Speech synthesis (TTS) | Piper (espeak-ng plus a VITS network on onnxruntime), local CPU (`tts/piper.py`, `speaker.py`) | Turns each chunk into audio, on a shared thread pool | Local: no network round trip and no per-call cost on every chunk | A hosted voice (ElevenLabs, Sarvam): adds a network hop and a cost to every chunk |
| Voices | Piper voices from a pinned `piper-voices` revision; per persona, one Hindi and one English (`[tts.piper.voices]` in `config.toml`, `language.py`) | The reply's first chunk picks the voice by script: any Devanagari is Hindi, none is English; the voice is then kept for the whole reply | The script is what the voice has to read; checking it costs nothing | One multilingual voice (XTTS): a larger model meant for cloning, never measured on the reply path |
| Frontend audio capture | Web Audio `AudioWorklet` (`frontend/public/audio-processor.js`, `src/hooks/useAudioCapture.js`) | Takes the mic at 16 kHz, builds 20 ms frames of 16-bit PCM, sends them as binary WebSocket messages | Runs on the audio thread, so UI work cannot drop audio | `ScriptProcessorNode`: runs on the main UI thread, drops frames under load, and is deprecated |
| Frontend playback | Web Audio scheduling on the `AudioContext` clock (`src/hooks/usePlaybackQueue.js`) | Plays each received frame right after the previous one, at the rate `audio.start` declared | The audio clock is steady whatever JavaScript is doing, so there are no gaps | `setTimeout` timers: fire late when the page is busy, which makes audible gaps |
| Testing | pytest with fakes for ASR, TTS and HTTP (`backend/tests/`); real Whisper only under `pytest -m slow`; frontend: plain Node test scripts (`npm test`) | Checks every stage without models, keys or network | The default run is fast and needs nothing downloaded | Real models in every test: a few hundred MB of download and seconds of CPU per test |
| CI | GitHub Actions: ruff and pytest on every PR into `dev` or `main` (`.github/workflows/ci.yml`), slow ASR tests in `asr-slow.yml` | Installs the exact locked versions (`uv sync --frozen`), fetches the default persona's voices, lints, tests | Every PR is checked the same way on a clean machine | Slow ASR tests in every PR: they run only when ASR code, config or dependencies change, because of the model download and CPU time |

There is no CI job for the frontend.

## c. One turn, end to end

From the user's voice in the mic to the agent's voice in the speaker. "Turn"
means one user utterance; its `turn_id` is made when speech starts, and the
transcript, the reply text and the reply audio all carry it.

0. **Server start.** File: `backend/vaani/app.py`. What: loads the Silero model (checks its sha256), loads and warms up Whisper, builds the provider chain (refuses to start if a listed provider has no API key) and loads every persona's two Piper voices. When: once, when the server starts; every session shares these. Database query: none, database not integrated yet.
1. **Connect.** File: `frontend/src/hooks/useAudioCapture.js`, called from `src/pages/ConversationPage.jsx`. What: asks for the mic with echo cancellation, noise suppression and auto gain on, opens an `AudioContext` at 16 kHz, loads the worklet, opens the WebSocket to `/ws/session` and sends `session.start` with the persona and the audio format. When: the user clicks Start Conversation. Database query: none, database not integrated yet.
2. **Session start.** File: `backend/vaani/gateway.py`. What: checks the audio format matches `config.toml` and the persona is a key of `[personas]`, then creates the `Session` (`session.py`), its `Telemetry` and its `TurnPipeline` (`turns.py`) with the persona's voices, and replies `session.started`. When: once per connection. Database query: none, database not integrated yet.
3. **Capture.** File: `frontend/public/audio-processor.js`, then `useAudioCapture.js`. What: the worklet collects samples into 320-sample frames, converts them to 16-bit little-endian PCM (640 bytes) and hands each to the page, which sends it as a binary message. When: every 20 ms, from `session.started` until disconnect. Database query: none, database not integrated yet.
4. **Ingest.** File: `gateway.py`. What: checks a session exists and the frame is exactly the size config implies, counts it and passes it to `TurnPipeline.on_frame`. When: every frame. Database query: none, database not integrated yet.
5. **VAD.** File: `vad.py`, called from `turns.py`. What: converts the frame to floats, runs Silero each time 512 samples have built up, and applies hysteresis: 4 speech frames in a row give `speech_started`, 10 silent frames give `speech_ended`. When: every frame, on the event loop. Database query: none, database not integrated yet.
6. **Turn opens.** Files: `endpoint.py`, `turns.py`, `session.py`, `turn_state.py`. What: on `speech_started` while the agent is idle, the endpointer opens an utterance (with 300 ms of audio from before speech began, so the first syllable is kept), the session makes a new `turn_id`, and the state machine moves to `listening` and sends `turn.state`. When: the first frame VAD calls speech. Database query: none, database not integrated yet.
7. **Endpointing.** File: `endpoint.py`, then `turns.py`. What: after `speech_ended` it waits 700 ms of silence, counted in frames; speech resuming cancels the wait. Too little voiced audio is discarded as a cough; 30 s forces an end. When the turn ends, `turns.py` records the `turn_ended` span, moves to `thinking` and asks ASR for the final transcript. When: every frame while an utterance is open. Database query: none, database not integrated yet.
8. **Transcription.** Files: `asr/runner.py`, `asr/whisper.py`. What: the runner queues the job and a background task runs it; Whisper decodes on its own thread pool (forced to Hindi, with a romanized Hinglish prompt, one decode, no retries). It sends `transcript.final`, or `ASR_FAILED` after `timeout_s`, and hands the text back to `turns.py`. Partial transcripts are off in config. When: right after the turn ends, off the frame loop. Database query: none, database not integrated yet.
9. **Reply starts.** Files: `turns.py`, `reply.py`. What: joins any words carried from an interrupted turn (section d) with the new transcript and starts a background reply with its own cancellation token (an `asyncio.Event` that a barge-in sets). When: as soon as the transcript arrives. Database query: none, database not integrated yet.
10. **Guardrail and prompt.** File: `persona.py`, called from `reply.py`. What: checks the raw transcript against the `[guardrail]` patterns (a match sends `INPUT_REJECTED` and goes idle), then builds the request: persona system prompt, the session's history, this transcript. When: once per reply, before any network call. Database query: none, database not integrated yet.
11. **Language model.** Files: `providers/chain.py`, `gemini.py`, `groq.py`, `streaming.py`, `spend.py`. What: the request cap is checked before each paid request; the chain streams from Groq, and fails over to Gemini only on a rate limit, timeout or outage, and only before the first word. Each piece of text is sent to the browser as `agent.text`. When: during `thinking`, as the model writes. Database query: none, database not integrated yet.
12. **Chunking.** File: `chunker.py`, called from `reply.py`. What: the first chunk is cut at the earliest sentence end or comma (or a conjunction once it has 8 characters, or the last space at 60); later chunks wait for a sentence end. When: on every piece of text. Database query: none, database not integrated yet.
13. **Synthesis.** Files: `speaker.py`, `language.py`, `tts/piper.py`. What: the first chunk picks the Hindi or English voice by script and locks it for the reply; Piper synthesises the chunk on a thread. On the first audio the state moves to `speaking` and `audio.start` declares the voice's sample rate; the audio goes out as binary frames of 20 ms at that rate. The cancellation token is checked before every send. When: each chunk, while the model is still writing. Database query: none, database not integrated yet.
14. **Playback.** Files: `ConversationPage.jsx`, `usePlaybackQueue.js`, `useTranscript.js`, `TranscriptView.jsx`. What: `audio.start` sets the playback rate; each frame becomes an audio buffer scheduled right after the previous one on the `AudioContext` clock; the browser resamples to the speaker's rate. The reply text appears as `agent.text` arrives. When: as frames arrive. Database query: none, database not integrated yet.
15. **Turn ends.** Files: `reply.py`, `speaker.py`, `session.py`. What: sends `agent.done` and `audio.end`, stays `speaking` until the audio should have finished playing (an estimate), then stores the exchange in history and moves to `idle`. When: after the last chunk. Database query: none, database not integrated yet.

Failures end the same way: an `error` message (`ASR_FAILED`, `LLM_FAILED`,
`TTS_FAILED` or `INPUT_REJECTED`), then `turn.state idle`. The browser shows the
code in a banner.

## d. Barge-in, end to end

The user talks while the agent is `thinking` or `speaking`.

1. **Routing.** File: `turns.py`. What: while the agent is busy, every frame goes to the barge-in judge instead of the endpointer. When: every frame during `thinking` or `speaking`. Database query: none, database not integrated yet.
2. **Judging.** File: `barge_in.py`. What: after `speech_started`, it counts frames whose speech probability reaches `[barge_in].threshold`, starting from VAD's 4; at `min_speech_ms` (200 ms) it is an interruption. A `speech_ended` first means it was a noise and the reply goes on. All frames since speech began are held. When: every frame of that speech. Database query: none, database not integrated yet.
3. **Stop.** Files: `barge_in.py`, `reply.py`, `session.py`. What: records the `barge_in` span, sets the reply's cancellation token (no more audio can be sent after this line), marks the turn flushed and sends `audio.flush` as the first message out. When: the frame that decides it. Database query: none, database not integrated yet.
4. **Upstream stops.** Files: `providers/streaming.py`, `speaker.py`, `tts/piper.py`, `asr/runner.py`. What: the model's HTTP stream is closed at once, even mid-wait; the speaker sends nothing more; a Piper synthesis already running finishes on its thread and its audio is thrown away. A transcript still being made is kept and carried into the next reply. When: right after the token is set. Database query: none, database not integrated yet.
5. **Browser stops.** Files: `useAudioCapture.js`, `usePlaybackQueue.js`, `ConversationPage.jsx`. What: on `audio.flush` it fades every scheduled sound to zero in 10 ms, stops them, resets the queue, replies `flush.ack` and marks the agent's text as interrupted. When: when `audio.flush` arrives. Database query: none, database not integrated yet.
6. **What was heard.** File: `barge_in.py` (`heard_text`), using `speaker.py`'s play-out estimates. What: estimates how much of the reply had played and records only that part in history. If nothing was heard, the user's words are carried and answered together with what they say next. When: during the stop, before the new turn opens. Database query: none, database not integrated yet.
7. **New turn.** Files: `turns.py`, `turn_state.py`. What: moves to `cancelling`, then `listening` with a new `turn_id`, and replays the held frames into the endpointer, so the new turn starts at the user's first sound. From here it is a normal turn (section c, step 7). If the new speech is too short to be a turn but words were carried, those words are answered. When: straight after the stop. Database query: none, database not integrated yet.
8. **Ack.** File: `session.py`. What: `flush.ack` is matched to the flushed turn and the round trip is logged (`flush_acked` span). When: when the ack arrives, usually after the new turn is current. Database query: none, database not integrated yet.

## e. Where the conversation context lives today

- **Where:** `Session.history` in `backend/vaani/session.py`: a list in the server's memory, one per WebSocket connection. Nothing is shared between sessions and nothing is written to disk.
- **What is kept:** the last `history_turns` exchanges (6 in `config.toml`). One exchange is the user's transcript plus what the user heard of the reply: the whole reply if it played to the end, the heard part if it was cut. It is re-sent to the model with every new turn (`persona.py`), after the persona's system prompt. The persona is fixed at `session.start`.
- **Also in memory:** words carried from an interrupted turn (`TurnPipeline` in `turns.py`), until the next reply uses them. The browser's transcript is React state (`useTranscript.js`), cleared on every connect.
- **What is lost, and when:**
  - Exchanges older than the last 6: dropped on the next new exchange, not summarised.
  - A turn that failed (`ASR_FAILED`, `LLM_FAILED`, `TTS_FAILED`) or was blocked (`INPUT_REJECTED`): never stored.
  - Everything: when the socket closes (session end, page closed, network drop) or the server restarts. Reconnecting starts a new, empty session.
  - The paid request counter (`spend.py`) is per process: it resets when the server restarts.

## f. Database

**Not integrated yet.** No table, no query and no database driver exist in
the code on `dev` (`backend/pyproject.toml` has none). When it is added, this
table lists every query the code sends:

| Table | Query | Sent from which file | When | Why this query and not another |
|---|---|---|---|---|
| (none yet) | | | | |

## g. Where the details live

- The WebSocket protocol (every message, field, error code and version): [`docs/contracts.md`](../contracts.md).
- The latency numbers and the budget: [`docs/findings/perf-1-latency-budget.md`](../findings/perf-1-latency-budget.md).
- Every runtime setting, with the reason for its value: `backend/config.toml`.
- How each step was built and why: the per-PR documents in `backend-learning/` and `frontend-learning/`.

## Known gaps on `dev`

- Groq's free tier is shared by everyone using the key; past its limit it answers HTTP 429 and the chain fails over to Gemini. For `openai/gpt-oss-20b` the limits are 1000 requests a day and 8000 tokens a minute; how many turns a minute that allows was not measured (`backend-learning/15c-groq-primary.md`).
- The browser plays any frame that arrives after `audio.flush`; it does not track flushed `turn_id`s as `contracts.md` asks. Today the server sends nothing after the flush, so this has not shown up.
- The backend sends no `telemetry` message, so the frontend's latency panel has nothing to show.
- Seen in the live demo (2026-10-08/09), not measured in a run file: long sentences hit the 5 s ASR timeout (15 s was used, as a local `.env` override only); noise or echo caused false barge-ins that produced short made-up Hindi transcripts; after `ASR_FAILED` the orb stayed on "thinking", and it said "tap connect" while already connected.
