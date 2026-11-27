# 23 - Groq STT: a hosted speech-to-text engine for machines with no GPU

Branch `feat/groq-stt` (from `dev`, uncommitted). Protocol unchanged (no `contracts.md` edit).

## 1. What

Speech-to-text (STT, also called ASR) can now run in two places, picked by one config value,
`[asr] engine`. `"faster-whisper"` (the default, unchanged) runs Whisper on this machine.
`"groq"` sends each finished turn's audio to Groq, which runs Whisper on its own hardware
and sends the text back. Two settings both engines read, the forced `language` and the
`initial_prompt`, moved from `[asr.whisper]` up to `[asr]`. A stale old-style variable
(`VAANI_ASR__WHISPER__LANGUAGE`, `..._INITIAL_PROMPT`) now stops startup, naming the new one.

## 2. Why

The only local setup that transcribes Hinglish is `large-v3` on a GPU; `small` on a CPU
cannot (`docs/spikes/asr-hinglish.md`). Free hosting has no GPU. Groq runs Whisper for us.

**What now leaves the machine:** with `engine = "groq"`, every turn's recorded audio is
uploaded to Groq. Before this, audio never left the server; only text went to the LLM.

Measured, one request per clip, so no p50. The first smoke run used `whisper-large-v3-turbo`
(`docs/findings/groq-stt/smoke_20261125.txt`): `turn_ended` to `transcript.final` was 488 ms
(Hindi), 270 ms (English), 253 ms (Hinglish), each paying a fresh TLS connection, in the
range of GPU faster-whisper (`docs/findings/perf-1-latency-budget.md`, ASR row). **But
turbo wrote even the pure-Hindi clip in Latin letters.**

Why: Whisper's **prompt** is text the model treats as if it had just been said before the
audio, so it carries on in the same style. Ours is romanized Hinglish, to keep the English
words of Hinglish in Latin letters. Turbo copied that style for the Hindi words too. Without
the prompt, turbo wrote Devanagari; `whisper-large-v3` wrote Hindi in Devanagari and English
in Latin WITH the prompt, as large-v3 does on our GPU (`docs/findings/groq-stt/
script_20261125.txt`: 373 ms on the Hindi clip, 788 ms on the whole 7.9 s Hinglish file, the
request alone). So the committed model is `whisper-large-v3`.

## 3. How

1. **Startup.** `backend/vaani/app.py` calls `build_recognizer` (`vaani/asr/__init__.py`). For
   `"groq"` it checks that `VAANI_GROQ_API_KEY` (the same key the LLM uses) is set and that
   partial transcripts are off, then builds a `GroqRecognizer`. Either check failing stops the
   server, naming the setting, never its value. faster-whisper is imported only inside the
   other branch, so a Groq server never loads it (a test checks this in a fresh process).
2. **A turn ends.** `vaani/asr/runner.py` is unchanged: it calls `transcribe(audio, cancel)`
   exactly as for Whisper. `cancel` is the **cancellation token**: a flag (an `asyncio.Event`)
   that anyone can set to say "stop, nobody wants this any more".
3. **Spend cap first.** `GroqRecognizer.transcribe` (`vaani/asr/groq.py`) counts the request
   against its own `RequestCap` (`vaani/spend.py`, limit `[asr.groq] max_requests_per_process`)
   BEFORE sending anything. Past the cap it fails without a network call.
4. **Raw audio to a WAV file, in memory.** Our audio is **PCM**: bare 16-bit numbers, 16,000 per
   second, with nothing saying so. `pcm_to_wav` puts a 44-byte **WAV header** in front (rate,
   channels, sample size) using Python's built-in `wave` module, writing into `io.BytesIO`,
   a file that lives in RAM. Nothing touches the disk.
5. **The upload.** httpx sends one `POST /audio/transcriptions` as **multipart/form-data**:
   the encoding a browser uses to upload a file, one body holding several named parts. Here:
   the WAV, `model`, `language`, `prompt`, `temperature` and `response_format`. The key goes
   in the `Authorization` header only, never the URL (URLs end up in logs).
6. **Racing the cancel.** The request is wrapped in `until_cancelled`
   (`vaani/providers/streaming.py`, the helper the LLM providers already use). It waits for
   whichever comes first: Groq's answer or the token. If the token wins (a barge-in, or the
   runner's `timeout_s`), the request is torn down, closing the socket, and `transcribe`
   returns nothing at once. Unlike local Whisper, no thread is left finishing a decode.
7. **The answer.** Groq replies `{"text": ...}`. We return that text with the language we
   forced, which is what faster-whisper reports too when the language is forced.
8. **Failures.** Every failure becomes an `AsrError`, so the runner's existing `ASR_FAILED`
   path runs unchanged. The runner shows that message in the browser, so it holds only the
   status ("rate limited (HTTP 429), retry after 7 s", "API key rejected", "HTTP 503").
   Groq's own text can contain account details, so it goes to the server log only, with
   the key cut out.

## 4. When

- **At startup:** the key and partials checks, and the old-name check (`vaani/config.py`).
- **At the end of every turn:** one paid request per turn, never per frame. Not on the
  endpointing path: the turn has already ended when it starts.
- **During a barge-in:** setting the token aborts an upload or a wait for Groq at once.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Groq's hosted Whisper | `small` on the CPU, the committed default | It cannot transcribe Hinglish (`docs/spikes/asr-hinglish.md`) and is slower than GPU (perf-1, ASR rows). We give up privacy (audio leaves) and pay per turn |
| `whisper-large-v3` | `whisper-large-v3-turbo`: $0.04 an audio hour, not $0.111 | With our prompt it wrote Hindi in Latin letters (smoke run). Dropping the prompt for turbo alone would need new code, and might lose the Latin English words of Hinglish (turbo without the prompt was not tried on Hinglish) |
| Plain httpx multipart | Groq's Python SDK | A new dependency hiding the HTTP call, so we could not be sure a cancel closes the socket |
| WAV, uncompressed | FLAC (smaller upload, Groq's tip for size) | Needs an encoder library; a 30 s turn is under 1 MB as WAV, far below the 25 MB limit |
| A separate STT spend cap | Sharing the LLM's cap | One turn = one STT + one LLM request, so 200 would quietly mean 100 turns |
| Refuse partials with Groq | Allow them, with a warning | Each partial is a paid request billed as at least 10 s, and 20 a minute is the limit |
| Old setting names stop startup | Ignore them, as unknown keys are | A stale `.env` line would be dropped without a word, and the reader would never know why |

## 6. Known issues

- `whisper-large-v3` was checked on 2 clips, one request each, and never through the
  runner and endpointer: its `turn_ended` to `transcript.final` time is not measured. In
  the Hinglish file two words were unclear (`script_20261125.txt`, run d).
- Groq has no `vad_filter`, so trailing silence is sent too, and Whisper can invent text
  into silence (turbo added one stray `đ`). Silence was not tested on Groq.
- The first request of a process pays connection setup; no warm-up, on purpose (it would be
  a paid call). Not measured separately: each smoke run was a fresh process.
- Rate limits: 20 requests a minute, 2,000 a day (`config.toml` `[asr.groq]`, from Groq's
  docs, which call them Developer-plan limits). The real free-tier numbers need the key
  owner's console page. The turn log has no column for the ASR engine (schema unchanged).
- Through the real runner, Groq's large-v3 wrote an English clip in Devanagari letters in 3
  of 6 turns; local large-v3 wrote it in Latin in all 6 (`docs/findings/voice-studio/
  e2e_20261127.txt`). Not investigated: probably the forced `language = "hi"`.
