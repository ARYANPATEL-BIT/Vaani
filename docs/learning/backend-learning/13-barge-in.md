# Barge-in: the user talks, the agent stops

## 1. What we built in this branch

Branch `feat/barge-in`. Until today the backend was **half-duplex**: while the agent
was thinking or speaking, the user's speech was detected and thrown away. Now, if
the user talks over the agent for 200 ms, the agent goes quiet at once. Its model
stream and any speech synthesis still running are cancelled, and the user's speech
becomes their next turn, starting from its first sound. History keeps only the part
of the reply the user actually heard. `dev.flush`, the fake trigger used since day 4,
is gone (shared protocol v0.7). `fake_client.py --barge-in-after MS` replaces it as
the harness for the real path.

## 2. What we used to build it

- **Barge-in.** *What:* interrupting a speaking voice agent by talking.
  *Here:* `vaani/barge_in.py` judges the speech and stops the reply.
  *Why:* the spec makes it a must (US-002, PERF-3/4/5).
- **A speech-frame counter (the "judge").** *What:* a count of 20 ms frames whose
  Silero speech probability is at least `[barge_in].threshold`.
  *Here:* `BargeIn.push`. *Why:* a cough also fires VAD's `speech_started`
  (80 ms), so `speech_started` alone would let any noise stop the agent.
- **Cancellation token** (see `06-cancel-failover.md`). *What:* an `asyncio.Event`
  that a long job checks, and stops when it is set.
  *Here:* `Responder.cancel()` sets the reply's token, and every send in `reply.py`
  and `speaker.py` checks it first. *Why:* one flag stops the model stream, the
  synthesis result and the frames at the same moment.
- **Replay.** *What:* feeding saved frames, with their VAD events, into the
  endpointer later, as if they had arrived live.
  *Here:* `TurnPipeline._barge_in`, step 5.
  *Why:* the endpointer counts frames, not seconds, so a replay gives the same
  result as live feeding, pre-roll included.
- **Play-out estimate.** *What:* the server's guess of when the browser plays each
  chunk. A chunk starts when the previous one ends, or "now", and it lasts
  samples ÷ sample_rate. *Here:* `Speaker.say` stores it in `spoken`, and
  `heard_text` reads it. *Why:* the browser doesn't report playback position.
- **`typing.NamedTuple`**: `Spoken(text, start, end)` reads as `chunk.end`, not `chunk[2]`.
- **A set of tasks plus `add_done_callback`.** *What:* the usual asyncio way to
  keep track of background tasks. Each task removes itself from the set when it
  ends. *Here:* `Responder._tasks`. *Why:* a cut reply is no longer awaited, so
  more than one reply task can be alive at once, and `close()` must wait for all
  of them.
