# 15c - Groq primary: Groq answers first, Gemini is the failover

Branch `fix/groq-primary-complete` (from `dev`, uncommitted).

## 1. What

The committed config now asks Groq first and Gemini only if Groq fails before its
first word: `provider_order = ["groq", "gemini"]` in `backend/config.toml`. Groq's
model changes from `qwen/qwen3.8-27b` to `openai/gpt-oss-20b`, with
`reasoning_effort = "low"`. No Python code changes: the provider chain already
follows whatever order config gives it. One test that checks the order was updated.

This finishes work that an earlier commit only claimed. Commit `fc9d1e3` (PR #36,
"feat(llm): groq primary, gemini failover") says in its message that it flipped the
order to groq, gemini and shipped this document, `15c-groq-primary.md`. It contained
neither. It changed only the persona prompts' role rule and comments in
`config.toml`, plus `scripts/ask.py` and `scripts/measure_turn.py`.
`provider_order` stayed `["gemini", "groq"]`, and Groq-first ran only as a local
`backend/.env` override. Its run files in `docs/findings/groq-primary/` were not
committed either; they belong in this PR.

## 2. Why

**Speed.** Gemini's first token was slower than both Groq models, measured over the
same 10 real prompts (`docs/findings/llm-latency/measure_llm_20261008-101039.txt`):
Gemini p50 1702 ms, `openai/gpt-oss-20b` (low) p50 788 ms, `qwen/qwen3.8-27b` (none)
p50 454 ms. Gemini alone uses more than the whole 1,000 ms budget.

**Correctness, which decides the model.** qwen is faster, but its Hindi was often
broken. Aryan marked 6 tutor replies from each model
(`docs/findings/groq-primary/tutor_hindi_20261008-113643.txt`), quoted exactly:

- qwen 1: broken - nonsense words (फलसोड़, जलमे, आलिस)
- gpt-oss 1: clean
- qwen 2: broken - nonsense opening sentence and broken grammar, though 3/4 is correct
- gpt-oss 2: clean
- qwen 3: broken - says "मशीन" instead of नियम
- gpt-oss 3: clean
- qwen 4: broken - a nonsense clause, and it promises a reminder it can't give
- gpt-oss 4: broken - advises in first person as if it were the student, switches to तुम
- qwen 5: clean - minor typo
- gpt-oss 5: broken - latin words the hindi voice will misread
- qwen 6: broken - nonsense words, thai characters in "डिसก์"
- gpt-oss 6: clean - "RAM" in latin is minor

Result: **qwen 1/6 clean, gpt-oss 4/6 clean.** The price: gpt-oss-20b costs about
**330 ms more** first-token latency than qwen (788 vs 454 ms p50, from the
llm-latency run above). We chose correctness: a fast reply that is nonsense is not
an answer.

**Whole turns** were measured with Groq first, but with qwen, not gpt-oss. From
transcript to first audio: Groq (qwen) p50 900 ms, Gemini p50 3281 ms
(`docs/findings/groq-primary/compare_primaries_20261008-110611.txt`). With gpt-oss,
expect about 330 ms more. That was not measured.

## 3. How

1. **Config.** `backend/config.toml`, `[llm]`: `provider_order` is now groq, gemini.
   `[llm.groq]`: model `openai/gpt-oss-20b`, `reasoning_effort = "low"` (the lowest
   level gpt-oss accepts). `include_reasoning = false` stays: the model's private
   reasoning text is never sent back, because it would never be spoken.
2. **Startup.** `vaani/providers/chain.py` builds the chain in config order. It
   needs both API keys, as before; a missing key still stops the server.
3. **Every turn.** `vaani/reply.py` asks the chain for a reply. The chain tries
   `vaani/providers/groq.py` first. If Groq is rate-limited (HTTP 429), times out or
   is unreachable *before its first word*, the chain tries `vaani/providers/gemini.py`.
   After the first word, there is no failover: the user may already be hearing it.
4. **Spend cap.** `vaani/spend.py` counts every request from both providers
   against one cap of 200 per process; a failover is one more counted request.
5. **Test.** `backend/tests/test_config.py` now expects groq, gemini.
6. **PROJECT.md** now says Groq is primary in the committed config.

## 4. When

- **Server start:** the chain is built once, Groq first.
- **Every turn, once the transcript is final:** the request goes to Groq first. The
  model's thinking (`reasoning_effort`) happens before its first token, so it is
  part of the wait the user hears.
- **Only when Groq fails before its first word:** Gemini is asked, and the user
  waits for Groq's failure plus Gemini's first token.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Groq first | Keep Gemini first | Gemini's first token p50 is 1702 ms against 788 ms for gpt-oss on Groq. Gemini first would spend the whole latency budget on one stage. |
| `openai/gpt-oss-20b` | `qwen/qwen3.8-27b`, the faster Groq model | 1 of 6 qwen replies was clean, against 4 of 6 for gpt-oss: made-up words, a wrong word ("मशीन" for नियम), Thai characters. We would have saved about 330 ms and lost correct Hindi. |
| `reasoning_effort = "low"` | `"medium"` | Thinking happens before the first token, so more effort means a longer wait. Medium was not measured; low already gave 4 of 6 clean. |
| Gemini kept as failover | Groq only | Groq's free tier for gpt-oss-20b is 1000 requests a day and 8000 tokens a minute, shared by everyone on our key (rate-limit headers, `docs/findings/groq-primary/ask_gptoss_20261009-145842.txt`). Past it Groq answers 429. Without a second provider, that turn would fail with `LLM_FAILED`. |

## 6. Known issues

- gpt-oss still leaks Latin words into Devanagari replies (prompts 5 and 6), and the Hindi voice misreads them.
- One gpt-oss reply broke persona: it spoke as the student instead of the tutor (prompt 4).
- Not measured with gpt-oss: whole turns (mic to first audio), and the token cost of a real turn with history, so turns per minute is unknown. The free-tier limits (1000 requests a day, 8000 tokens a minute) are the same as qwen's.
- The marks cover 6 tutor prompts, one reply each: a small sample, not a quality rate.
