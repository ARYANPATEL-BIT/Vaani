# Finding: PERF-1 cannot be met with the current pipeline

Date: 2026-10-02 (day 10). Status: **needs a decision, to be taken to the mentor.**
No option is recommended here.

## The target

CLAUDE.md: *"Target: P50 under 1,000 ms, mic-stop to first audible sample."*
(The full PERF-1 wording is in `docs/complete documentation vaani.pdf`, which
could not be opened in this session. The CLAUDE.md wording is used.)

## What we have measured, stage by stage (p50)

| Stage | p50 | Source | Notes |
|---|---|---|---|
| VAD: last audible sound → `speech_ended` | 280 ms | 09-endpointing.md, 13 utterances | 200 ms is `[vad].end_frames`; the rest is Silero's own decay |
| Endpointer wait: `speech_ended` → `turn_ended` | 700 ms | 09-endpointing.md | `[endpoint].end_of_turn_silence_ms`, a config value |
| ASR: `turn_ended` → `transcript.final`, cuda/large-v3 | **577 ms** (p95 635) | day 10, `scripts/measure_asr.py`, 12 runs | **Preliminary:** 4 clips (1 human, 3 TTS) × 3. The real run waits on Aryan's 10 Hinglish recordings |
| ASR, cpu/small (committed default; cannot do Hinglish) | 1330 ms (p95 1391) | same | Shown for completeness |
| LLM: request → first token (Gemini via the chain) | 1291 ms | 06-cancel-failover.md, n=14 | Network, so it varies a lot (1110–1837 ms) |
| TTS: text → first audio (Piper) | ~100 ms | frontend-learning/05-tts-spike.md | Measured on Apple Silicon, not on our backend |
| Playback, network hops | not measured | — | — |

These are separate p50s added together. They are **not** an end-to-end measurement:
the pipeline is not connected yet (ASR → LLM lands later).

## The arithmetic

**Before the LLM sees a word (GPU path):** 280 + 700 + 577 = **1,557 ms**,
57% over the whole 1,000 ms budget before any reply exists.

**Whole path, GPU:** 280 + 700 + 577 + 1291 + ~100 ≈ **2,950 ms**, about
three times the target.

**Left for LLM + TTS + playback at the current settings: −557 ms.**

## Option A — lower the endpointing threshold

Keep PERF-1. Shorten `end_of_turn_silence_ms`, and accept that the turn ends
during more mid-sentence pauses.

| `end_of_turn_silence_ms` | Silence before turn ends (280 + T) | Before LLM, GPU (+577) | Left for LLM + TTS + playback | A pause longer than this cuts the user off |
|---|---|---|---|---|
| 700 (today) | 980 ms | 1,557 ms | −557 ms | ~980 ms |
| 500 | 780 ms | 1,357 ms | −357 ms | ~780 ms |
| 400 | 680 ms | 1,257 ms | −257 ms | ~680 ms |
| 200 | 480 ms | 1,057 ms | −57 ms | ~480 ms |
| 0 | 280 ms | 857 ms | 143 ms | ~280 ms (VAD alone) |

What this shows:
- **No threshold meets PERF-1 on its own.** Even at 0 ms, 143 ms are left,
  and the LLM's first token alone was measured at 1,291 ms.
- Every step down ends turns during shorter pauses. Day 9 noted that people
  pause **200–500 ms** mid-sentence; our own fixture has a 350 ms pause after
  "Hello". **We have not measured the cut-off rate** at any threshold. That
  would need recordings of natural speech with thinking pauses, scored by hand.
- Cost to the user: the agent answers half a sentence ("My flight is on…").

## Option B — revise PERF-1, with this evidence

Keep endpointing at 700 ms (no extra cut-offs). Change the target to one the
measured stages can meet. The evidence for the change is the table above:
- two stages alone (endpointing 980 ms + LLM first token 1,291 ms) already
  exceed 2,000 ms;
- ASR on the only configuration that can do Hinglish adds 577 ms on a GPU.
  Without a GPU there is a hosted recogniser (Sarvam, not built), which adds a
  network round trip.

A revised target has to say **which span it measures**, because the options
differ by a second or more: from mic-stop (≈2,950 ms today), or from
`turn_ended` (577 + 1291 + ~100 ≈ 1,970 ms today). Picking a number is the
decision. This document does not pick one.

Cost: the headline promise gets weaker. A voice agent that answers about
3 s after you stop feels slow next to one that answers in 1 s.

## Other levers (already listed in 09-endpointing.md, Q11; not evaluated here)

- Start the final ASR decode at `speech_ended` instead of `turn_ended`, and throw it
  away if speech resumes. On the GPU, 577 ms fits inside the 700 ms wait,
  so ASR would add ~0 ms. The cost is a wasted decode on every pause that does not end
  the turn.
- A faster or nearer LLM (time to first token is the single biggest stage).
- Semantic endpointing (Future Scope).

These are not alternatives to the A/B decision: they change the numbers it
is made on.

## What would change these numbers

- Aryan's 10 Hinglish recordings (ASR p50/p95 on real speech, not TTS).
- An end-to-end measurement once ASR → LLM → TTS is connected (week 2–3).

## Day 11 update: the first connected, end-to-end measurement

Date: 2026-10-02 (day 11). The pipeline is now connected through the model's
first token, so this is one measurement, not separate p50s added together.

Setup: server on cuda/large-v3 (RTX 5070 Laptop), echo off, provider order
`gemini, groq` (Gemini answered every turn). Client `scripts/measure_turn.py`,
12 turns, one Hinglish TTS clip (Piper, "Namaste, aaj hum real-time voice
conversation ke baare mein baat karenge.", 5 s), real-time pace, one session,
so history grew to the 6-exchange cap.

| Span | p50 | p95 | Clock |
|---|---|---|---|
| `speech_ended` → `turn_ended` (endpointer wait) | 704 ms | 718 ms | server |
| `turn_ended` → `transcript.final` (ASR, large-v3) | 1188 ms | 1389 ms | server |
| LLM request → first token (Gemini, real prompts) | 913 ms | 1256 ms | server |
| **`turn_ended` → first `agent.text`** | **2140 ms** | **2429 ms** | server |
| **last voiced frame → first `agent.text`** | **3127 ms** | **3440 ms** | client |

**Against the 1,000 ms target: 3.1× over at p50, and nothing is audible yet**
(TTS and playback still to add).

Two things moved since the day-10 table:
- ASR on this 5 s clip took 1188 ms, about twice day 10's 577 ms on 4 shorter
  clips. Decode time grows with clip length; we have not separated that
  from other causes.
- Gemini warm first token, timed on its own with `scripts/measure_llm.py`
  (10 real assembled prompts): **p50 898 ms, p95 1075 ms** (day 6: 1291 ms,
  on toy prompts and cold connections).

**Groq was not measured.** `VAANI_GROQ_API_KEY` in `backend/.env` was rejected
(HTTP 401, Invalid API Key). Whether flipping `provider_order` is a cheap win
is still unknown until the key is replaced and `measure_llm.py` is re-run.
