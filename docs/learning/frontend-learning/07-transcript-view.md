# 07 — Live Transcript View

## 1. What we built in this branch

Branch: `feat/transcript-view`

This branch adds live speech transcription display to the Conversation screen.
As speech occurs, active partial transcripts update in place on screen without
creating duplicate chat bubbles. When speech ends, the final transcript settles
permanently into the transcript log, clears the active partial indicator, and
freezes in place so subsequent turns do not modify previous conversation turns.
Because the backend speech-to-text pipeline is scheduled for Day 10 and does not
yet emit transcript WebSocket events, the frontend architecture and React state
model are fully implemented and verified, while end-to-end backend streaming is
explicitly documented as blocked awaiting backend event emission.

## 2. What we used to build it

**React `useState` & `useCallback`** — React core state and memoization hooks.
`useTranscript` uses `useState` to separate mutable active partial text from the
immutable list of completed turns. `useCallback` provides stable function
identities across re-renders for parent component handlers.

**Custom hook `useTranscript`** — Encapsulates transcript business logic.
Maintains `finalTranscriptEntries` and `currentPartialTranscript`, exposing clean
transitions (`updatePartial`, `finalizeTurn`, `clearActivePartial`, `resetTranscript`).
Used to isolate transcript mutations from component rendering.

**Presentational Component `TranscriptView`** — Pure UI component displaying the
transcript feed. Separates finalized turns from the active partial turn using
distinct visual badges (`Final` vs `Listening…`), timestamps, and an accessible
log feed (`aria-live="polite"`).

**`useEffect` lifecycle binding** — Synchronizes transcript state with WebSocket
status. Clears any in-flight active partial whenever `wsStatus` switches to
`disconnected` or `error`, preventing hanging partial text.

**Passthrough subscriber `onServerMessage`** — Optional callback added to
`startCapture` in `useAudioCapture`. Allows parsed server JSON messages to reach
subscribers without opening duplicate WebSocket connections or adding redundant
socket listeners.

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| Transcript state model | Two discrete variables (`finalTranscriptEntries` + `currentPartialTranscript`) | Single array with `{ isFinal: boolean }` flag | Finding and replacing the last partial in an array requires linear scans and risks race conditions; two discrete states make partial replacement O(1) and impossible to corrupt finalized history | Simple single-variable state |
| Active partial update strategy | Overwrite `currentPartialTranscript` in place | Append every partial as a new row in the chat log | Appending creates dozens of noisy, fragmented rows ("what", "what is", "what is the") cluttering the screen | Chat history showing intermediate recognition steps |
| New session transcript handling | Reset transcript on Connect (`resetTranscript()`) | Retain previous session transcripts indefinitely | Mixing conversation turns across different WebSocket sessions confuses context and leaks prior conversation state | Multi-session persistent history (deferred to storage sprint) |
| Disconnect transcript cleanup | Clear active partial, keep finalized turns | Wipe everything on disconnect | Users want to read their final transcript after ending a call; only in-flight incomplete partials need cleanup | Completely blank page on disconnect |
| Backend event handling | Await real backend ASR events; mark E2E verification blocked | Mock/invent fake transcript events or modify `backend/` | Modifying backend violates ownership rules; inventing message types (`transcript.partial`) causes drift against Aryan's future implementation | Claiming full E2E pass today |

## 4. Where things live

| What | File | Function or class |
|---|---|---|
| Transcript state hook | `frontend/src/hooks/useTranscript.js` | `useTranscript()` |
| Partial update logic | `frontend/src/hooks/useTranscript.js` | `updatePartial(text)` |
| Finalize turn logic | `frontend/src/hooks/useTranscript.js` | `finalizeTurn(text)` |
| Transcript UI component | `frontend/src/components/TranscriptView.jsx` | `TranscriptView({ finalTranscriptEntries, currentPartialTranscript, isCapturing })` |
| Transcript styling | `frontend/src/components/TranscriptView.css` | `.transcript-section`, `.transcript-final`, `.transcript-partial` |
| Session & transcript integration | `frontend/src/pages/ConversationPage.jsx` | `ConversationPage()`, `handleConnect()`, `handleDisconnect()` |
| WebSocket message forwarding | `frontend/src/hooks/useAudioCapture.js` | `socket.onmessage` calling `onServerMessage(msg)` |
| Backend protocol (read-only audit) | `backend/vaani/protocol.py` | Models inspected: only `SessionStart`, `SessionStarted`, `AudioStart`, `AudioEnd`, `AudioFlush`, `FlushAck`, `ErrorMessage` exist |

## 5. How it works

### State machine flow

