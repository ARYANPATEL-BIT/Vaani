# 11 — Turn UI States, Streaming Reply, Interrupted Turns & Error States

## 1. What we built in this branch

Branch: `feat/turn-ui-states`

This branch delivers the official Week 3 Day 2 frontend functionality for Vaani:
1. **Turn States in the UI**: Mirroring the backend turn state machine (`idle`, `listening`, `thinking`, `speaking`, `cancelling`) in the UI components (`VoiceOrb`, `TranscriptView`, and `ConversationPage`), driven by real `turn.state` wire messages (`SHARED PROTOCOL v0.4`).
2. **Streaming Agent Reply as Text**: Incrementally appending streamed text fragments from `agent.text` deltas into active draft responses in real time, settling into immutable entries upon receiving `agent.done`.
3. **Interrupted Turns Clearly Marked**: When a turn is interrupted or flushed (`turn.state cancelling` or `audio.flush`), preserving the accumulated response text, marking the entry explicitly with `interrupted: true` and an visual `[Interrupted]` badge, without silent discarding or false completion.
4. **Comprehensive Error Screens & States ("Nothing Fails Silently")**:
   - **Microphone Denied**: Clear user-facing card explaining permission requirement and site settings, with a "Try Again" recovery action.
   - **Connection Dropped**: Clear alert notifying unexpected socket closure, preventing false active session state, with a "Reconnect" action.
   - **Provider Failure**: Explicit notifications for `LLM_FAILED`, `ASR_FAILED`, `TTS_FAILED`, and `INPUT_REJECTED` mapped to clear human-readable explanations via `formatServerError`.
5. **Automated Unit Tests**: 52 assertions across 13 required test cases in `frontend/src/turnState/turnState.test.js` validating state transitions, delta accumulation, cancellation, and error mappings.

## 2. What we used to build it

- **Turn Contract & Validator Module `turnContracts.js`** — Pure JavaScript validation and error formatting module mirroring wire types from `backend/vaani/protocol.py` and `docs/contracts.md` §2.3–§2.5. Rejects malformed frames without throwing.
- **Enhanced `useTurnState` Hook** — Tracks `turnState`, `turnId`, `agentDraft`, and `lastAgentMessage` cleanly synchronized with protocol messages.
- **Enhanced `useTranscript` Hook** — Manages user turns, live partials, streaming agent replies, and interrupted turn finalization (`interruptAgentTurn`).
- **Enhanced `useAudioCapture` Hook** — Tracks `micStatus` ('idle' | 'requesting' | 'active' | 'denied' | 'error'), handles unexpected socket closure as connection-dropped, and routes server error messages without swallowing them.
- **Dialogue Feed `TranscriptView`** — Renders live streaming bubbles with live indicators, thinking dot animations, and interrupted dialogue cards.
- **Visual Presence `VoiceOrb`** — Displays turn state titles and subtitles for all 5 pipeline states including `Interrupted` for cancelling.

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| Streamed reply display | Append real `agent.text` deltas progressively | Simulated streaming via `setInterval` | Fake streaming creates artificial lag and violates the core rule of grounding in real protocol events | Trivial client-only demo |
| Interrupted turn handling | Preserve received text with `interrupted: true` badge | Silently discard in-flight text on cancel | Silently deleting replies confuses the user and masks model output | Simpler transcript array manipulation |
| Error code presentation | Map `ErrorCode` to plain language via `formatServerError` | Raw error codes or alert popups | Raw strings (e.g. `LLM_FAILED`) confuse users; browser alerts freeze the UI event loop | Zero-effort error pass-through |
| Turn state validation | Pure validator functions in `turnContracts.js` | Ad-hoc inline checks in components | Ad-hoc checks lead to duplicate validation and make headless unit testing difficult | Single-file quick hacks |

## 4. Where things live

| What | File | Function or component |
|---|---|---|
| Turn contracts & error mappings | `frontend/src/turnState/turnContracts.js` | `TURN_STATES`, `ERROR_CODES`, `formatServerError`, validators |
| Turn state hook | `frontend/src/hooks/useTurnState.js` | `useTurnState()` |
| Transcript state hook | `frontend/src/hooks/useTranscript.js` | `useTranscript()`, `interruptAgentTurn()` |
| Audio capture & error states | `frontend/src/hooks/useAudioCapture.js` | `useAudioCapture()`, mic denied & dropped connection handling |
| Transcript presentation | `frontend/src/components/TranscriptView.jsx` | `TranscriptView`, interrupted badge, streaming text |
| Transcript styling | `frontend/src/components/TranscriptView.css` | `.message-interrupted`, `.badge-interrupted`, `.thinking-dots` |
| Conversation page | `frontend/src/pages/ConversationPage.jsx` | Integration of turn routing and failure screens |
| Conversation styling | `frontend/src/pages/ConversationPage.css` | `.error-banner` variations and action buttons |
| Unit test suite | `frontend/src/turnState/turnState.test.js` | 52 assertions covering all 13 test requirements |

## 5. How it works

1. **User Speaks**: As the user speaks, `transcript.partial` updates the active user bubble in `TranscriptView`. When endpointing fires, `transcript.final` commits the utterance to the permanent transcript list.
2. **Thinking**: The backend sends `turn.state thinking`. The `VoiceOrb` displays "Thinking..." and the `TranscriptView` shows an animated thinking indicator.
3. **Agent Streams**: As the model generates tokens, `agent.text` deltas arrive and are appended into `currentAgentPartial`. The user sees the assistant's reply streaming in real time.
4. **Speaking**: When the first audio frame arrives, the backend sends `turn.state speaking`. The `VoiceOrb` pulses with the speaking animation.
5. **Completion or Interruption**:
   - If normal: `agent.done` arrives, committing the full text to the transcript list with `interrupted: false`.
   - If interrupted: `audio.flush` or `turn.state cancelling` arrives. `interruptAgentTurn` commits the text accumulated so far with `interrupted: true`, immediately displaying the `[Interrupted]` badge.
6. **Error States**: If microphone access is denied or the socket drops, dedicated error banners render with "Try Again" / "Reconnect" buttons. If a provider fails (`LLM_FAILED`), the error is mapped to an informative message and displayed without crashing or silent failure.
