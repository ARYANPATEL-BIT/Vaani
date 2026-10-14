# 20 - Guardrails: what the agent may claim, in which language, and what time it is

Branch `feat/guardrails` (from `dev`, uncommitted). No protocol change.

## 1. What

The three persona prompts in `backend/config.toml` (`[personas]`) are rewritten so the
agent stops pretending: it has no tools, so it never promises or claims an action, it
refuses weather, news and prices, and it answers the date and time from a new **clock
line** that the server adds to every system prompt (`vaani/persona.py`, `[llm].timezone`).
The prompts also ask for the reply in the user's language and for the right Hindi
gender, for the agent and for the user. `vaani/speaker.py` now logs any Latin word left
in a Hindi chunk (`vaani/language.py`, `latin_words`). `scripts/probe_replies.py` asks
every persona 37 fixed questions and saves the replies to be judged. One new dependency:
`tzdata`. The final prompts are round 3 of three rewrites; section 6 lists what they
still get wrong.

## 2. Why

A **system prompt** is the hidden text sent before the user's words on every request; it
is the only place we tell the model who it is and what it may do. With the prompts on
`dev`, Groq's replies to 37 probe questions held 12 promises ("I will remind you at 7")
and 7 invented facts: Delhi at 38 C, a petrol price, a wrong time of day
(`docs/findings/guardrails/judged_before_groq_claude.txt`). The dev prompt's own example
sentence was a promise ("I'll remind you at 8 tomorrow and give you the traffic update").

## 3. How

1. **Prompt first.** The fix is in the prompt, not in code that rewrites the reply. The
   reply is spoken chunk by chunk while the model is still writing (`chunker.py`), so by
   the time code could see "I'll remind you", the first half is already playing.
