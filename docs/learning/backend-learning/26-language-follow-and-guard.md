# 26 - The reply follows the language you spoke, and a forced language is enforced

Branch `fix/language-and-login` (from `dev`, uncommitted). Protocol unchanged (no `contracts.md` edit).

## 1. What

Four changes. **ASR language pick**: each speech-to-text engine can now choose English or Hindi
per turn instead of always forcing Hindi (`pick_language`). **A per-turn reply-language note**:
the server adds one short instruction after the user's words, saying which language and script
to answer in: the forced one, or the one the ASR picked. **The forced-language guard**: in a
session that forces English or Hindi, no reply in the other script is shown or said, and the
Hindi voice never receives a Latin letter. **The landing header**: "Sign in" shows unless the
server says you are signed in; signed in, your name and a Log out button.

## 2. Why

- **"It often doesn't understand me."** Whisper (the speech-to-text model) was told the
  speech is Hindi on every turn. Told that, it sometimes writes ENGLISH speech in Devanagari
  letters ("हेलो इस एस ए शॉर्ट टेस्ट"): 2 of 6 English clips on Groq, and 3 of 4 of Aryan's
  real English turns on the GPU ("LeetCode" became "लीड को"). The model then saw a Hindi-looking
  message and answered in Hindi (`docs/findings/language/asr_experiment_20261127.txt`,
  `transcripts_20261127.txt`). Plain auto-detection is no fix: Groq wrote pure Hindi as Urdu,
  in Arabic script, 6 of 6 times.
- **The toggle did not force anything.** Forced English answered 8 of 9 Hindi messages in
  Hindi: one line at the end of the system prompt lost to the persona's "a Hindi message gets
  a Hindi reply" rule (`reply_language_probes_20261127.txt`). Forced Hindi sent Latin letters to
  the Hindi voice, which reads them as noise; the server only logged it.
- **No Sign in.** The header showed it only for a 401. With the backend down, still loading its
  models, or slow (a Render cold start), the answer was a 502 or a timeout, and the header
  offered no way in. Reproduced on `http://localhost:5173/` with a fresh browser profile and the
  backend stopped. It was not the studio merge and not a stale `frontend/dist`: that build has
  "Sign in"; it only predates the studio commit.

## 3. How

1. **Pick (faster-whisper)**, `asr/whisper.py`: `detect_language` gives a probability per
   language. English wins only at or over `english_min_prob` (0.5); otherwise the decode is
   forced to Hindi. On every English clip English scored 1.00, on every other at most 0.25.
2. **Pick (Groq)**, `asr/groq.py`: two requests go at once, one auto-detected (`verbose_json`,
   the format that names the detected language) and one forced to Hindi. The auto text is kept
   only if Groq says "English". `asyncio.TaskGroup` runs the two side by side and, if one
   fails, cancels the other. The request cap counts both before either is sent (`spend.py`).
3. **Hand-over**: the `Transcript` carries `picked` (`en`, `hi`, or none when forced);
   `asr/runner.py` passes it to `turns.py`, then to `reply.py`.
4. **Which note**: `language.turn_language` picks the session's forced language if there is
   one, else the picked one, and calls a picked-Hindi turn with Latin words in it `hinglish`.
   `persona.assemble` adds that note (`[reply_language.reminders]` in `config.toml`) after this
   turn's words only; history keeps the words as spoken. The Hindi and Hinglish notes ask for
   every English word, name, brand, abbreviation and formula in Devanagari, and no code.
5. **First-chunk check**, `reply_stream.py` (the stream loop, moved out of `reply.py`, which was
   over 300 lines): in a forced session the text is **held**, not sent, until the first chunk
   is cut. If that chunk is in the other script, the stream is closed unseen and `reply.py`
   asks once more with a sharper note; if that fails too, it says the configured fallback line.
6. **The strip**, `speaker.py`: `say` is the one place text reaches a voice. In a forced
   session a chunk in the other script is skipped, and in forced Hindi `language.strip_latin`
   removes every Latin letter from the voice's copy. The screen keeps the chunk as written.
   Each strip logs the number of letters removed, never the text.
7. **Header**, `frontend/src/landing/HeaderAuth.jsx`, `Hero.jsx`, `login/loginState.js`:
   only a clear "signed in" (name, Log out) or "auth off" (nothing) hides Sign in. Log out
   posts `/auth/logout`, asks `/auth/me` again and shows that answer at the top of `/`.

## 4. When

The pick runs on every final transcript; the note is chosen once per reply, before the model
call. The hold and the first-chunk check run once per reply, in forced sessions only. The strip
runs on every chunk of a forced Hindi reply. The header asks `/auth/me` once per landing visit.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Detect, then decode forced to en or hi (whisper) | Plain auto-detect (`language=None`) | large-v3 wrote pure Hindi in Arabic script 3 of 6 times; the pick got the script right 18 of 18 times |
| Groq: two requests at once | One after the other: auto first, forced only if it is not English | Every Hindi turn would wait a whole extra round trip (420-705 ms in the experiment) |
| A note after the user's message | A stronger line at the end of the system prompt | The system-prompt line is what lost 8 of 9 times; the note is the last thing the model reads |
| Retry once, then a fallback line | Say the wrong-script reply with the forced voice (as before) | The Hindi voice reading English is the noise the user heard |
| Strip Latin letters before the Hindi voice | Spell them out in Devanagari in code | Needs a transliteration table or library for every word; the strip is one regex and never wrong about what it removes |
| Render test through Vite's `ssrLoadModule` | A browser test runner (Playwright) | A new dependency and a browser in CI; Vite and react-dom are already installed |

## 6. Known issues

- The pick costs latency on every turn (`docs/findings/language/latency_ab_20261128.txt`): ASR
  +172 ms p50 on the GPU on the Performance plan (+341 ms on Silent), +41 ms on Groq. Mic-stop
  to first audio went from 2034 to 2223 ms p50 on the GPU (12 turns each), already over the
  1000 ms target before. On Groq every turn is two paid requests: 10 turns a minute on Groq's
  20-a-minute limit, and half as many turns under the cap.
- The strip still fires in about 1 chunk in 6 in forced Hindi (31 of 197; 330 letters, down
  from 4.4% to 2.8% of all letters), mostly in long "teach me in 500 words" answers with code and
  brand names (`guard_probes_hi_note2_20261128.txt`). The note helped less than hoped.
- Hinglish detection needs Latin words in the transcript. When large-v3 writes the English words
  of Hinglish in Devanagari, the turn counts as Hindi: still a Devanagari reply, less mixed.
- The retry and the fallback are tested with a scripted model only; 0 of 33 forced-session probe replies
  needed one. The retry is a second paid LLM request.
- The committed CPU config keeps the pick off (+6.8 s on `small`), so on CPU the reply still
  follows the persona's own rule, as before.
