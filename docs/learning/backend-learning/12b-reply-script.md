# Reply script: replies the voice can say, and an honest first-chunk measurement

## 1. What we built in this branch

Branch `fix/reply-script`. On day 12 the agent wrote Hinglish in Latin script and the Hindi
voice read it out unintelligibly. Now every reply is written **entirely in Devanagari**,
English words too, the format of `hinglish_C.wav`, the clip rated best. The first chunk
is now cut at any sentence end however short ("Hello!"). The chunker understands
Devanagari conjunctions. Every first cut is explained in a debug log line. Measurement runs
never overwrite earlier evidence. `contracts.md` matches the code again (shared protocol v0.6).

## 2. What we used to build it

- **The persona prompt** (`config.toml [personas]`). The instructions sent before every
  turn. Here it carries the script rule and one example sentence. It is cheaper than any code: no
  new dependency, and the model writes the words itself, so it can tell मैं ("I") from English
  "main".
- **Regex lookahead `(?!...)`**. Checks what comes *next* without consuming it. Here it
  says "the conjunction must not be followed by more letters". It replaced `\b`, which is
  wrong for Devanagari (section 5).
- **`%a` in log calls / `"backslashreplace"`**. Turns every non-ASCII character into an
  ASCII escape: a backslash, `u`, and the four hex digits of its code point (ठ becomes
  backslash-u-0920). Used wherever text reaches the console, because the Windows console's
  code page cannot be trusted with Devanagari.
- **`str.isalpha()`**. True for letters in any script. Used to tell a real chunk from
  punctuation alone ("...").
- **Windows MCI (`winmm.dll`)**. A recorder built into Windows, reached from PowerShell.
  `backend/scripts/record_fixture.ps1` uses it to record the real Hinglish fixture
  (16 kHz, mono, 16-bit) with no new dependency. **The fixture is not recorded yet.**

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| How to get Devanagari | Ask for it in the persona prompt | Transliterate Latin to Devanagari in code (`indic-transliteration`) | New dependency; romanized Hindi is ambiguous ("main" = मैं or English "main"); English words come out letter by letter | The model can still drift (1 of 26 replies did) |
| Short first chunk | A sentence end cuts at any length | Lower `first_min_chars` | That would also cut at every short comma; tuning belongs to day 14 | "जी," (3 characters) still cannot cut early |
| Conjunction boundary | Lookahead "not followed by a letter or Devanagari character" | `\b` | `\b` never matches after तो and does match inside तोड़ (proved by a test) | A longer regex to explain |
| Punctuation-only chunk | Cuts count only after the first letter | Drop it in `Speaker.say` | Dropping loses the text; merging keeps every character spoken in order | None found |
| Debug level for the cut log | `log.debug`, enabled per run | `log.info` | Every turn would print long escaped Devanagari lines | You must remember to switch it on (section 5) |

## 4. Where things live

| What | File | Function or class |
|---|---|---|
| The reply-script rule | `backend/config.toml` | `[personas]` default, tutor, support |
| Devanagari conjunctions | `backend/config.toml` | `[chunker] conjunctions` |
| First-chunk rule, letter filter | `backend/vaani/chunker.py` | `ClauseChunker._find_cut`, `_boundaries`, `flush` |
| Which rule cut | `backend/vaani/chunker.py` | `ClauseChunker.first_rule` |
| First-cut debug log | `backend/vaani/reply.py` | `Responder._answer`, `_log_first_cut` |
| First-chunk synthesis log | `backend/vaani/speaker.py` | `Speaker.say` |
| Script check, in code | `backend/scripts/ask.py` | `script_counts`, `--persona`, `--save` |
| Timestamped run files and WAVs | `backend/scripts/run_log.py` | `RunLog.stamp`, `OUT` |
| Listening clips | `backend/scripts/measure_tts.py`, `hinglish_tts.py` | `REPLY`, `VARIANTS` |
| Recording the real fixture | `backend/scripts/record_fixture.ps1` | `Send-Mci` |
| Evidence | `docs/findings/reply-script/` | one file per run; `tts-day12/` is frozen |
| Wire format | `backend/vaani/protocol.py`, `docs/contracts.md` | v0.6 |

No database, no new config section, no new dependency.

## 5. How it works

**The prompt.** `backend/config.toml`:

```toml
write every word in Devanagari script, English words too: "traffic" is \
ट्रैफ़िक and "update" is अपडेट. Write numbers as digits and end each \
sentence with ।. Example: ठीक है, मैं कल सुबह 8 बजे याद दिला दूँगी और \
```