- **`time.perf_counter`** (see `03-echo-telemetry.md`): the server-side barge-in timings.
- **uvicorn in a thread + the `websockets` client** (test only): `test_fake_client.py`
  runs the real `fake_client.main` against the app on a free port (never 8000).

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| Trigger | 200 ms of speech frames from onset | (a) `speech_started` alone (80 ms); (b) wait for a word from ASR; (c) duck the volume at onset, stop on confirm | (a) every cough stops the reply; (b) a CPU partial costs about as much as a final, which is seconds; (c) needs a new `audio.duck` message and frontend work | A "hmm" of 300 ms or more still stops the agent |
| What to count | Frames at or above `threshold` | Time since `speech_started` | VAD stays "in speech" for 200 ms after the sound stops, so a 100 ms cough would look like 300 ms | Probability is updated every 32 ms (Silero's chunk), so the count lags slightly |
| Order of the stop | Token, then `audio.flush`, then everything else | The spec's order: cancel the stream, flush the queue, stop playback last | The user judges the interruption by when the speaker goes quiet | Nothing; the token is set without an await, so it costs microseconds |
| Waiting for the cut reply | Don't wait; the task ends on its own | Await it inside `on_frame`, as `dev.flush` used to | That stalls the frame loop for up to one synthesis while the user is mid-sentence | `close()` must track several tasks (`_tasks`) |
| The new turn's audio | Hold frames while judging; replay them into the endpointer | (a) feed the endpointer live and throw away its turn if it turns out to be noise; (b) start the turn at the trigger frame | (a) more branches in `turns.py`, which was already over 300 lines; (b) loses the first 200 ms, i.e. the first word | The endpointer sees the frames up to 200 ms late (it only counts frames, so the result is the same) |
| What "heard" means | Play-out estimate at the moment `audio.flush` went out | (a) the full reply; (b) a `played_ms` field in `flush.ack` | (a) the model would "remember" saying things the user never heard; (b) needs frontend work, and is wrong until the browser plays at the declared rate anyway | About 27% over-count today (section 6) |
| Cut before anything was heard | Carry the transcript into the next reply | Drop it | "Set an alarm [pause] for 8" would reach the model as "for 8" | A carried question is answered together with whatever came next |
| `dev.flush` | Removed (v0.7) | Keep it alongside barge-in | Two triggers for one cancel path; the contract promised it would go | Manual testing needs the real path (`--barge-in-after`) |
| `playback.done` from the browser | Not added | A new message when audio finishes playing | Barge-in doesn't need it: if `idle` comes ~100 ms early, speech then becomes a normal turn | `speaking` can end before the speaker is really quiet |

## 4. Where things live

| What | File | Function or class |
|---|---|---|
| Config read (`min_speech_ms`, `threshold`) | `backend/config.toml` `[barge_in]`, `backend/vaani/config.py` | `BargeInSettings` |
| Who gets each frame (routing seam) | `backend/vaani/turns.py` | `TurnPipeline.on_frame`, `_watch` |
| Is it an interruption? Frames held | `backend/vaani/barge_in.py` | `BargeIn.push`, `take` |
| Stop: token, `audio.flush`, history, timing log | `backend/vaani/barge_in.py` | `stop_reply` |
| Close the agent turn, open the user's, replay | `backend/vaani/turns.py` | `TurnPipeline._barge_in` |
| What was heard | `backend/vaani/barge_in.py`, `backend/vaani/speaker.py` | `heard_text`, `Speaker.spoken` / `Spoken` |
| History written | `backend/vaani/session.py`, `backend/vaani/reply.py` | `Session.remember`, `Responder.remember` |
| Carried words | `backend/vaani/turns.py` | `_carried`, `_on_final`, `_discard_turn`, `_reply` |
| Legal state moves | `backend/vaani/turn_state.py` | `_LEGAL` (`cancelling -> listening` only) |
| Late `flush.ack` accepted | `backend/vaani/session.py` | `Session.handle_flush_ack` |
| Span name | `backend/vaani/telemetry.py` | `BARGE_IN` |
| Wire format (no new message) | `backend/vaani/protocol.py`, `docs/contracts.md` §2.7 | docstring v0.7 |
| Harness | `backend/scripts/fake_client.py` | `barge_in_run`, `--barge-in-after` |
| Tests | `backend/tests/test_barge_in.py`, `test_flush.py`, `test_fake_client.py` | |

No database layer: history lives only in memory, in `Session.history`.

## 5. How it works

**The routing seam.** Every frame passes through VAD first. Then, in
`backend/vaani/turns.py`, `on_frame`:

```python
if self._machine.state in (TurnState.THINKING, TurnState.SPEAKING):
    await self._watch(data, speech_event)
else:
    if self._barge.judging:
        for frame, event in self._barge.take():
            await self._endpoint(frame, event)
    await self._endpoint(data, speech_event)
```

When the agent is busy, frames go to the judge. The `else` branch handles a race.
Speech can start over the reply, and the reply can finish before that speech has
been judged. That speech is the user's next turn, so its held frames go to the
endpointer first, and its first word is kept.

**Judging.** In `backend/vaani/barge_in.py`, `BargeIn.push`:

```python
if self.started is None:
    if event is None or event.kind != SPEECH_STARTED:
        return False
    self.started = event
    self._speech = self._start_frames
elif event is not None and event.kind == SPEECH_ENDED:
    self.started = None  # it stopped short: a noise, not an interruption
    return False
elif probability >= self._threshold:
    self._speech += 1
return self._speech >= self._needed
```

`_needed` is 200 ms ÷ 20 ms = 10 frames. VAD needed 4 speech frames in a row to
fire `speech_started`, so counting starts at 4. Six more speech frames fire it.

`_watch` hands the frames of a noise (or of plain silence) to the endpointer as
silence: `self._endpointer.push(frame, None)`. Two things follow. The endpointer now
really sees every frame, which its docstring always required. And its pre-roll is
fresh audio when the next turn opens.

**Stopping (steps 1 to 3).** In `backend/vaani/barge_in.py`, `stop_reply`:

```python
triggered = telemetry.record(BARGE_IN, turn_id).at
responder.cancel()
await session.flush(send_json, telemetry)
cut_at = perf_counter()
```

`cancel()` is synchronous and has no await before it. From that line on, every send
in `reply.py` and `speaker.py` sees the token and sends nothing. The token is a
flag, not a message, so `audio.flush` is still the first thing the browser receives.

Steps 2 and 3 need no code here. Setting the token is what does them:
- The chain races each read against `cancel.wait()` and closes its stream (day 6).
- `Speaker.say` throws away a synthesis that returns after the cut. It has a check
  directly after `await self._synth.synthesize(...)`.

**History.** `heard_text` walks the chunks' play-out windows. A chunk that ended
before `cut_at` was heard whole. The chunk that was playing is cut by the share of
its play-out time that had passed, then trimmed back to a whole word.

```python
if not started:
    return ""
if not heard:
    return responder.transcript
responder.remember(responder.transcript, heard)
return ""
```

So the function returns one of three things:
- **The reply had not started** (the transcript was still being made): `""`.
  `_on_final` will carry that transcript when it arrives.
- **Nothing was heard:** the transcript, to carry into the next reply.
- **Something was heard:** `""`, after writing that part to history.

The normal ending in `reply.py` changed to match. A reply is now remembered only
after it has **played**, right before `idle`, with no await in between:

```python
if cancel.is_set():
    return  # cut while playing: the barge-in recorded what was heard
self.remember(transcript, reply)
await self._move_to(TurnState.IDLE)
```

Before today it was remembered when `agent.done` was sent. A cut during the
play-out would then have left the full text in history.

**Steps 4 and 5.** In `backend/vaani/turns.py`, `_barge_in`:

```python
await self._machine.move_to(TurnState.CANCELLING)
await self._open_turn()
for frame, event in self._barge.take():
    await self._endpoint(frame, event)
```

`_open_turn` makes the new `turn_id`. It exists only because speech started.
The replay runs through `_endpoint`, so the endpointer opens the utterance on the
replayed `speech_started` frame, with its 300 ms pre-roll. The test
`test_the_new_turn_starts_at_the_first_sound_of_the_interruption` checks this frame
by frame.

**Carried words.** A turn that was cut before any of its reply was heard is
answered by the next reply, together with what came next (`_reply`). One case
needs extra care: the next turn is too short to count (a "hmm" under
`min_utterance_ms`). In that case `_discard_turn` goes to `thinking` and answers
the carried words alone. If their transcript hasn't arrived yet, it sets
`_answer_carried`, and `_on_final` answers them when it does.

With the default settings the "too short" case can't actually happen. A barge-in
is at least 10 speech frames. The endpointer measures from `speech_started` to the
end of VAD's 10-frame silence wait, so even the shortest barge-in measures
10 + 7 = 17 frames, i.e. 340 ms. That's over the 300 ms minimum. The test raises
`min_utterance_ms` to reach the case.

**The races you named, and what happens:**

| Speech is judged an interruption... | Result |
|---|---|
| during first-chunk synthesis (`thinking`) | `audio.flush` with no `audio.start` before it; the synthesis finishes and is thrown away; nothing heard, so the transcript is carried |
| while `agent.done` is being sent | the token is set, so `finish()` is skipped and no `audio.end` is sent; history gets what was heard |
| after `agent.done` and `audio.end`, still playing | still `speaking` (play-out estimate), so a normal cut: `audio.flush` follows `audio.end` |
| as the reply ends, before judging finishes | no cut; the held frames become the user's next turn |

**Measured** (fakes, real Silero, `localhost`). These are not PERF numbers:

- **Server-side, one harness run** (`test_fake_client.py`): `speech_started` ->
  `audio.flush` sent took **153.9 ms**. That's 152.9 ms of judging and 1.0 ms of
  stopping.
  - Judging took longer than the 120 ms minimum, probably because some frames of
    the clip scored under 0.5. Not checked.
  - The client measured its first speech frame -> `audio.flush` received at
    **315 ms**.
  - The `flush.ack` round trip was 7.9 ms.
- **Live run, a single run** (`fake_client.py --barge-in-after 300`; real Silero,
  large-v3 on CUDA, Gemini, Piper): server-side **129.6 ms** (judging 128.7,
  stopping 0.9); client **288 ms**; ack round trip 6.0 ms; order matched v0.7;
  1 Gemini request. Logs: `docs/findings/barge-in/barge_in_live_20261006-152217_server.txt`
  and `docs/findings/barge-in/barge_in_live_20261006-152217_client.txt`.
- **PERF-3 is not measured.** It is measured at the speaker, which needs a
  barge-in loopback rig that doesn't exist yet.
- **`on_frame` cost** (2,800 silent frames × 3 runs each):
  - idle path, p50 / p95: 99.5 / 118.0 µs before; 99.6–99.9 / 116.9–119.3 µs after;
  - busy path, p50 / p95: 98.1 / 114.6 µs before; 98.5–98.9 / 115.0–117.8 µs after.
  - No regression beyond noise. The mic-stop -> first-audio path is unchanged.

## 6. When things go wrong

| What fails | What the code does | What the user sees |
|---|---|---|
| A cough or click (under 200 ms) | Judge resets on `speech_ended`; frames go to the endpointer as silence | The reply carries on |
| A "hmm" of 300 ms or more | Barge-in | The agent stops; the "hmm" is a turn, answered together with any carried words |
| Socket closes during the stop sequence | The send raises; the gateway's `finally` calls `close()`, which waits for every reply task | Nothing (they're gone) |
| The cut turn's transcript fails (`ASR_FAILED`) | `_on_final(..., None)` carries nothing | `ASR_FAILED`; the next turn is answered alone |
| The model errors while the cut is happening | `_error_then_idle` checks the token after its send and leaves the state alone | `LLM_FAILED`, then the new turn's `listening` |

