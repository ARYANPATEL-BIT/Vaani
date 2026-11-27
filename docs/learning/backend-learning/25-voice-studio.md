# 25 - Voice studio: enrol your own voice, hear a script in it

Branch `feat/voice-studio` (from `dev`, uncommitted). New server `studio/`; routes in
`docs/contracts.md` section 4 (STUDIO API v0.1); shared socket protocol unchanged.

## 1. What

Phase 2's first piece. On `/voice` a signed-in user enrols their **own** voice (a 10 to 30 s
sample plus a live challenge phrase), types a script in Hindi, English or both, and gets it
back as a WAV in that voice, to play or download. One button deletes the voice and everything
made from it. It runs in a **second server process**, `studio/voice_studio/`, on its own
**port** (a numbered door on the machine: the backend is 8000, the studio 8100). The four old
`/enrol` pages are deleted: they called `/api/enrol/*` routes that never existed, and serving
those routes was not enough, because their flow had no live random phrase and no upload.

## 2. Why

Voice cloning means making a model speak new sentences in a voice it heard for a few seconds.
Our model is **Chatterbox Multilingual v3** (Resemble AI, MIT licence). It is a big neural
network that needs **torch** (the GPU maths library, several GB). Putting it inside the
backend would add torch to `backend/uv.lock` and the Render image, and a GPU memory failure
would happen inside the process that runs live conversations. A separate process avoids both.

The two enrolment thresholds were measured
(`docs/findings/voice-studio/calibration_20261126-151301.txt`). The spike's clip A, recorded
through laptop auto gain at about 6 dB SNR, cloned into audio with no words in it. The
spike's clips read 5.9 to 11.8 dB and clean recordings 29.0 to 43.7, so the floor is 20. The
same person on two clean recordings scored 0.914 to 0.947 on the speaker check and synthetic
other voices at most 0.443, so the floor is 0.75.

Measured: about 3.3 GB of GPU memory at peak, and the Perth watermark found in every sentence.
**RTF** (real-time factor) is seconds of work per second of audio made: under 1 is faster
than real time. Speed was **not stable** on this laptop. A 2-sentence script took 26 to 29 s
warm in its usual "slow" state (RTF about 6), one short sentence 2.2 s in a brief "fast"
state (RTF about 0.9); the cause was not found (`docs/findings/voice-studio/notes_20261126.txt`).
Through the real server and the Vite proxy the same script took 29.4 and 30.9 s warm
(`e2e_20261126.txt`).

## 3. How

1. **One origin.** The browser only talks to Vite's server (:5173). Vite forwards `/studio`
   to :8100 (`frontend/vite.config.js`), just as it forwards `/auth` and `/ws` to :8000. To
   the browser everything is one site, so it sends the `vaani_session` cookie along. If the
   studio is not running, Vite answers 502 and the page says "the voice studio is not running".
2. **Who is asking** (`access.py`). The cookie is "user details + an HMAC signature": a
   fingerprint made with a secret key, which nobody can forge without the key (doc 22). The
   studio checks it with the backend's own `read_cookie` and the backend's own settings. That
   works because `studio/` installs `backend/` as an **editable dependency**: it imports the
   backend's code straight from `backend/vaani/`, so the check is never copied. No valid
   cookie means 401. A POST or DELETE also needs an allowed `Origin` header, as in `auth.py`.
3. **Consent (ETH-3).** The page shows the consent text it got from `GET /studio/voice` and a
   checkbox. Only a ticked box sends that text back. The studio stores it word for word with a
   UTC timestamp in `consent.json`, and refuses to generate anything without that file.
4. **The sample** (`audio_checks.py`). The page records with the browser's voice-call filters
   OFF (`useMicRecorder.js`): auto gain turns the volume up in pauses, so room noise swells
   between words, which is what wrecked clip A (section 2). A phone file can be uploaded
   instead. PyAV decodes any of WebM, M4A, MP3 or WAV. The length must be 10 to 30 s.
   **SNR** (signal-to-noise ratio) is how far the voice sits above the background, in dB. We
   cut the clip into 20 ms frames: the quietest tenth shows the noise, the loudest tenth the
   speech, and the gap is the SNR. Below 20 dB the studio refuses and says how to fix it.
