# Audio Playback Flush

## 1. In one minute

Audio flushing allows the server to silence the browser speaker immediately when a conversation interruption occurs.
When an `audio.flush` message arrives over the WebSocket, the browser stops all scheduled and playing audio,
applies a 10 ms click-free fade-out, resets its scheduling clock cursor to zero, and returns an `audio.flush.ack`
acknowledgement containing its high-resolution timestamp.

## 2. Files

| File | Responsibility |
|---|---|
| `docs/contracts.md` | Formalises the `audio.flush` command and `audio.flush.ack` control message schemas and payloads. |
| `frontend/src/hooks/usePlaybackQueue.js` | Tracks active `AudioBufferSourceNode` and `GainNode` instances, stops them with a 10 ms linear fade, and resets `nextStartTimeRef`. |
| `frontend/src/hooks/useAudioCapture.js` | Parses the `audio.flush` JSON frame, invokes `onFlushCommand`, and sends the `audio.flush.ack` payload. |
| `frontend/src/pages/ConversationPage.jsx` | Binds `flushPlayback` from `usePlaybackQueue` into `startCapture` in `useAudioCapture`. |

## 3. How it works

```mermaid
sequenceDiagram
    participant S as Server
    participant C as useAudioCapture
    participant Q as usePlaybackQueue
    participant G as GainNode & Source
    S->>C: JSON {"type": "audio.flush"}
    C->>Q: flushPlayback()
    Q->>G: gain.linearRampToValueAtTime(0, now + 0.01)
    Q->>G: source.stop(now + 0.01)
    Q->>Q: activeSourcesRef.clear(); nextStartTimeRef = 0
    C->>S: JSON {"type": "audio.flush.ack", "timestamp_ms": ...}
```

### Flush Order
1. **Receive and validate**: `useAudioCapture.js` detects a JSON message with `msg.type === 'audio.flush'`.
2. **Execute flush callback**: `onFlushCommand()` invokes `flushPlayback()` in `usePlaybackQueue.js`.
3. **Fade-out and stop active sources**: For each active source, a 10 ms linear ramp drops gain to 0, then `source.stop()` halts playback.
4. **Clear tracked sources**: `activeSourcesRef.current.clear()` wipes all tracked references.
5. **Reset scheduling cursor**: `nextStartTimeRef.current = 0` resets the playback timeline so future chunks start immediately.
6. **Acknowledge**: `useAudioCapture.js` checks if the WebSocket is open and immediately sends `audio.flush.ack` with `performance.now()`.

### Implementation Snippets

In `frontend/src/hooks/usePlaybackQueue.js`, every chunk is paired with an inline `GainNode` and tracked in `activeSourcesRef`:
```javascript
const source = ctx.createBufferSource();
source.buffer = audioBuffer;

const gainNode = ctx.createGain();
source.connect(gainNode);
gainNode.connect(ctx.destination);

source.start(startAt);

const sourceData = { source, gainNode };
activeSourcesRef.current.add(sourceData);

source.onended = () => {
  activeSourcesRef.current.delete(sourceData);
  gainNode.disconnect();
};
```

When flushed, `flushPlayback()` fades out and halts every source safely:
```javascript
const flushPlayback = useCallback(() => {
  if (!audioCtxRef.current) return;
  const ctx = audioCtxRef.current;
  const now = ctx.currentTime;
  const fadeDuration = 0.01; // 10 ms fade-out

  activeSourcesRef.current.forEach(({ source, gainNode }) => {
    try {
      gainNode.gain.setValueAtTime(gainNode.gain.value, now);
      gainNode.gain.linearRampToValueAtTime(0, now + fadeDuration);
      source.stop(now + fadeDuration);
    } catch {
      // Ignore if already stopped or invalid state
    }
  });

  activeSourcesRef.current.clear();
  nextStartTimeRef.current = 0;
}, []);
```

In `frontend/src/hooks/useAudioCapture.js`, the message triggers the flush and sends the acknowledgement:
```javascript
} else if (msg.type === 'audio.flush') {
  if (typeof onFlushCommand === 'function') {
    onFlushCommand();
  }
  if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
    try {
      socketRef.current.send(
        JSON.stringify({
          type: 'audio.flush.ack',
          timestamp_ms: performance.now(),
        })
      );
    } catch (ackErr) {
      console.warn('[useAudioCapture] Failed to send flush ack:', ackErr);
    }
  }
}
```

## 4. New concepts