**Known issues.** None of these is fixed in this branch.

1. **Chrome's echo cancellation on Web Audio output is unverified.**
   - The mic uses `echoCancellation: true` (`useAudioCapture.js`), but the agent
     plays through an `AudioContext`, not a WebRTC stream.
   - If AEC doesn't cancel that output, the agent hears itself and stops itself.
     The guard is `[barge_in].threshold`, and it is 0.5, the same as VAD, so today
     it guards nothing.
   - Day 14 needs a run with speakers on, no one talking and a long reply. Every
     barge-in in that run is self-interruption. Headphones are the spec's fallback
     (TR-2).
2. **A "hmm" stops the agent, then gets answered.** Anything past 200 ms
   interrupts. Then VAD's 200 ms end hangover counts toward `min_utterance_ms`
   (`_finish` measures `speech_started` to the `speech_ended` confirmation), so
   every barge-in turn is at least 340 ms and passes the 300 ms minimum. The
   pre-roll is not counted. Fix on day 14: count voiced frames only.
3. **History over-counts "heard" by about 27%** until the frontend plays at the
   rate `audio.start` declares. It plays 22050 Hz audio at 16000 Hz
   (`contracts.md` §2.2), so after t seconds it has played only
   16000/22050 = 72.6% of what the estimate says. The estimate also ignores
   network, browser and device latency, which over-counts a little more.