5. **The live challenge (ETH-1, ETH-2)** (`verify.py`). The studio draws 5 random words (valid
   5 minutes, memory only) and the user reads them aloud. Two checks: Whisper `small` on CPU,
   the backend's own recogniser, must hear at least 4 of the 5 words (a clip recorded earlier
   cannot contain them). Then a **speaker embedding**: 256 numbers that describe WHO speaks,
   not what is said, from Chatterbox's own voice encoder. The **cosine** of two embeddings is
   1.0 when they point the same way. Sample against phrase must reach 0.75, so someone who
   uploads another person's clip and reads the phrase themselves is refused. Only after all
   checks pass are `reference.wav`, `embedding.npy` and `consent.json` written, consent last.
6. **Generate** (`generate.py`, `script.py`, `model.py`). Cheap refusals first: no consent, a
   script over 300 characters or a sentence over 250, the daily cap (30 in 24 h, counted from
   `provenance.jsonl`), another generation running. The script is cut into sentences; one
   with any Devanagari is Hindi, else English (the agent's own rule, `vaani/language.py`). The
   model **loads lazily**: on the first generate, not at startup, so an unused studio holds no
   GPU memory. It runs on a **worker thread** so the server keeps answering meanwhile. The
   **cancellation token** is a `threading.Event` checked between sentences: if the browser
   leaves (or Cancel is pressed), the route notices the closed request and sets it. A sentence
   already inside the model cannot be stopped. If CUDA runs out of memory, the half-built
   model is dropped and the user gets `STUDIO_GPU_BUSY`; the next request tries again.
7. **Provenance (ETH-5).** The file gets a WAV comment (model, generation id, time, script
   hash) and a line in `provenance.jsonl` (user id, time, script sha256, duration, no text).
   Chatterbox also adds **Perth**, an inaudible watermark marking it as AI-made; we never
   disable it, and `model.py` refuses to run if it failed to load (a spike bug).
8. **Delete (ETH-4).** `DELETE /studio/voice` removes the user's folder (sample, embedding,
   consent, generated audio) and any pending phrase. The provenance lines stay: no voice data.

## 4. When

At studio startup: settings, the cookie secret, Whisper `small` and the voice encoder load
(CPU). On `/voice`: one `GET /studio/voice`. On enrol: one request runs every check. On the
first generate: Chatterbox downloads (first run only, about 3 GB) and loads. Never during a
conversation: the voice agent does not know the studio exists.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Chatterbox Multilingual v3 | XTTS-v2 | Faster on the GPU in the spike (RTF 0.29), but its CPML licence is non-commercial, and it failed 2 of 11 spike clips (`docs/findings/voice-cloning/xtts_cuda_clip_a_take1_run_20261121-211638.tsv`) |
| One multilingual model | IndicF5 for Hindi | Gated weights (a Hugging Face login to accept terms), needs the exact transcript of the sample, and RTF 1.7 to 1.9 on the GPU (`indicf5_cuda_*`) |
| v3 from a pinned GitHub commit | PyPI `chatterbox-tts` 0.1.7 | 0.1.7 can only load the older v2 checkpoint |
| A separate process | Routes in the backend | torch in the backend's lock and image; a GPU failure inside live conversations |
| Editable `vaani` dependency | Copy the cookie check | Two copies of security code drift apart |
| Chatterbox's voice encoder | SpeechBrain ECAPA | A second model and dependency for the same job |
| SNR 20 dB, cosine 0.75 | The spike recorder's 25 dB | It needs a silent lead-in; uploads have none (`calibration_20261126-151301.txt`) |
| Change the client | Serve `/api/enrol/*` | Their flow had no live phrase or upload; every page needed rewriting anyway |

## 6. Known issues

- Slow: about RTF 4 per sentence on the Performance plan too, with or without Whisper on
  the GPU (`e2e_20261127.txt`); the 11-26 "fast state" never came back. Cause still unknown.
- Beside the agent's Whisper large-v3 it fits (7.4 of 8.1 GB, no out-of-memory), but each
  agent turn is about 1 s slower while it generates; with Groq ASR, no slowdown (same file).
- Thresholds rest on one real person and synthetic "other" voices; two devices not measured.
- Not run in a browser yet: both end-to-end checks used HTTP and Windows SAPI voices, which
  prove the flow, not cloning quality (`e2e_20261126.txt`, `e2e_20261127.txt`).
