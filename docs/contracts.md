# Vaani — Frontend/Backend Communication Contracts

This document describes the agreed interface between the frontend (Samyak)
and the backend (Aryan). Both sides should update this file when the
contract changes.

Status labels:
- **Agreed** — both sides have confirmed.
- **Proposed** — drafted by one side, awaiting confirmation.
- **Planned** — required by the build plan but not yet specified.

---

## 1. Health Check (Agreed)

Used by the frontend to verify the backend is reachable.

| Field    | Value                |
|----------|----------------------|
| Method   | `GET`                |
| Path     | `/health`            |
| Response | `{ "status": "ok", "version": "<semver>" }` |

Already implemented in `backend/vaani/app.py`.

---

## 2. WebSocket Audio Channel (Agreed)

Real-time bidirectional channel for voice conversation.

| Field       | Value                          |
|-------------|--------------------------------|
| Endpoint    | `ws://<host>/ws/session`       |
| Direction   | Bidirectional                  |
| Initiated by| Frontend                       |

### 2.1 Client → Server: Audio Frames (Agreed / Client Implemented)

The frontend captures microphone audio using AudioWorklet and sends it as binary
WebSocket messages.

| Parameter       | Value                                  |
|-----------------|----------------------------------------|
| Message type    | Binary                                 |
| Encoding        | Raw PCM, 16-bit signed little-endian (Int16LE) |
| Sample rate     | 16,000 Hz                              |
| Channels        | 1 (mono)                               |
| Frame duration  | 20 ms                                  |
| Samples/frame   | 320                                    |
| Bytes/frame     | 640 (320 samples × 2 bytes)            |
| Byte order      | Little-endian                          |
| Expected rate   | ~50 frames/second                      |

Each binary message is exactly 640 bytes. The frontend converts Float32 Web Audio
samples directly to Int16LE inside the dedicated AudioWorklet thread.

### 2.2 Server → Client: Audio Playback (Proposed — pending Aryan confirmation)

The backend will stream synthesised audio back as binary WebSocket frames using
the **same PCM encoding** as the upstream direction. This is the format the
frontend playback queue (Day 3) is built to decode.

| Parameter       | Value                                  |
|-----------------|----------------------------------------|
| Message type    | Binary                                 |
| Encoding        | Raw PCM, 16-bit signed little-endian (Int16LE) |
| Sample rate     | 16,000 Hz                              |
| Channels        | 1 (mono)                               |
| Frame duration  | Variable (backend may bundle frames)   |
| Bytes/sample    | 2                                      |
| Byte order      | Little-endian                          |

The frontend decodes incoming bytes as `Int16Array`, scales to Float32
(dividing by 32768), and schedules each chunk on the Web Audio clock for
gapless playback. No format negotiation is needed: both sides use the same
sample rate and encoding.

> **Note**: The current backend (`gateway.py`) does not yet echo audio back.
> This format will be confirmed when Aryan implements the TTS/echo path.

### 2.3 Control Messages (Agreed)

Control messages use JSON text frames (not binary).

#### Client → Server

| Type             | Payload                                                   | When                                             |
|------------------|-----------------------------------------------------------|--------------------------------------------------|
| `session.start`  | `{ "type": "session.start", "persona": "default", "audio": { "sample_rate": 16000, "channels": 1, "frame_ms": 20 } }` | After WebSocket connects                         |
| `session.end`    | `{ "type": "session.end" }`                               | User ends conversation                           |
| `audio.flush.ack`| `{ "type": "audio.flush.ack", "timestamp_ms": <number> }` | Sent immediately after audio playback is flushed |

#### Server → Client

| Type             | Payload                                               | When                              |
|------------------|-------------------------------------------------------|-----------------------------------|
| `session.started`| `{ "type": "session.started", "session_id": "..." }`  | Backend accepted session.start    |
| `error`          | `{ "type": "error", "code": "...", "message": "..." }` | Protocol error (non-fatal)        |
| `audio.flush`    | `{ "type": "audio.flush" }`                           | Server requests immediate silence |

### 2.4 Transcripts — SHARED PROTOCOL v0.3 (Agreed)

Server → client, JSON text frames. Implemented on the backend in
`backend/vaani/protocol.py` (`TranscriptPartial`, `TranscriptFinal`).

| Type | Payload | When |
|---|---|---|
| `transcript.partial` | `{ "type": "transcript.partial", "turn_id": "<string>", "text": "<string>" }` | While the user is still speaking. Each one **replaces** the previous partial for that `turn_id`; it is not appended |
| `transcript.final` | `{ "type": "transcript.final", "turn_id": "<string>", "text": "<string>", "duration_ms": <number>, "language": "<string or null>" }` | Once per turn, after endpointing fires. Replaces the partial |