2. **The probe set.** `docs/findings/guardrails/probes_20261014.tsv`: 37 questions over the
   three personas: actions (A), live data (B), names (N), ordinary help (C), English (E).
   `probe_replies.py` sends each one once, 12 s apart (under Groq's 8000 tokens a minute),
   with no history, and writes every reply with code counts and an empty `mark:` line.
   Claude, not a person, judged each reply with letter codes (P promise, E wrong language,
   F feminine user...); the `judged_*_claude.txt` files hold them, `summary_20261014.txt`
   puts the rounds side by side.
3. **The round 1 English regression.** Round 1 wrote the new rules, and an example
   sentence, in Devanagari. English questions answered in Hindi went from 2 of 12 to 9 of
   12 (`judged_round1_groq_claude.txt`). A model continues the text it is given, and the
   language of that text pulls the reply's language with it: a system prompt that is
   mostly Hindi tells the model "this conversation is in Hindi" more loudly than the one
   rule that says "answer English in English". Round 2 wrote every rule in English, with
   Devanagari only inside quotes, and dropped the example sentence. That explanation fits
   the numbers; it was not tested on its own.
4. **The clock line.** A model has no clock: asked the time, it guesses, and guessed
   10:30 at 10:48. `reply.py` reads the time once per reply in the `[llm].timezone` zone,
   and `persona.assemble` adds it as the LAST line of the system prompt ("Current date and
   time (Asia/Kolkata): Wednesday, 14 October 2026, 15:23."). Last, so the persona text in
   front of it is byte-for-byte the same on every turn. Weekday and month names are
   English because the server never changes Python's locale.
5. **tzdata.** A **time zone** is a set of rules, not just an offset: some zones change
   their clocks for daylight saving. Python's `zoneinfo` reads those rules from the
   operating system, and Windows has none, so the `tzdata` package supplies them
   (`docs/versions.md`). `config.py` checks the zone name at startup, so a typo stops the
   server instead of failing a user's turn.
6. **The per-chunk Latin check.** The Hindi Piper voice reads Latin letters with English
   spelling rules and mangles them (`12-chunking-tts.md`). Before each Hindi chunk is
   synthesised, `speaker.py` asks `language.latin_words` for any run of A-Z letters and
   logs a warning naming them, such as "SSD". It does not fix the word; it counts it. One
   regex scan costs about 2 microseconds on a 200-character chunk
   (`chunk_check_cost_20261014-104727.txt`), which is too small to measure in a turn.
7. **Groq and Gemini, same prompt.** With the round 3 prompts, Gemini's 8 replies (the
   default persona; the run then timed out) had no promise, no English answered in Hindi,
   no feminine form for the user and no Latin word. Groq's same 8 questions had 2, 2, 3
   and 0. But Gemini's first token was p50 2413 ms and p95 17152 ms, against Groq's 750
   and 6973 over 37 (`summary_20261014.txt`). Groq stays first.
8. **Why the rounds stopped converging.** Three rounds did not add up to a clean prompt
   on `openai/gpt-oss-20b`, for four reasons that the run files show:
   - **One draw per question.** A model **samples** its reply: it picks each word at
     random among the likely ones, so the same question can get a different answer
     each time (no temperature is set in config, so the provider default applies). With
     one reply per probe, a change of two or three between rounds may be chance; no
     probe was repeated to find out.
   - **An unchanged rule got worse.** The "no tools" rule was the same text in rounds 2
     and 3, yet on the same default and tutor questions promises went from 0 to 4.
     Changing other rules moved this one: rules in one prompt compete for the model's
     attention.
   - **Hindi forces a gender on "you".** "आप कर सकते हैं" (masculine) and "आप कर
     सकती हैं" (feminine) are both polite; there is no neutral verb. Every F in rounds
     1 to 3 came from a female persona: the model lends its own gender to the user.
     Round 3 quoted the forbidden "सकती" in the prompt, and F stayed at 3.
   - **The model, not only the prompt.** The same round 3 prompt on Gemini had none of
     the four failures (8 replies). Gemini follows the same list better; why was not
     tested.
   So the next fixes move work out of the prompt and into code (section 6).

## 4. When

The prompt and the clock line: once per reply, in `reply.py`, before the paid request.
The Latin check: on every chunk of a reply whose voice is Hindi. The time zone check:
once, at server start. `probe_replies.py`: only when run by hand.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Rules in the prompt | A filter that rewrites promises in the reply | The reply is already being spoken while it streams; a filter would have to hold back audio, adding wait to every turn |
| Rules written in English | Rules in Devanagari, as in round 1 | 9 of 12 English questions came back in Hindi (round 1) |
| No example sentence | A new example that refuses politely | All three personas copied the old example's promise (`docs/findings/groq-primary/ask_gptoss_20261009-145842.txt`); a copied example would stay in every reply |
| Clock line at the end of the system prompt | A tool the model calls to ask the time | Our providers are called with no tools; a tool call is a second round trip before the first word |
| `zoneinfo` + `tzdata`, zone by name | A fixed offset (+05:30) in config | No dependency, but wrong twice a year in any zone with daylight saving, and no zone name to print |
| Log Latin words | Transliterate them into Devanagari in code | A word list or a model for every brand name; logging first tells us how often it happens |
| Groq stays first (`provider_order` unchanged) | Gemini first, which was cleaner | Gemini's first token, p50 2413 ms and p95 17152 ms over 8 replies, is far over the 1000 ms target |

## 6. Known issues

- Round 3, the final prompt, still fails 4 of 8 criteria on Groq: English answered in
  Hindi 6 of 12, promises 6, feminine forms for the user 3, Latin in Hindi 4
  (`judged_round3_groq_claude.txt`). Planned fix: the server decides from the transcript
  whether the user spoke English and tells the model per turn.
- Every verdict is Claude's, from the text; no reply was judged by ear or by a native
  speaker, and no probe was run twice.
- Latency: no end-to-end before/after run (`measure_turn.py`). Probe first token went
  from p50 605 / p95 974 ms (before) to 750 / 6973 ms (round 3); the p95 is 3 slow
  replies, and whether Groq's load or the prompt caused them was not measured.
- Failed requests on 2026-10-14: Groq 4 of 138, Gemini 1 of 21, none a 429
  (`timeouts_20261014.txt`). Planned fix: a first-token deadline that fails over sooner.
- Gemini's quality edge rests on 8 replies from one persona.