- **Scheduled audio sources**: `AudioBufferSourceNode` objects scheduled on the audio clock via `start(when)` to play in the future.
- **AudioBufferSourceNode.stop()**: A Web Audio method that permanently terminates playback of a buffer source node at a given clock timestamp.
- **Audio clock (`AudioContext.currentTime`)**: A steady hardware-driven time in seconds since the audio context started, unaffected by JavaScript event loop delays.
- **Short fade (Gain Ramp)**: Smoothly reducing audio amplitude to zero across 10 ms (`linearRampToValueAtTime`) to avoid loud clicks caused by abrupt waveform cuts.
- **High-resolution timestamp (`performance.now()`)**: A monotonic floating-point timestamp measured in milliseconds since document origin, ideal for network latency tracking.

## 5. Why this and not that

| Choice | Picked | Alternatives | Why not them |
|---|---|---|---|
| Source tracking | `Set` of `{ source, gainNode }` references | Global array or recreating `AudioContext` | Closing and reopening `AudioContext` violates autoplay gesture restrictions and adds hundreds of milliseconds of latency. A `Set` gives O(1) tracking and clean cleanup. |
| Click prevention | Per-source `GainNode` with 10 ms ramp | Master `GainNode` or abrupt `source.stop(0)` | Abrupt stops cause loud speaker pops. A shared master gain node would silence incoming audio arriving right after the flush. |
| Acknowledgement trigger | Sent in `useAudioCapture` after `onFlushCommand` | Sent inside `usePlaybackQueue` | `usePlaybackQueue` focuses exclusively on Web Audio and has no WebSocket coupling. Keeping transport in `useAudioCapture` maintains clean separation. |

## 6. When things go wrong

| Failure Scenario | Behaviour in Code |
|---|---|
| Flush received with empty queue | `activeSourcesRef` is empty; the loop does nothing, cursor resets to 0, and `audio.flush.ack` is sent immediately without error. |
| Source already stopped before flush | `source.stop()` inside the loop is wrapped in a `try/catch` block that catches and suppresses `InvalidStateError`. |
| WebSocket closed when sending ack | `socketRef.current.readyState === WebSocket.OPEN` guard skips sending, and an error catch logs a warning without throwing. |
| Malformed control JSON received | `try { JSON.parse(event.data) } catch` in `useAudioCapture.js` logs a warning and avoids crashing the stream. |
| Duplicate / repeated flush messages | Multiple flushes in succession safely clear empty sets and send sequential acks cleanly. |

## 7. Questions you could be asked

**1. Where is the code that stops currently playing audio?**
In `frontend/src/hooks/usePlaybackQueue.js` inside `flushPlayback()`, iterating through `activeSourcesRef.current` and invoking `source.stop(now + fadeDuration)`.

**2. Where is the acknowledgement sent?**
In `frontend/src/hooks/useAudioCapture.js` inside the `socket.onmessage` handler when `msg.type === 'audio.flush'`.

**3. Why does the flush order matter?**
Fading and stopping must occur before resetting `nextStartTimeRef.current = 0`. If `nextStartTimeRef` were reset before stopping old sources, any chunk enqueued during the flush could collide with still-playing audio.

**4. Why is a 10 ms fade applied instead of calling `source.stop(0)` immediately?**
Abruptly cutting off an audio wave away from its zero-crossing point creates a discontinuous waveform step, which speakers output as an audible pop or click. A 10 ms linear ramp to 0 eliminates the transient.

**5. What happens if Aryan's backend sends another audio chunk immediately after the flush?**
Because `nextStartTimeRef.current` was reset to `0`, `Math.max(ctx.currentTime, nextStartTimeRef.current)` evaluates to `ctx.currentTime`, and the new audio begins playing without delay.

**6. What happens if `source.stop()` throws an error because the buffer already ended?**
The call is enclosed in a `try/catch` block inside the loop, preventing an individual node error from blocking the rest of the queue or crashing the app.

**7. Why use `performance.now()` instead of `Date.now()` for the timestamp?**
`performance.now()` is monotonic and cannot jump backwards if the user's system clock syncs. It also provides microsecond precision.

**8. Why not close and recreate the `AudioContext` on flush?**
Creating a new `AudioContext` in browsers often requires a fresh user gesture (click) due to autoplay policies, and context recreation introduces perceptible latency (often 100+ ms).

**9. What happens if the WebSocket disconnects during a flush?**
The readyState check prevents calling `.send()` on a non-open socket, and the error catch logs safely without uncaught exceptions.

**10. What is the hardest part of this implementation?**
Ensuring that already-scheduled future buffers and actively-playing buffers are both terminated while leaving the audio context open and ready to schedule new buffers at `ctx.currentTime`.

## 8. Check yourself

1. What data structure tracks active audio sources and why?
2. Why must `nextStartTimeRef.current` be reset to `0` when flushing?
3. What is the exact payload sent in the client flush acknowledgement?