A final may arrive with no preceding partial, and may differ from the last
partial shown. The browser must handle both.

Backend notes (day 10):
- **A turn is one user utterance.** Its `turn_id` is created when speech
  starts. Partials, the final, and any echo audio for that utterance share it.
  This changes echo mode: `audio.start` / `audio.end` now come **once per
  utterance**, not once per session, and frames between utterances are not
  echoed.
- Partials are **off by default** (`[asr].partial_interval_ms = 0`), so today
  the browser receives finals only.
- A turn that is flushed (`audio.flush`) gets no transcript at all.
- `text` may contain Devanagari and Latin script in the same sentence.
- `duration_ms` is the length of the user's speech in the turn.

### 2.5 Agent turn — SHARED PROTOCOL v0.4 (Proposed — pending Samyak, agree as one block)

Server → client, JSON text frames. Implemented on the backend in
`backend/vaani/protocol.py` (`TurnStateMessage`, `AgentText`, `AgentDone`,
`ErrorCode`). Everything in this section is new in v0.4 and is meant to be
agreed **together**.

| Type | Payload | When |
|---|---|---|
| `turn.state` | `{ "type": "turn.state", "turn_id": "<string or null>", "state": "idle" \| "listening" \| "thinking" \| "speaking" \| "cancelling" }` | On every state change. `turn_id` is `null` only when `state` is `idle` |
| `agent.text` | `{ "type": "agent.text", "turn_id": "<string>", "delta": "<string>" }` | One streamed fragment of the reply. **Append** these (unlike `transcript.partial`, which replaces) |
| `agent.done` | `{ "type": "agent.done", "turn_id": "<string>", "text": "<string>" }` | The reply is complete; `text` is the full reply. A client may ignore it if it accumulated the deltas |

One normal turn traces `listening → thinking → speaking → idle`. The
`turn_id` is the user utterance's id, so the transcript and the reply share it.
A failed turn gets `error` then `turn.state idle`, and **no** `agent.done`. A
cancelled turn (`dev.flush` today) traces `cancelling → idle`, and also gets
no `agent.done`.

Backend notes (day 11):
- `speaking` means "reply text is streaming" until speech synthesis lands
  (day 12). Nothing is audible yet.
- The backend is **half-duplex**: speech while the agent is thinking or
  speaking is dropped (logged server-side), so no `listening` appears then.
- `session.start`'s `persona` must be one of `default`, `tutor`, `support`
  (config.toml `[personas]`); anything else gets `BAD_MESSAGE`.

**Error codes (all three pending Samyak).** Shape:
`{ "type": "error", "code": "<code>", "message": "..." }`. All are non-fatal:
the connection stays open. None carries a `turn_id`.

| Code | Meaning | What follows |
|---|---|---|
| `ASR_FAILED` | The turn's final transcript could not be produced (recogniser error, or the `[asr].timeout_s` timeout) | No `transcript.final`; `turn.state idle` |
| `LLM_FAILED` | The agent could not answer: every provider failed, a provider error, the spend cap, or an empty reply | No `agent.done`; `turn.state idle`. Must be surfaced to the user, never silence. Once synthesis exists (day 12) the backend will **speak** an apology instead of only sending text |
| `INPUT_REJECTED` | The user's turn was blocked by the input guardrail before reaching the model | `turn.state idle`. The message is deliberately vague ("that turn wasn't processed"): the user needs to know nothing happened, not which rule fired |

---

## 3. Future Contracts (Planned)

These will be specified as their implementation days arrive:

- **Barge-in signalling** — Week 3
- **Voice enrolment API** — Week 4

---

## Changelog

| Date       | Author  | Change                                                                                  |
|------------|---------|-----------------------------------------------------------------------------------------|
| 2026-09-22 | Samyak  | Initial draft: audio frame format, session lifecycle                                    |
| 2026-09-23 | Samyak  | Day 2 implementation: Int16LE 640B frames via AudioWorklet                              |
| 2026-09-23 | Samyak  | Day 3: fix endpoint to /ws/session, fix session.start payload, document playback format  |
| 2026-09-24 | Samyak  | Day 4: audio.flush and audio.flush.ack specification for immediate playback silencing   |
| 2026-10-02 | Aryan   | Day 10: shared protocol v0.3 transcripts; turn = utterance (echo per utterance); proposed ASR_FAILED |

| 2026-10-02 | Aryan   | Day 11: shared protocol v0.4 (turn.state, agent.text, agent.done); ASR_FAILED, LLM_FAILED, INPUT_REJECTED proposed together in §2.5 |
