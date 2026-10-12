# 17 - Push-to-talk: the user's button, not their silence, ends the turn

Branch `feat/push-to-talk1` (from `dev`, uncommitted). Shared protocol v0.9.

## 1. What

Vaani had one way to talk to it: hands-free. The server listens all the time, decides
on its own when you start and stop speaking, and stops the agent when you talk over it.
This branch adds a second way, **push-to-talk** (ptt): you press "speak", talk, and press
"stop", like a walkie-talkie. The browser chooses the mode once, in `session.start`
(`"mode": "vad"`, the default, or `"ptt"`). A ptt session adds two messages, `ptt.start`
and `ptt.end`. Hands-free sessions behave exactly as before. The exact messages, fields
and edge cases are in [`docs/contracts.md`](../../contracts.md) section 2.8.

## 2. Why

In hands-free mode, two guesses stand between you and the answer. **Endpointing**
(deciding that you have finished) waits for 700 ms of silence after your last word
(`[endpoint].end_of_turn_silence_ms` in `backend/config.toml`). That wait is part of
every turn's latency. A **barge-in** (stopping the agent when you talk) is judged from
sound, so noise can also trigger it. PROJECT.md records false barge-ins from noise and
echo in the 2026-10-08/09 live demo. In ptt mode you make both decisions yourself: the
stop press ends the turn with no wait, and only a press interrupts the agent.

What was measured: the per-frame cost of hands-free mode before and after this branch
(below). It did not change. What was **not** measured: the time from stop press to the
first audible sample. That needs a real run with Groq and Piper, which was not done.
The 700 ms saving is by design, not a measurement.

| `on_frame` p50 / p95, microseconds (3 runs each, median shown) | before | after |
|---|---|---|
| idle, silent frames | 101.4 / 124.1 | 102.0 / 129.7 |
| idle, speech fixture | 102.8 / 125.0 | 102.8 / 126.8 |
| agent speaking, silent frames | 102.0 / 140.7 | 103.7 / 128.7 |

Source: `docs/findings/push-to-talk/measure_on_frame_20261012-143143.txt` (before) and
`..._143146.txt` (after). Both were run back to back under the "Silent" power scheme.
Both files carry the same commit line. The `vaani imported from` line tells them apart.

## 3. How

1. **Mode.** `vaani/gateway.py` reads `mode` from `session.start` and stores it on the
   `Session` (`vaani/session.py`). A second `session.start` changes nothing.
   `session.started` sends back the mode that is actually in force.
2. **Pipeline choice.** `vaani/turns.py` builds the session's pipeline once. In ptt mode
   it builds a `PttBuffer` (`vaani/ptt.py`) *instead of* the `Endpointer`
   (`vaani/endpoint.py`), so the silence rule never runs.
3. **Speak pressed.** The gateway passes `ptt.start` to `TurnPipeline.on_ptt_start`.
   - If the agent is idle, a new turn opens and the state becomes `listening`.
   - If the agent is thinking or speaking, the same barge-in runs as in hands-free
     mode: `_interrupt` in `turns.py` calls `stop_reply` in `vaani/barge_in.py`. So
     `audio.flush` goes out first, then the model stream and any running synthesis
     stop, and history keeps only what you heard.
   - Either way, VAD's memory is then wiped (`VadStream.reset`, `vaani/vad.py`) and
     the press opens.
4. **While pressed.** Each frame still goes through Silero VAD. That gives a speech
   probability: how sure the model is that the frame contains a voice. `PttBuffer`
   keeps the frame and counts it as *voiced* if that probability reaches
   `[vad].threshold`. Nothing here can end the turn, except the 30 s length cap.
5. **Stop pressed.** `on_ptt_end` closes the press.
   - If too few frames were voiced (below `[endpoint].min_utterance_ms`), the press
     was empty. It is dropped by the same `_discard_turn` that drops a cough in
     hands-free mode, and the state returns to `idle`.
   - Otherwise `PttBuffer` hands back the same kind of finished-turn record the
     endpointer produces, and from there everything is the normal path: Whisper,
     the model, chunking, Piper.

**Recurrent state.** Silero is a *recurrent* network. It carries a small memory from
one chunk of audio to the next, which is how it hears that a sound is continuing.
In ptt mode the browser sends no audio between presses. Without the reset, the second
press would start with a memory of audio that ended seconds earlier.
`tests/test_ptt.py` checks this: two presses of the same audio give exactly the same
probabilities, and with the reset turned off they do not.

## 4. When

- **`session.start`:** the mode is fixed, and the pipeline is built for it.
- **Every frame (ptt):** Silero runs, and the frame joins the open press. If no press
  is open, the frame is dropped. The client is not supposed to send such frames.
- **`ptt.start`:** a turn opens, or a barge-in runs first. VAD is reset.
- **`ptt.end`:** the turn ends at once and transcription starts. An empty press goes
  back to `idle`.
- **Socket closed during a press:** the press's audio is thrown away. Nothing is
  transcribed.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| `mode` as a field of **`session.start`** | A separate `session.mode` message | Audio could arrive before the mode does, and the pipeline would have to be rebuilt in the middle of a session. |
| Names **`ptt.start` / `ptt.end`** | `ptt.start` / `ptt.stop` | The protocol's pairs are already start/end (`session.*`, `audio.*`). A third pattern makes the protocol harder to guess. |
| Reuse **`BAD_MESSAGE`** for a ptt message in a vad session | A new `WRONG_MODE` error code | The frontend would need to handle one more code, for something only a client bug can cause. |
| A separate **`PttBuffer`** that repeats the empty-press rule | Drive the `Endpointer` with fake events and add an "end now" method to it | That needs three special cases inside endpointing: ignore VAD's own speech_ended, skip the pre-roll, and dodge its reopen-at-the-cap behaviour. The cost of our choice: one comparison now exists twice, kept in sync by comments in both files. |
| Call the **existing `stop_reply`** for a press barge-in | A ptt-only stop routine | The order (`audio.flush` first) is the most important part of a barge-in. Two copies of it could drift apart. |
| **Ignore** a second `ptt.start` | Restart the press | Holding a key down makes the browser repeat its keydown event. Restarting would throw away speech many times a second. |
| **Reset** Silero's memory at every press | Keep it from the previous press | The new press's first probabilities would depend on audio from seconds ago (the test shows they differ). |
| Keep **Silero running** to count voiced frames | Treat every press as speech | An empty press would send silence to Whisper, and Whisper tends to invent text on silence. |
| **Drop** frames outside a press without a reply | Send an error for each one | A misbehaving client would get 50 errors a second. |

## 6. Known issues

- No frontend yet: the button and mode choice are Samyak's side (contracts.md 2.8 is Proposed), so ptt runs only in tests.
- Stop press to first audible sample is not measured; it needs a real Groq + Piper run.
- `min_utterance_ms` is 40 ms (2 voiced frames), so a click or breath can pass the empty-press check and reach Whisper.
- No pre-roll: words spoken just before the press are lost; no partial transcripts in ptt mode (they are off in config anyway).
- `turns.py` is 399 lines, over the ~300 limit; a follow-up PR splits it (PROJECT.md, known gaps).
