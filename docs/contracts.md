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

### 2.5 Error code `ASR_FAILED` (Proposed — backend addition, pending Samyak)

`{ "type": "error", "code": "ASR_FAILED", "message": "..." }` is sent when a
turn's final transcript could not be produced (recogniser error, or the
`[asr].timeout_s` hard timeout). It is non-fatal: the connection stays open.
No `transcript.final` follows for that turn. The message has no `turn_id`.

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

