# 06 — Conversation Session Shell

## 1. What we built in this branch

Branch: `feat/conversation-shell`

This branch adds the Week 2, Day 1 conversation screen: a UI that makes the
session lifecycle explicit and observable. Before this, the "Start Microphone"
button silently opened a WebSocket session. Now the page has **Connect** and
**Disconnect** buttons, a **session status badge** that always shows the current
state (`Disconnected`, `Connecting…`, `Starting session…`, `Session active`,
`Connection error`), and a **persona selector** that is sent to the backend in
the `session.start` message. A bug in the `flush.ack` message type and payload
fields was discovered and fixed as part of the audit.

## 2. What we used to build it

**React `useState`** — JavaScript function that gives a component a reactive
variable and a setter. `selectedPersona` lives in `useState` so the dropdown
re-renders when the user changes it. Used because the persona choice outlives
individual connect/disconnect cycles.

**`useAudioCapture` hook (existing, extended)** — The Week 1 hook that owns the
WebSocket and audio capture pipeline. Extended with: a `persona` argument to
`startCapture`, a `sessionId` state variable populated from `session.started`,
and a corrected `flush.ack` message.

**`usePlaybackQueue` hook (existing, unchanged)** — Handles gapless PCM
playback. Not modified; `enqueue` and `flushPlayback` are still passed into
`startCapture` as Week 1 callbacks.

**CSS `appearance: none` + `background-image` SVG** — Removes the browser's
native dropdown arrow from `<select>` and replaces it with a consistent inline
SVG chevron. Used to style the persona selector uniformly across browsers.

**`aria-describedby` / `aria-label`** — HTML accessibility attributes. Links
the persona hint paragraph to the select element so screen readers announce it,
and labels the Connect / Disconnect buttons semantically.

**`disabled` attribute on `<select>` and `<button>`** — HTML boolean attribute
that prevents user interaction. The persona selector is disabled when a session
is active (persona cannot change mid-session); the Connect button is disabled
while transitioning.

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| Session state machine | Reuse `wsStatus` string from `useAudioCapture` | Add a separate `sessionStatus` enum | `wsStatus` already maps exactly to the contract states; duplicating state risks them drifting out of sync | None |
| Persona state location | `useState` in `ConversationPage` | `useRef`, prop drilling, context | Persona is UI state that survives connect/disconnect; `useState` re-renders the dropdown; `useRef` would not | None |
| New session hook | Extend `useAudioCapture` | Create `useSession.js` | The audio capture hook already owns the WebSocket and all session logic; a separate hook would require sharing the socket reference, a harder problem than adding two parameters | Slightly wider responsibility for the existing hook |
| Persona options | Only `"default"` in the selector | Hardcode additional persona names | `protocol.py SessionStart.persona` is `str`, no enum, and `config.toml` defines no persona names; inventing values would be fabricating contract | UI only shows one option until the backend defines more |
| `flush.ack` bug fix | Fix as part of Day 1 audit | Defer to a separate PR | The bug meant the backend's `session.handle_flush_ack()` was silently ignoring every ack sent from the frontend; catching it now validates the full flush round-trip | Having to update contracts.md changelog |

## 4. Where things live

| What | File | Function or class |
|---|---|---|
| Session status badge | `frontend/src/pages/ConversationPage.jsx` | `getSessionStatusDisplay()` |
| Persona selector dropdown | `frontend/src/pages/ConversationPage.jsx` | `handlePersonaChange()`, `PERSONA_OPTIONS` |
| Connect handler | `frontend/src/pages/ConversationPage.jsx` | `handleConnect()` |
| Disconnect handler | `frontend/src/pages/ConversationPage.jsx` | `handleDisconnect()` |
| Persona passed to session | `frontend/src/hooks/useAudioCapture.js` | `startCapture(onBinaryMessage, onFlushCommand, persona)` |
| `sessionId` exposed to UI | `frontend/src/hooks/useAudioCapture.js` | `useState(null)` → `setSessionId(msg.session_id)` |
| `flush.ack` fix | `frontend/src/hooks/useAudioCapture.js` | `socket.onmessage` handler |
| Session status badge CSS | `frontend/src/pages/ConversationPage.css` | `.session-status-row`, `.session-status-badge`, `.session-id-display` |
| Persona selector CSS | `frontend/src/pages/ConversationPage.css` | `.persona-section`, `.persona-select`, `.persona-hint` |
| Disabled button CSS | `frontend/src/pages/ConversationPage.css` | `.action-btn:disabled` |
| Valid persona names | `docs/contracts.md` §2.3 | `session.start` payload row |
| Backend persona field | `backend/vaani/protocol.py` | `SessionStart.persona: str = "default"` |
| Backend flush.ack model | `backend/vaani/protocol.py` | `FlushAck` |

