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

## 2. WebSocket Audio Channel (Proposed)

Real-time bidirectional channel for voice conversation.

| Field       | Value                          |
|-------------|--------------------------------|
| Endpoint    | `ws://<host>/ws/audio`         |
| Direction   | Bidirectional                  |
| Initiated by| Frontend                       |

### 2.1 Client → Server: Audio Frames (Proposed)

The frontend captures microphone audio and sends it as binary
WebSocket messages.

| Parameter       | Value                                  |
|-----------------|----------------------------------------|
| Message type    | Binary                                 |
| Encoding        | Raw PCM, 16-bit signed little-endian (Int16) |
| Sample rate     | 16,000 Hz                              |
| Channels        | 1 (mono)                               |
| Frame duration  | 20 ms                                  |
| Samples/frame   | 320                                    |
| Bytes/frame     | 640 (320 samples × 2 bytes)            |
| Byte order      | Little-endian                          |
| Expected rate   | ~50 frames/second                      |

Each binary message is exactly 640 bytes. The backend can read them as
a flat `Int16Array` or equivalent.

> **Needs Aryan's confirmation:** Is raw PCM Int16LE the preferred
> encoding, or does the backend expect Float32? Int16LE is more
> compact (640 bytes vs 1280 bytes per frame) and is the standard
> input format for Silero VAD and faster-whisper.

### 2.2 Server → Client: Audio Playback (Planned)

The backend will stream synthesised audio back. Format TBD.

### 2.3 Control Messages (Proposed)

Control messages use JSON text frames (not binary).

#### Client → Server

| Type           | Payload                          | When                              |
|----------------|----------------------------------|-----------------------------------|
| `session.start`| `{ "type": "session.start" }`    | After WebSocket connects          |
| `session.end`  | `{ "type": "session.end" }`      | User ends conversation            |

#### Server → Client

| Type           | Payload                          | When                              |
|----------------|----------------------------------|-----------------------------------|
| `session.ready`| `{ "type": "session.ready" }`    | Backend is ready to receive audio |
| `error`        | `{ "type": "error", "message": "..." }` | Unrecoverable error        |

> **Needs Aryan's confirmation:** Are these the right session
> lifecycle messages? Additional types (flush, interrupt, transcript)
> will be added in later weeks.

---

## 3. Future Contracts (Planned)

These will be specified as their implementation days arrive:

- **Flush / interrupt** — Week 1, Day 4
- **Transcript streaming** — Week 2
- **Barge-in signalling** — Week 3
- **Voice enrolment API** — Week 4

---

## Changelog

| Date       | Author  | Change                              |
|------------|---------|-------------------------------------|
| 2026-09-22 | Samyak  | Initial draft: audio frame format, session lifecycle |