4. **PERF-3 budget: a decision for the mentor.** The client already sees
   315 ms (fakes) and 288 ms (live run) to `audio.flush` received, against a
   300 ms target at the speaker. `min_speech_ms` (200) plus VAD's confirmation
   (~80) use it up by design. Options: a lower `min_speech_ms`, duck-then-stop,
   or moving the target.
5. **Over 300 lines:** `config.py` 340 (was 327; `[barge_in]`, as agreed);
   `fake_client.py` 381 (was 313; the harness added 68). `turns.py` is 323 (was 324).
6. **The stream of a reply cut during synthesis closes late.** It closes when that
   synthesis returns, which can take up to one chunk, because the task is blocked
   inside it. Not measured on Piper.
7. **After a forced 30 s turn end**, the endpointer's utterance stays open while
   the agent thinks; frames pushed then join it. Untested, as before today.
8. **Echo's flush gate is unreachable** (`echo.py`): nothing flushes a user turn now.
9. **The PDF's barge-in diagram (p. 23) draws stop-playback last;** see `contracts.md` §2.7.
10. **Live coverage is thin.** The reply to the interruption (carried words, the
    second Gemini call) has run only against fakes: the live session closed while
    that turn was still thinking. The live numbers come from a single run.

## 7. New terms

- **AEC (acoustic echo cancellation)**: removes the speaker's sound from the mic
  signal. If it fails, the agent can interrupt itself.