## 5. How it works

### Session state machine

```
disconnected
    │ (Click Connect)
    ▼
connecting      ← WebSocket TCP handshake in progress
    │ (onopen fires)
    ▼
connected       ← session.start sent; awaiting server reply
    │ (session.started received)
    ▼
ready           ← session active; audio streaming; persona set
    │ (Click Disconnect → session.end sent → WebSocket closed)
    ▼
disconnected

Any state → error  (WebSocket onerror)
```

The five state names (`disconnected`, `connecting`, `connected`, `ready`,
`error`) are the exact values `useAudioCapture` writes to `wsStatus`. The UI
reads `wsStatus` directly — there is no second state machine.

### Connect flow

```jsx
// frontend/src/pages/ConversationPage.jsx
const handleConnect = () => {
  if (isCapturing) return;
  startCapture(enqueue, flushPlayback, selectedPersona);
};
```

`startCapture` receives the persona chosen in the dropdown. Inside the hook,
when the WebSocket opens, `session.start` is sent with that persona:

```js
// frontend/src/hooks/useAudioCapture.js
socket.send(JSON.stringify({
  type: 'session.start',
  persona,                    // ← from startCapture argument
  audio: { sample_rate: 16000, channels: 1, frame_ms: 20 },
}));
```

The backend validates the audio params and, if they match `config.toml`, sends
`session.started`. The hook catches that and sets state:

```js
if (msg.type === 'session.started') {
  isSessionReadyRef.current = true;
  setSessionId(msg.session_id ?? null);
  setWsStatus('ready');
}
```

`sessionId` flows up to the page and is rendered as a truncated ID badge.

### Disconnect flow

```jsx
// frontend/src/pages/ConversationPage.jsx
const handleDisconnect = () => {
  stopCapture();
};
```

`stopCapture()` (Week 1, unchanged): stops media tracks → disconnects AudioWorklet →
closes AudioContext → sends `session.end` if session was ready → closes WebSocket →
resets all state including `sessionId = null`.

### Persona selector

```jsx
<select
  id="persona-select"
  value={selectedPersona}
  onChange={handlePersonaChange}
  disabled={isCapturing}    // locked while session is live
>
  {PERSONA_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
</select>
```

`handlePersonaChange` only acts when `!isCapturing`, providing a second guard
on top of the `disabled` attribute (the attribute prevents user interaction;
the function guard defends against programmatic calls).

### `flush.ack` bug fix

The Week 1 Day 4 implementation sent:

```json
{ "type": "audio.flush.ack", "timestamp_ms": 1234 }
```

The backend's `FlushAck` model (`backend/vaani/protocol.py`) expects:

```json
{ "type": "flush.ack", "turn_id": "...", "client_ts": 1234 }
```

Because the type string did not match (`audio.flush.ack` ≠ `flush.ack`),
the backend's `mtype == "flush.ack"` branch was never entered and every ack
was silently ignored. The fix corrects both the type and the field names:

```js
socketRef.current.send(JSON.stringify({
  type: 'flush.ack',
  turn_id: flushTurnId,   // from msg.turn_id in the audio.flush message
  client_ts: performance.now(),
}));
```

## 6. When things go wrong

| What fails | What the code does | What the user sees |
|---|---|---|
| Backend not running | `WebSocket onerror` fires → `wsStatus = 'error'` → `errorMessage` set | Error banner: "WebSocket connection failed. Ensure Aryan's backend is running." |
| Microphone permission denied | `getUserMedia` rejects with `NotAllowedError` → `micStatus = 'denied'` | Error banner with permission message; session does not open |
| Click Connect while already connected | `isCapturing` guard in `handleConnect` returns early | Nothing happens; no duplicate connection |
| Click Connect while transitioning | `disabled` attribute on Connect button | Button is greyed out; click is ignored by the browser |
| Backend sends `error` JSON message | `msg.type === 'error'` branch logs a warning | Console warning; UI does not crash |
| Server closes the WebSocket | `socket.onclose` fires → `wsStatus = 'disconnected'`, `sessionId = null` | Status badge shows "Disconnected"; user can reconnect |
| `session.started` has no `session_id` | `msg.session_id ?? null` → `sessionId = null` | No session ID badge rendered; session still works |
| Persona changed while active | `disabled` on select + `if (!isCapturing)` guard | Select is visually greyed out; change is ignored |

## 7. New terms

**`flush.ack`** — A control message the frontend sends to the backend
immediately after it stops playing a flushed audio turn. The backend logs the
round-trip time (from when it sent `audio.flush` to when `flush.ack` arrives).
Contains `turn_id` (which turn was flushed) and `client_ts` (the browser's
monotonic clock at ack time). Defined in `backend/vaani/protocol.py FlushAck`.

