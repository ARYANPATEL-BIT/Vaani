# 16 - English voice: an English question gets an English answer

Branch `feat/english-voice` (from `dev`, uncommitted). Shared protocol v0.8.

## 1. What

Until this branch every reply was written in Devanagari and spoken by a Hindi voice,
even when the user spoke plain English. Now each persona has two Piper voices, one Hindi
and one English. The persona prompt tells the model to answer an all-English message in
plain English (Latin letters), and anything else in Devanagari as before. The server
looks at the script of the reply's first chunk and picks the matching voice for that
whole reply. No new protocol message: `agent.text` can now be Latin script, and the
`sample_rate` in `audio.start` may change from one reply to the next.

## 2. Why

An English speaker got a Hindi answer. In the prompt A/B run
(`docs/findings/english-voice/prompt_ab_20261008-150927.txt`), with the old prompt
**6 of 6** all-English messages (3 personas x Groq and Gemini) were answered in Hindi.
With the new prompt **5 of 6** were answered in English. Hindi and mixed messages were
still answered in Devanagari in all 12 cases, with one exception: one Groq reply slipped
8 Latin letters into a Devanagari sentence (known issues).

The Hindi voice could not simply read the English text: the day-12 listening test
(`12-chunking-tts.md`) rated Latin text through the Hindi voice unintelligible. So a
second voice per persona was needed, not only a prompt change.

The English voices are not slower. First-chunk synthesis for a 10-character chunk is
51 ms (kristin) and 38 ms (norman), against 38 ms for a 7-character Hindi chunk on the
same laptop (`docs/findings/reply-script/measure_tts_20261008-150*.txt`). Choosing the
voice is a single text scan of the first chunk and was not timed separately. A full
mic-to-first-audio run was not done on this branch.

## 3. How

1. **Startup.** The server loads two voices per persona from `[tts.piper.voices]` in
   `backend/config.toml`: `default` and `support` share kristin (female), `tutor`
   gets norman (male). Each persona keeps the same gender in both languages. If a
   persona has no voice for either language, the server refuses to start rather than
   go silent later. `vaani/app.py` runs that check. `vaani/tts/piper.py` loads each
   voice file only once, even when two personas use it.
2. **Session start.** `vaani/gateway.py` gives the turn pipeline the persona's *pair*
   of voices instead of one voice. `vaani/turns.py` and `vaani/reply.py` just pass the
   pair along.
3. **The prompt decides the language.** The three persona prompts in `config.toml` now
   say: if the user's latest message is entirely English, reply in plain English in
   Latin letters; otherwise use the old all-Devanagari rule. They also say "kal meeting
   hai" counts as Hindi, even though it is written in Latin letters. The model judges
   by the words, not the alphabet.
4. **The script decides the voice.** `vaani/language.py` answers one question: does
   this text contain any Devanagari character? Yes means "hi", no means "en". One
   Devanagari letter is enough, so a mixed reply stays on the Hindi voice.
5. **Locked on the first chunk.** In `vaani/speaker.py`, the first chunk of a reply
   picks the voice, and the server announces that voice's sample rate in `audio.start`.
   Every later chunk uses the same voice. If a later chunk is in the other script,
   the locked voice reads it anyway and a "script drift" warning is logged.
6. **Small supporting changes.** The chunker now treats `a.m` and `p.m` as
   abbreviations, so it does not cut "8 a.m. tomorrow" in the middle of a sentence.
   `scripts/fetch_models.py` downloads the English voices. CI caches `en_US-*.onnx`.
   `scripts/ask.py` prints which voice a reply would get. `docs/contracts.md` and
   `vaani/protocol.py` record v0.8.

## 4. When

- **Process start:** both voices of every persona are loaded and checked, once.
- **`session.start`:** the session's persona fixes which pair of voices it will use.
- **Every turn, at the LLM call:** the language rule is part of the system prompt,
  which is sent with every turn, so each new message is judged on its own. An English
  turn can follow a Hindi one in the same conversation.
- **Every turn, at the first chunk:** the moment the chunker cuts the first piece of
  the streamed reply, before any audio exists, the voice is picked. That is the only
  new step on the conversation path.
- **Every later chunk:** script compared to the locked voice. Logged on mismatch, nothing
  else changes.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Pick the voice from the reply's **script** (any Devanagari = Hindi) | A language-identification library run on the reply text | It would add a dependency and some time to the hot path to answer a question the text already answers. The voice only cares about the alphabet it has to read, and that is exact. |
| Pick the voice from the **reply** | Pick it from the user's language as detected by Whisper | On day 10, Whisper's auto-detect labelled one Hindi speaker `hi`, `ur` (Urdu) and `la` on different clips (`10-asr.md`, the language row and section 6). That is why we force `hi` and get no detected language back. Even with a correct label, the model can still answer in the other script, and the voice has to match what was actually written. |
| **Lock** the voice on the first chunk | Switch the voice whenever a chunk's script changes | `audio.start` announces one sample rate per reply. Changing voice mid-reply would also sound like a second speaker joining in. |
| The **prompt** decides the reply language | The server detects the language and tells the model which one to use | That needs the detection step above (and Whisper's guess) before every LLM call. The model already sees the whole message and handles Hinglish written in Latin letters better. |
| Piper **en_US-kristin / en_US-norman** (medium) | `en_US-lessac`, Piper's best-known English voice | Lessac's training data (Blizzard 2013) is treated as research-only, and that excludes every voice fine-tuned from it. Kristin and Norman are public-domain LibriVox recordings, trained from scratch. |
| **Two single-language voices** per persona | One multilingual voice (XTTS) for both languages | XTTS is a larger model meant for cloning in the studio. Its CPU speed on the reply path was never measured (`12-chunking-tts.md`), while Piper's is: 38-51 ms for a first chunk. Each Piper voice is trained on one language only, so two languages need two voices. |
| `a.m` / `p.m` added as **abbreviations** | Leave them out | "at 8 a.m. tomorrow" would be cut after "a.m." and spoken as two chunks with a pause in the middle of the sentence. The cost: a sentence that really ends in "a.m." runs into the next one. |

## 6. Known issues

- English question, Hindi answer on Groq: 1 of 6 in the run files (tutor), and confirmed live ("can you tell me what data science is and how it could help me in my career").
- Latin words inside a Devanagari reply ("yaad dila", default/hi/Groq) are read by the Hindi voice with English spelling rules. The chunk still contains Devanagari, so it is not even logged as drift.
- Gemini returned 429 (quota exhausted) during the live demo, so that day there was no failover at all. When it does answer, its first token took 777-1519 ms, past the 1,000 ms target.
- A sentence that really ends in "a.m." or "p.m." runs on into the next chunk.
- No end-to-end mic-to-first-audio measurement exists for this branch yet.
