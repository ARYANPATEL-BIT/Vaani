# 21 - Reply language: let the user force English or Hindi for a whole session

Branch `feat/reply-language` (from `dev` at `c01b16b`, uncommitted). Protocol v0.10.

## 1. What

The page gets a third picker, "Reply", beside Persona and Mode: Any language (the
default), English or Hindi. The choice travels in `session.start` as a new optional
field, `reply_language` (`"any"`, `"en"`, `"hi"`), and `session.started` echoes it back.
With `en` or `hi`, the server ends every system prompt with one more line, after the
clock line ("Reply language: Hindi (Devanagari script)."), and that language's voice
speaks every reply. `any` is exactly the behaviour before this branch. The three persona
prompts gain one rule that makes the line win, and now name the clock line by its words.
The protocol itself is in `docs/contracts.md` sections 2.3 and 2.5.

## 2. Why

Today the reply language comes from **mirroring**: the prompt asks the model to answer
in the language the user spoke. That is the right default, but it fails often. In
round 3 of the guardrails work, 6 of the 12 English questions got Hindi replies
(`docs/findings/guardrails/judged_round3_groq_claude.txt`). A user who knows they want
English, or a Hindi learner who wants Hindi whatever they say, had no way to say so.
A forced choice does not replace mirroring; it is a switch on top of it for the user who
knows. On the same 12 English questions (`docs/findings/reply-language/
judged_reply_language_groq_claude.txt`, judged by Claude, not a person), forced English
got 11 English replies and forced Hindi got 12 Hindi ones. The planned automatic fix, a
server-side hint judged from the transcript, is still not built (PROJECT.md, known gaps).

## 3. How

1. **The picker.** `frontend/src/pages/ConversationPage.jsx` draws three chips in the
   same style as the mode picker, locked while a session is live. Its choice is passed to
   `startCapture` in `src/hooks/useAudioCapture.js`, which sends the message built by
   `buildSessionStart` (`src/turnState/turnContracts.js`). The builder is a plain function,
   so a plain Node test (`sessionStart.test.js`) can check what is sent.
2. **Validation.** `backend/vaani/protocol.py` declares the field as a **Literal type**: a
   type that allows only the listed strings. Pydantic (the library that turns JSON into
   these models) refuses anything else, and the gateway answers `BAD_MESSAGE`, exactly as
   for an unknown `mode`. A missing field means `"any"`.
3. **Kept once.** `gateway.py` stores the value on the `Session` (`session.py`) and puts
   it in `session.started`. A repeated `session.start` is **idempotent**: doing it twice
   has the same effect as once. It gets the first session's reply again, value unchanged.
4. **The echo.** The browser shows the language the server confirmed, not its own guess
   (`confirmedReplyLanguage` in `turnContracts.js`): an older server sends no field, and
   that reads as `any`, which is what an older server does.
5. **The prompt.** `reply.py` reads the session's value once, when the session's
   responder is built. On each reply, `persona.assemble` builds the system prompt
   (the hidden instructions sent before the conversation): the persona text, a blank
   line, the clock line, then, for `en` or `hi`, the reply-language line from
   `REPLY_LANGUAGE_LINES`. It names the script as well as the language, because a model
   told only "Hindi" may write romanized Hindi, which the Hindi voice cannot read.
6. **The rule in the prompts.** Each persona prompt in `config.toml` now says that a
   "Reply language" line at the end overrides every language rule. Each grew 123
   characters (now 1466 to 1517). They used to say "give the time from the last line of
   this prompt"; with a line after the clock that would point at the wrong line, so they
   now say "from the 'Current date and time' line".
7. **The voice.** `speaker.py` locks one voice per reply on the first chunk. With `any`
   the first chunk's script decides (Devanagari: Hindi voice). With `en`/`hi` the forced
   language decides, so a Hindi reply that opens with "OK," keeps the Hindi voice. When a
   forced reply's first chunk is in the other script, one warning is logged. The turn's
   database row still records the first chunk's script in `reply_script`
   (`turn_log.py`), as `schema.sql` defines it, not the forced voice.

## 4. When

At session start: the picker's value is sent, validated, stored and echoed. On every
reply: the line is added when the request is built (a dictionary lookup and one string
join, no network call), and the voice is chosen on the first chunk. Measured: `assemble`
took 6.4 to 6.5 us before and 6.5 to 7.0 us after
(`docs/findings/reply-language/assemble_cost_before_20261111-120748.txt`,
`assemble_cost_after_20261111-121402.txt`).

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| A forced choice on top of mirroring, default `any` | Force by default: always English unless Hindi is chosen | Hinglish speakers, the main users, would have to pick before every session, and a Hindi or mixed message would get an English reply |
| Fixed per session, in `session.start` | A per-turn field the browser can change mid-session | History would hold replies in the old language, which pulls the model back to it, and a reply already being written would need a rule for which value it uses. Reconnecting does the same job |
| One line at the end of the system prompt | A note added to each user message | The note would sit inside the transcript the guardrail checks and the history keeps, so server text and the user's words would mix |
| The line texts in `persona.py`, beside the clock line | A table in `config.toml` | The keys are fixed by the protocol; a config table would need a startup check that its keys match `en` and `hi` exactly, for two strings |
| Validation by the Literal type in `protocol.py` | A check in the gateway, like the persona's | The gateway check gives a more precise message, but needs code the type already gives; `mode` works the same way |
| A forced language picks the voice for the whole reply | Keep the first chunk's script picking the voice | A forced Hindi reply opening with "OK," would be spoken entirely by the English voice |
| `buildSessionStart` moved out of the hook | Keep the message inline in `useAudioCapture.js` | The hook cannot run in a plain Node test; adding a React test library was ruled out |

## 6. Known issues

- Forced English still got one Hindi reply in 12 (default persona, sleep question), and
  forced Hindi addressed the user with feminine forms twice and left Latin words in 2
  replies (judged file above). Gemini, the failover, was not probed with the line.
- First token on these 24 requests: p50 574 / 620 ms against 702.5 in round 3, from 12
  samples each on different days. That shows no slowdown; it does not measure the cost.
- The reply language is not in the database (schema v1, no column), so turn statistics
  cannot be split by it.
- Not run in a real browser: that the picker's value reaches `session.start` is checked
  by reading the code; `sessionStart.test.js` covers only the builder and the echo.
- `language.reply_language()` (the script judge) and the new `reply_language` field share
  a name. The scripts use `session_language` for the field, so they never shadow it.