**`session.start` / `session.started`** — The handshake that opens a session.
The client sends `session.start` with audio params and a persona; the server
replies with `session.started` containing a `session_id`. Audio frames may only
flow after this exchange.

**Persona** — A string label the client sends in `session.start` to tell the
backend which conversational character to use. The backend stores it on the
`Session` object. Currently only `"default"` is defined; future values will
map to different voice, language, or prompt configurations.

**`disabled` (HTML attribute)** — Prevents all user interaction with a form
element. The browser ignores clicks, the element cannot receive focus, and its
value is excluded from form submission. Used here on the persona `<select>`
while the session is live and on the Connect `<button>` while transitioning.

**Session state machine** — A formal model of which states a system can be in
and which transitions are legal. The conversation screen has five states driven
by WebSocket and protocol events. The UI reads these states to decide what to
render; it does not modify them directly.

**`appearance: none`** — A CSS property that removes the browser's native
widget styling from form elements, allowing full custom styling. Required for
the persona dropdown because each browser renders `<select>` differently;
removing the native styling and adding a custom SVG arrow gives a consistent
cross-browser look.

## 8. Questions you could be asked

**Where is the code that sends persona to the backend?**
`useAudioCapture.js`, inside `socket.onopen`, in the `JSON.stringify` call that
builds the `session.start` message. The persona value arrives via the
`persona` parameter of `startCapture`.

**What happens if the user clicks Connect twice quickly?**
The first click sets `isCapturing = true` synchronously before the second click
is processed. `handleConnect` guards with `if (isCapturing) return`, and
`startCapture` also guards with `if (isCapturing) { return; }`. No duplicate
connection can be created.

**What happens if the server is unavailable?**
`new WebSocket(url)` succeeds immediately (it only starts the TCP handshake).
When the handshake fails, `socket.onerror` fires, setting `wsStatus = 'error'`
and `errorMessage` to a user-visible string. `socket.onclose` fires next,
resetting `wsStatus = 'disconnected'`. `stopCapture` is then called to release
audio resources.

**Why is the persona selector disabled while the session is active?**
The backend binds the persona to the `Session` object at `session.start` time.
There is no protocol message to change it mid-session. Allowing the user to
change the dropdown while connected would create an illusion that the change
took effect when it did not.

**What does `wsStatus === 'connected'` mean versus `'ready'`?**
`'connected'` means the WebSocket TCP connection is open and `session.start`
has been sent, but the backend has not yet replied with `session.started`. In
this state audio frames must not be sent (the backend would reject them with
`SESSION_NOT_STARTED`). `'ready'` means `session.started` was received and
audio streaming is active.

**Why not use `'loading'` or `'pending'` as state names?**
The state names come from `useAudioCapture`, which uses the exact values from
the contract. Renaming them in the UI layer would create a translation layer
that could drift. The contract defines `'connecting'`, `'connected'`, `'ready'`;
those exact strings are what the status badge renders.

**Where is the flush.ack bug fix?**
`useAudioCapture.js`, in `socket.onmessage`, in the `'audio.flush'` branch.
The type was changed from `'audio.flush.ack'` to `'flush.ack'` and the field
names from `timestamp_ms` to `turn_id` + `client_ts`, matching `FlushAck` in
`backend/vaani/protocol.py`.

**What is `performance.now()` and why is it used for `client_ts`?**
`performance.now()` returns the number of milliseconds since the page was
loaded, as a floating-point number. It is a monotonic clock — it never goes
backward, unlike `Date.now()` which can jump if the system clock changes. The
backend logs `client_ts` but explicitly does not subtract it from a server
timestamp because the two clocks start at different moments and their difference
is meaningless.

**Why is `sessionId` truncated to 8 characters in the UI?**
The session ID is a 32-character hex string (`uuid.uuid4().hex`). Showing 8
characters (`sessionId.slice(0, 8)`) is enough to distinguish sessions visually
(collision probability is 1 in 4 billion for 8 hex characters) while keeping
the UI compact. The full ID is available in the backend logs for debugging.

**What would need to change if Aryan adds a second persona?**
Only `PERSONA_OPTIONS` in `ConversationPage.jsx` needs a new entry. The
selector, the `handleConnect` call, and the `useAudioCapture` hook all already
pass through whatever string the user selects.

## 9. Check yourself

Answer these out loud without looking at the document:

1. Name the five `wsStatus` values in order, and what protocol event causes
   each transition.
2. Why does clicking the persona selector do nothing while a session is active?
3. What was wrong with the `flush.ack` message and how was it fixed?