Checked in code, not by eye: `script_counts` in `ask.py` counts Devanagari characters, Latin
letters and anything else. 10 prompts: **0 of 10 drifted**, all ended with ।
(`ask_script_check_20261006-115858`). Tutor and support, 2 each: **0 of 4**
(`ask_script_check_20261006-122020`). In the 12-turn after-run, **1 of 12** drifted: turn 9
wrote "Vani", the project name heard in the transcript. Greetings: the before-run started
12 of 12 replies with "Hello!"; the after-run greeted only on turn 1.

**Does it sound right?** New clips in `docs/findings/reply-script/`:
`prosody_{whole,conservative,aggressive}_20261006-120108.wav` are the hinglish_C sentence
plus a second sentence, chunked three ways. `hinglish_{A,B,C,R1,R2,R3}_20261006-120122.wav`
are the day 12 anchors plus three real Gemini replies in the new format.

**Listening verdict, Aryan's words:**

> my listening verdict, wavs played directly:
> hinglish_A (all latin, old format, anchor): not intelligible, same as day 12
> hinglish_B, hinglish_C: good and clear
> R1, R2, R3 (real replies in the new format): good and clear
> prosody whole, conservative, aggressive: good and clear

So the script problem from day 12 is fixed for real replies. With Devanagari text, all three
chunkings sound clear. This is the comparison day 12 could not make.

**The first-chunk rule.** `backend/vaani/chunker.py`:

```python
            cuts = [(e, "sentence end") for e in sentences]
            cuts += [(e, "clause break") for e in clauses if e >= cfg.first_min_chars]
            cuts += [
                (e, "conjunction") for e in conjunctions if e >= cfg.first_min_chars
            ]
            if cuts:
                return min(cuts)  # the earliest position
```

A sentence end needs no minimum; a comma or conjunction still needs 8 characters. Each cut
carries its rule's name, which ends up in `first_rule`.

**Why not `\b`.** `\b` is the edge between a "word character" and anything else. Python
does not count Devanagari vowel signs (the ो in तो) as word characters. So `तो\b` finds no
edge before a space, and finds a false one inside तोड़. The fix:

```python
            rf"\s(?=(?:{words})(?![\w{_DEVANAGARI}]))", re.IGNORECASE
```

**Punctuation alone.** `_boundaries` drops any cut before the first letter, so "..."
waits and joins the next chunk. `flush` returns `None` for a letterless remainder.

**The evidence line.** Off by default. Start the server with:
`uv run python -c "import logging, uvicorn; [logging.getLogger(n).setLevel(logging.DEBUG) for n in ('vaani.reply', 'vaani.speaker')]; uvicorn.run('vaani.app:app', port=8765)"`.
`reply.py` keeps `(ms after turn_ended, text)` for every delta (one streamed piece of the
reply) until the first cut, then logs the chunk, the rule and the deltas with `%a`.

**What the before-run measured** (`measure_turn_20261006-114707`, old persona and
chunker, 12 turns). Server clock, from `turn_ended`, p50 / p95:

| Stage | p50 | p95 |
|---|---|---|
| ASR (`turn_ended` → `asr_final`) | 717 ms | 935 ms |
| `asr_final` → LLM request sent | 0 ms | 1 ms |
| Gemini time to first token | 1758 ms | 3737 ms |
| = `turn_ended` → delta 1 | 2432 ms | 4449 ms |
| Delta 1 → first cut (waiting for delta 2) | 239 ms (median) | 1517 ms (max) |
| First-chunk synthesis | 122 ms (median) | 149 ms (max) |

Gemini sent each reply in about two deltas. "Hello!" was rejected (6 characters, under
8), so the first chunk always waited for delta 2.

**This PR's latency effect is bounded by the delta-2 wait: median 239 ms in this run.**
The main cost is `turn_ended` → delta 1 (p50 2432 ms), and nothing here touches it. In the
after-run the new rule never fired early. Turn 1's sentence end was 41 characters in. Turns
2–12 were one-sentence replies, so the cut came at the end of the reply. Delta 1 was 2–10
characters ("जी", "जी,"), too short to hold any boundary.

**Reconciling 4110 ms with day 12's 6127 ms.** Both are the client's last voiced frame →
first audio frame, same fixture, same GPU. Neither number is wrong. In every turn of both
runs, client minus server (`turn_ended` → first audio) is 996–1119 ms. That gap is
endpointing (200 ms VAD + 700 ms silence) plus frame timing, so the two clocks agree. Day 12
was slower because turns 1–7 were slow on the server. The after-run shows the same pattern,
and its new debug lines show where the time went: first-chunk synthesis took 1146–1762 ms in turns 1–6
and 79–120 ms in turns 7–12, and ASR took about 2000 ms vs about 650 ms. CPU and GPU work slowed
together, so the whole machine was slow in those turns. The cause is **not known**. The
after-run's whole-turn p50 (5627 ms) is therefore not a fair "after" number.