- **Barge-in**: the user talking over the agent, and the agent stopping.
- **Carried words**: a cut user turn's transcript, held in `TurnPipeline._carried`
  and sent with the next reply's request.
- **Half-duplex / full-duplex**: one side talks at a time, versus both at once.
- **Held frames**: frames `BargeIn` keeps while judging, so a turn starts at its first sound.
- **Judging**: the up-to-200 ms between `speech_started` and the decision.
- **PERF-3**: the spec's barge-in stop latency, 300 ms, measured at the speaker.
- **Play-out window**: the server-clock time span a chunk should play in.
- **Pre-roll**: the 300 ms before `speech_started`, kept because VAD confirms 80 ms late.
- **Replay**: feeding held frames, with their VAD events, into the endpointer later.
- **Self-interruption**: the agent's own voice leaking into the mic and barging in.

## 8. Questions you could be asked

1. **Where is the code that decides a sound is an interruption?**
   `BargeIn.push`, in `backend/vaani/barge_in.py`. It's called from
   `TurnPipeline._watch` in `turns.py`.
2. **Where does the agent actually go quiet?** `stop_reply` in `barge_in.py` calls
   `session.flush`, which sends `audio.flush`. The browser fades out within 10 ms.
3. **What happens if the user coughs?** VAD may fire `speech_started`. Fewer than
   10 speech frames follow, then `speech_ended`, so the judge resets and the reply
   carries on (`test_a_short_noise_does_not_stop_the_reply`).
4. **What happens if the browser's echo cancellation fails?** The agent's voice
   reaches the mic, and if it lasts 200 ms the agent stops itself. Nothing in the
   code prevents that today except a threshold that is still at its default. See
   known issue 1.
5. **Why not wait for the cancelled reply to finish before opening the new turn?**
   A synthesis that is already running can't be interrupted. Waiting would freeze
   the frame loop for up to one chunk while the user is talking. The token already
   guarantees the old task sends nothing and never changes the state.
6. **Why does the token get set before `audio.flush`, if flush must be first?**
   Setting the token sends nothing; it's a memory write. If the flush went first,
   the speaker task could run during its `await` and send one more frame after the
   flush.
7. **What does "heard" mean, and what's wrong with it?** It's what the play-out
   estimate says had played when `audio.flush` went out. It ignores network and
   device latency, assumes the browser plays at the declared rate (today it
   doesn't: about 27% too much), and assumes every character takes the same time
   to say.
8. **Why was `cancelling -> idle` removed?** Only a barge-in reaches `cancelling`
   now, and its speech always opens a new turn. The removed path was `dev.flush`.
   Session end and disconnect never move the state. The failure endings
   (`LLM_FAILED`, `TTS_FAILED`, `INPUT_REJECTED`, `ASR_FAILED`) all go
   `thinking`/`speaking -> idle`.
9. **Why is the `flush.ack` of an older turn now accepted?** A barge-in opens the
   new turn microseconds after the flush, so the ack always arrives after that.
   The old "current turn only" check would have thrown every barge-in ack away.
10. **What does "replay" mean, and why does it give the same result?** The held
    frames are pushed into the endpointer with their original VAD events. The
    endpointer counts frames, not seconds, so pushing them late changes nothing.
11. **Hardest: a question, a 1 s pause, then "hmm" before the question has even
    been transcribed. What happens?** The barge-in fires in `thinking`. No reply
    exists yet, so nothing is carried yet. Say the "hmm" is too short:
    `_discard_turn` sees the question's final is still awaited and sets
    `_answer_carried`. When the transcript arrives, `_on_final` carries it and
    answers it under the new turn's id
    (`test_hmm_while_the_question_is_still_transcribing_answers_it`).

## 9. Check yourself

1. Say the five barge-in steps in order. For each one, name the function that does it.
2. Why does the judge count speech frames instead of time since `speech_started`?
3. A reply is cut 0.3 s into a 0.5 s chunk "Theek hai,". What goes into history, and why?
