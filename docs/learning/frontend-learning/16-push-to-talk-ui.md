# 16 - Push-to-talk in the browser, and the demo fixes

Branch `fix/frontend-demo` (from `dev`, uncommitted). Implements the browser side of
shared protocol v0.9; `docs/contracts.md` is unchanged.

## 1. What

The server has had push-to-talk since `backend-learning/17-push-to-talk.md`, but the
browser could not use it. This PR adds a mode choice before connect ("Hands-free" or
"Push-to-talk", sent as `session.start`'s `mode`) and a Speak/Stop button with Space
as hold-to-talk. It also fixes four demo bugs: the orb said "Tap connect" while
connected, `TTS_FAILED` wiped the reply text, frames of a flushed turn could still
play, and a reply cut after `agent.done` was not marked "Interrupted".

## 2. Why

Push-to-talk avoids the 700 ms silence wait and the false barge-ins seen in the
2026-10-08/09 live demo (PROJECT.md, known gaps), but only if the browser can drive it.
The four bugs are visible in a recorded demo. Nothing was measured: no real session
ran in a browser for this PR. The time from local stop to the server's `audio.flush`
is now logged in the browser console, so the demo recording can measure it.

## 3. How

1. **Mode.** `src/pages/ConversationPage.jsx` shows a mode picker next to the persona
   picker, locked while connected. `src/hooks/useAudioCapture.js` puts the mode in
   `session.start`. The UI then follows the mode in `session.started`, because the
   server decides: an older server answers without one, which means hands-free.
2. **Mic and frames.** The mic opens once at connect, as before. The *AudioWorklet*
   (`public/audio-processor.js`, code that runs on the browser's audio thread) keeps
   making 20 ms frames. In a ptt session the hook sends them only during a press.
3. **The press.** `src/ptt/pttPress.js` is a *state machine*: a value that can only
   be in one of a few named states, with fixed moves between them. Here they are
   idle, holding and stopping. Speak moves idle to holding and sends `ptt.start`.
   Stop moves holding to stopping. Any other press is ignored.
4. **The last frame.** On stop, the worklet still holds up to 19 ms of audio, too
   little for a frame. The hook asks it (a message on its *port*, the channel between
   the two threads) to send that audio as one last frame, padded with silence, then a
   marker. A port delivers messages in the order they were sent, so when the marker
   arrives every frame of the press is already on the socket. Only then does
   `ptt.end` go out. If no marker arrives within 300 ms (`PTT_END_FALLBACK_MS`,
   `src/config.js`), `ptt.end` is sent anyway, with a `console.warn`.
5. **Speak over the agent.** The hook remembers the agent's turn while `turn.state`
   says thinking or speaking. Pressing speak then marks that turn flushed, stops
   playback (`flushPlayback`, `src/hooks/usePlaybackQueue.js`), and marks the reply
   interrupted, all before sending `ptt.start`. When the server's `audio.flush`
   arrives, it is handled as before, and `console.info` logs the gap in ms.
6. **Dropping a flushed turn.** `src/turnState/turnFilter.js` keeps the set of flushed
   turns, plus the turn of the latest `audio.start`. Audio frames carry no turn id;
   they belong to that turn. The hook drops frames, `audio.start`, `audio.end`,
   `agent.text` and `agent.done` of a flushed turn before the page sees them.
   `turn.state`, transcripts and errors always pass.
7. **The button.** `src/components/PttButton.jsx`: a click toggles Speak and Stop.
   Space: key down starts, key up stops. Holding a key fires repeated key-down events
   (*auto-repeat*); these carry a repeat flag and are ignored. Space does nothing
   while typing in a field. Its default action is blocked, because Space would
   otherwise scroll the page or click the focused button a second time.
8. **Text fixes.** `src/components/VoiceOrb/VoiceOrb.jsx` picks its connected
   subtitles by mode. On an `error`, the page keeps the streamed reply as a transcript
   line, instead of clearing it. `src/hooks/useTranscript.js` stores each reply's
   turn id, so a later `audio.flush` can mark a finished reply interrupted.

## 4. When

- **Connect:** the mode goes out in `session.start`; `session.started` confirms it.
- **Every 20 ms frame:** sent in hands-free mode; in ptt mode, only while holding or
  stopping.
- **Speak press:** local stop if the agent is busy, then `ptt.start`.
- **Stop press:** last-frame request, then `ptt.end` on the marker (or after 300 ms).
- **Every server message:** the flushed-turn filter runs first.
- **Disconnect:** an open press is dropped without sending anything.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Marker from the worklet before `ptt.end` | Wait a fixed delay, then send `ptt.end` | Too short cuts the last syllable; too long adds wait to every turn. The marker is exact |
| Pad the last partial frame with silence | Drop the partial frame | Loses up to 19 ms of the user's last sound; the padding is at most 20 ms of silence |
| Keep the mic open, skip frames between presses | Start and stop the mic track on each press | The contract asks for one open track; reopening costs permission and device start-up time and restarts echo cancellation |
| Stop playback locally on speak | Wait for the server's `audio.flush` | One network round trip of agent voice over the user, plus the server's time to react |
| Set of flushed turn ids | One true/false flag (the old code) | Any `audio.start` cleared the flag, so it could not tell an old turn from a new one |
| Space hold-to-talk, button toggle | Space toggles like the button | Holding a key is the usual walkie-talkie gesture; a toggle key is easy to leave on |
| Small plain modules for the press and the filter | Logic inline in the hook | The frontend tests are plain Node scripts; Node cannot run a React hook or a worklet |

## 6. Known issues

- Not run in a browser: the worklet marker, Space handling, local stop and sound are
  checked only by reading the code. `npm test` covers the press states (33 checks)
  and the filter (20 checks), not the hook.
- Stop press to first audible sample: not measured. Local stop to `audio.flush`: logged,
  not measured.
- The first frame of a press can carry up to 19 ms of audio from just before the press.
- `useAudioCapture.js` grew from 369 to 505 lines, past the ~300 limit; split after
  phase 1 (PROJECT.md, known gaps).
- After `TTS_FAILED`, the kept reply looks like a normal line; only the banner says it
  was not spoken.