**Real-clip numbers: pending.** The clean after-run, on a recording of Aryan's own Hinglish
voice (`backend/tests/fixtures/hinglish_real_16k.wav`), has not been run. It will be a
separate measurement. Every latency number above comes from the English test clip
`speech_16k_mono.wav`.

## 6. When things go wrong

| What fails | What the code does | What the user sees |
|---|---|---|
| Model writes Latin anyway | Nothing; the voice reads it badly | That word is unclear (1 of 26 replies) |
| Reply starts with "..." | Joins the next chunk | Nothing odd |
| Reply opens "जी," or "ठीक है," | Under `first_min_chars`; cut later or at the end | Longer wait for the first audio |
| Debug left off | No first-cut lines | Nothing; only tuning loses data |

**Known issues.** None of these is fixed in this branch.

1. **Invented facts (guardrails day).** Asked about Delhi's weather, the agent gave a
   forecast and a temperature (32 degrees). It has no weather data, so it made them up.
2. **Proper nouns stay in Latin.** "Vani" from the transcript came back as `Vani` inside a
   Devanagari reply (after-run turn 9). The voice reads that word with English rules.
3. **Mid-phrase first cuts and short openings (day 14).** `ठीक है,` is 7 code points and
   `जी,` is 3. Both are under `first_min_chars = 8`, so they never cut. In
   `measure_tts_20261006-120108` the committed setting cut the reply at the 60-character
   word boundary instead, in the middle of the phrase "ट्रैफ़िक का | अपडेट".
4. **The first ~90 s of a run are slow.** In day 12's turns 1–7 and the after-run's turns
   1–6, CPU work (Piper) and GPU work (ASR) were slow together. Cause unproven. The
   hypothesis is the machine itself: CPU/GPU throttling right after a heavy job (the after-run
   started less than a minute after `hinglish_tts.py` ran large-v3 on the GPU). A second candidate
   was found later: a `uvicorn --reload` dev server on port 8000 was running during all
   three runs. It starts a fresh worker that reloads Whisper and Piper on the CPU after every
   `.py` edit. The before-run, with no slowdown, had the same server running, so it is not
   the whole story.
5. **`protocol.py` is 310 lines**, over the ~300 limit, because it repeats the version
   history from `contracts.md`.
6. **Real-clip numbers pending.** No measurement on real Hinglish speech yet. The fixture is
   not recorded, and the clean after-run will be a separate measurement. Until then there is no
   fair "after" latency number for this branch.

## 7. New terms

- **BOM**: three invisible bytes some editors put at the start of a UTF-8 file. We forbid it.
- **Code page**: the Windows console's character table; Devanagari may not be in it.
- **Code point**: one Unicode character number. ठीक is 3 code points, though it reads as 2 syllables.
- **Combining mark (matra)**: a vowel sign drawn on a consonant, like ो in तो.
- **Delta**: one streamed piece of the model's reply, as sent in `agent.text`.
- **Devanagari**: the script Hindi is written in; Unicode block U+0900–U+097F.
- **Lookahead**: a regex check on what follows, without consuming it.
- **TTFT**: time to first token, from sending the request to the first delta.

## 8. Questions you could be asked

1. **Where is the code that decides the first chunk?** `ClauseChunker._find_cut` in
   `backend/vaani/chunker.py`, the `if self._first:` block.
2. **Where is drift checked?** `script_counts` in `backend/scripts/ask.py`, run with
   `--persona default --save FILE`.
3. **What happens if Gemini answers in Latin?** Nothing stops it. The script count reports
   it, and the voice reads it badly.
4. **What happens to a chunk that is only "..."?** It is never cut alone. It joins the
   next chunk, or is dropped at the end.
5. **Why not transliterate in code?** "main" can mean मैं or English "main"; only the
   model knows which.
6. **What does `\b` mean, and why is it wrong here?** A word edge. Python treats Devanagari
   vowel signs as non-word, so the edge falls inside words.
7. **Did this PR make the agent faster?** At most by the delta-2 wait (median 239 ms), and in the
   after-run not at all. The big cost is ASR plus Gemini's first token.
8. **Why do day 12 and today disagree by 2 s?** Machine-wide slowness in day 12's turns 1–7;
   both measurements are internally consistent.
9. **Hardest: is the after-run a valid before/after?** No. Turns 1–6 ran on a slowed machine.
   Only the delta-2 wait (222 ms after vs 239 ms before) compares fairly.

## 9. Check yourself

1. Why does "Hello!" now cut alone, but "जी," does not?
2. Which four stages make up `turn_ended` → first audio, and which is largest?
3. Why is `%a` used in every new log line?