```
[Idle / Disconnected]
       │ User clicks "Connect"
       ▼
resetTranscript() called (clean slate)
       │
[Session Active]
       │ User speaks → intermediate recognition result arrives
       ▼
updatePartial("what is") ─────────────► currentPartialTranscript = "what is"
       │ Next partial arrives
       ▼
updatePartial("what is the weather") ─► currentPartialTranscript = "what is the weather" (replaces in place!)
       │ Backend detects endpoint / silence → final transcript arrives
       ▼
finalizeTurn() ──────────────────────► finalTranscriptEntries += [{ text: "what is the weather" }]
                                        currentPartialTranscript = null
       │ Next speech turn starts
       ▼
updatePartial("and tomorrow?") ──────► currentPartialTranscript = "and tomorrow?"
                                        (turn 1 remains frozen in finalTranscriptEntries!)
```

### Key code: State separation in `useTranscript.js`

```javascript
// frontend/src/hooks/useTranscript.js
export function useTranscript() {
  const [finalTranscriptEntries, setFinalTranscriptEntries] = useState([]);
  const [currentPartialTranscript, setCurrentPartialTranscript] = useState(null);

  const updatePartial = useCallback((text) => {
    if (typeof text !== 'string' || !text.trim()) {
      setCurrentPartialTranscript(null);
      return;
    }
    setCurrentPartialTranscript(text);
  }, []);

  const finalizeTurn = useCallback((text) => {
    setCurrentPartialTranscript((currentPartial) => {
      const finalText = text !== undefined ? text : currentPartial;
      if (typeof finalText === 'string' && finalText.trim()) {
        const entry = {
          id: `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          text: finalText.trim(),
          timestamp: Date.now(),
        };
        setFinalTranscriptEntries((prev) => [...prev, entry]);
      }
      return null;
    });
  }, []);
```

### Key code: Session lifecycle integration in `ConversationPage.jsx`

```javascript
// frontend/src/pages/ConversationPage.jsx
  const handleConnect = () => {
    if (isCapturing) return;
    resetTranscript();
    startCapture(enqueue, flushPlayback, selectedPersona);
  };

  const handleDisconnect = () => {
    clearActivePartial();
    stopCapture();
  };

  useEffect(() => {
    if (wsStatus === 'disconnected' || wsStatus === 'error') {
      clearActivePartial();
    }
  }, [wsStatus, clearActivePartial]);
```

## 6. When things go wrong

| What fails | What the code does | What the user sees |
|---|---|---|
| User disconnects while speaking | `clearActivePartial()` drops in-flight partial text; finalized entries remain preserved | Active partial immediately disappears; completed turns remain readable |
| WebSocket connection drops or errors | `useEffect` catches `wsStatus === 'error'/'disconnected'` and clears active partial | Error banner shown at top; partial text cleared; no corrupted entries |
| Empty or whitespace partial received | `updatePartial` checks `!text.trim()` and sets partial to `null` | No empty speech bubble or ghost element rendered |
| Backend emits no transcript events | Frontend renders empty state placeholder; pipeline logs diagnostics | "No speech detected yet. Connect and speak to see live transcription." |

## 7. New terms

- **Active Partial Transcript** — Intermediate, provisional speech recognition text that updates continuously as audio frames are processed. Subject to revision until speech ends.
- **Finalized Transcript** — An immutable, settled speech turn produced when an end-of-speech boundary (VAD silence / endpointing) is confirmed.
- **In-place replacement** — Updating the single active text node in DOM rather than appending new elements to a list, preventing UI visual spam.
- **Immutable turn log** — An append-only list of completed conversation turns that are never mutated by subsequent recognition events.

## 8. Questions you could be asked

1. **Where is the code that handles partial updates?**
   In `frontend/src/hooks/useTranscript.js` in the `updatePartial` function, which mutates `currentPartialTranscript` without modifying `finalTranscriptEntries`.
2. **What happens if three partial results arrive in quick succession?**
   Each call to `updatePartial` replaces the string in `currentPartialTranscript`. Only the latest string is rendered; no previous partials are saved to history.
3. **Why not keep partial and final transcripts in a single array?**
   Keeping them separate guarantees that partial updates cannot accidentally modify or re-render previous finalized turns, and eliminates array-slicing logic on every 50 ms recognition tick.
4. **What happens to the transcript when the user clicks Disconnect?**
   `clearActivePartial()` is called, which clears any unfinalized partial text. The finalized turns remain visible in the transcript feed for review.
5. **What happens when the user clicks Connect to start a new session?**
   `resetTranscript()` is called, clearing both finalized entries and active partial, ensuring a fresh session.
6. **Did we modify any backend code?**
   No. All changes are strictly inside `frontend/`. Backend files (`backend/vaani/`) were inspected read-only.
7. **Does the backend currently stream transcripts?**
   No. The backend (`backend/vaani/protocol.py` and `gateway.py`) currently handles audio frames, echo, VAD, and flush, but has not yet integrated STT (scheduled for Day 10).
8. **What is the hardest problem in live speech transcript display?**
   Preventing layout thrashing and duplicate entries while intermediate partial recognition results flicker and settle into final text.

## 9. Check yourself

1. Why must partial results replace rather than append?
2. When should `resetTranscript()` be called vs `clearActivePartial()`?
3. What is the current blocker preventing real end-to-end transcript streaming?
