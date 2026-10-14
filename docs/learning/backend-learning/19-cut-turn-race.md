# 19 - The cut-turn race: a transcript that arrives while a barge-in is still sending

Branch `fix/cut-turn-race` (from `dev`, uncommitted). No protocol change.

## 1. What

When the user interrupts the agent while it is still `thinking` (its transcript of the
user's question not yet ready), the server stops that turn and opens a new one. If the
question's transcript happened to arrive in the few moments while the server was still
sending the stop messages, the server answered the cut turn anyway. This branch makes
`vaani/turns.py` treat that late transcript as belonging to a cut turn: its words are
kept and answered once, with the user's next turn. It also corrects a stale sentence in
`docs/contracts.md` section 2.4.

## 2. Why

A **race condition** is a bug that depends on the order in which two things happen to
run. The server runs on one **event loop** (a single thread that switches between tasks).
A task keeps the loop until it reaches an `await` (a point where it waits, for example
for a message to be sent). At that point the loop may run any other task that is ready.

A barge-in sends `audio.flush`, then `turn.state cancelling`. Each send is an `await`.
During either one, the speech recogniser's task could deliver the cut turn's **final**
(its finished transcript). The old code still saw the cut turn as the current one, so it
started a reply for it. Reproduced in `backend/tests/test_cut_turn_race.py` before the
fix, the old code:

- made a second paid model call, for the cut turn;
- sent that reply's text and audio after `audio.flush` (the browser drops them);
- had the real reply to the user's new turn crash on an illegal state move
  (`idle -> speaking`), so the new turn was never answered aloud;
- if the recogniser **failed** in that window: moved `thinking -> idle` mid-barge-in,
  then crashed on `idle -> cancelling`, which ends the whole session.

The window is short, but pressing "speak" in push-to-talk during a slow transcription
lands in it. Latency: not measured (the change adds one set lookup per final).

## 3. How

1. **The signal already existed.** `Session.flush` (`vaani/session.py`) marks a turn as
   **flushed** before it sends `audio.flush`, and the mark never comes off. Only a
   barge-in flushes. So "flushed" means "this turn has been cut", from the very start of
   the stop.
2. **Guard 1, in `_on_final` (`turns.py`).** This is where the recogniser hands over a
   final, or `None` if transcription failed. A final for a turn that is not current,
   **or is current but flushed**, is treated as cut. Its words are added to the
   **carried** words (speech the user said but never heard answered), and no reply
   starts. A failed final adds nothing (`join_speech` in `vaani/barge_in.py` ignores
   `None` and empty text), so it no longer moves the state. When the guard catches the
   race, it logs one line: "final for turn ... arrived during its barge-in, carried".
3. **Guard 2, in `_interrupt` (`turns.py`).** After a cut question and then a too-short
   "hmm", the "hmm" turn waits in `thinking` for the question's words
   (`_answer_carried`). That flag used to be reset only after the stop messages had
   been sent. A barge-in on the "hmm" turn could then let the question's final start a
   reply for the "hmm" turn. The flag is now reset before the first send.
4. **What still happens to the cut turn.** `stop_reply` (`barge_in.py`) finds that no
   reply started, so it carries nothing itself. The new turn's final arrives, and
   `_reply` answers the carried words and the new words together, once.
5. **No other route.** `_reply` has three callers. A failed final reaches it only
   through `_on_final`. The third caller, `_discard_turn`, only ever answers the
   newly opened turn, which is never flushed.

## 4. When

On every final transcript (the guard is one check). The new branches run only during a
barge-in, while the agent is `thinking`: from the moment `audio.flush` starts sending
until the new turn opens. Both modes are covered: hands-free (judged speech) and
push-to-talk (a press).

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Check the existing flushed mark in `_on_final` | Open the new turn before sending `audio.flush` | `audio.flush` and `cancelling` read the current turn's id; both would need the old id passed in, reordering the barge-in path the contract fixes (section 2.7) |
| Reuse `Session.is_flushed` | A new "interrupting" flag on `TurnPipeline` | Duplicates what the flushed mark already says, and must be cleared correctly on every path |
| Guard where the final arrives (`_on_final`) | Refuse in `Responder.start` (`reply.py`) | By then `_reply` has already emptied the carried words: they would be lost instead of answered twice |
| Reset `_answer_carried` before `stop_reply` | Also check `is_flushed` inside `_reply` | One more check on the reply path for a case the earlier reset already makes impossible |

## 6. Known issues

- Tested with fakes only (`test_cut_turn_race.py`: 5 race tests that failed before the
  fix, 4 `ASR_FAILED` regression tests that passed before and after). Not reproduced
  with a real microphone, Whisper or Groq.
- Latency before/after: not measured; the hot path gains one set lookup.
- A cut turn's `ASR_FAILED` is still sent to the browser during the barge-in. It no
  longer changes the state, but the banner may show for a turn the user abandoned.
- `turns.py` grew to 425 lines (from 411), further over the ~300-line limit; the split is a
  follow-up.
