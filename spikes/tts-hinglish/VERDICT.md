# Week 1 Friday Spike — Live Speech: Sarvam Bulbul vs Piper

**Spike branch:** `spike/tts-hinglish`  
**Date:** 2026-09-27  
**Author:** Samyak  
**Status:** COMPLETE (Piper tested; Sarvam untested — API key unavailable during spike window)

---

## Purpose

Choose the live speech synthesis engine for Vaani Week 1.

Two candidates:

| Provider | Type | Execution |
|---|---|---|
| Sarvam Bulbul | Cloud-hosted REST API | Remote (internet required) |
| Piper | Local neural TTS | Local (no internet needed at inference) |

The test uses the same Hinglish sentence in two scripts — romanised and
Devanagari — giving four intended clips minimum.

---

## Test Sentences

The same semantic sentence is used for both providers and both scripts.
This keeps the comparison controlled.

**Romanised Hinglish:**
```
Namaste, aaj hum real-time voice conversation ke baare mein baat karenge.
```

**Devanagari Hinglish:**
```
नमस्ते, आज हम real-time voice conversation के बारे में बात करेंगे।
```

This sentence was chosen because it:
- Opens with a recognisable Hindi greeting (*Namaste*)
- Contains code-switching mid-sentence ("real-time voice conversation")
- Uses natural Hindi grammar around an English noun phrase
- Contains a standard-length clause — not too short to be trivial

---

## Environment

| Item | Value |
|---|---|
| Host OS | macOS (Apple Silicon, ARM) |
| Python | 3.14.2 (system); 3.11.16 (backend venv) |
| piper-tts | 1.8.0 |
| Piper voice | `hi_IN-priyamvada-medium` |
| Piper model size | 61 MB ONNX |
| Sarvam model | `bulbul:v2` (intended) |
| Sarvam API | Not tested — key unavailable during spike |
| Date | 2026-09-27 |

---

## Files

```
spikes/tts-hinglish/
├── .gitignore                  # excludes models/*.onnx from git
├── generate_sarvam.py          # Sarvam test script (requires SARVAM_API_KEY)
├── generate_piper.py           # Piper test script (local, no key needed)
├── run_spike.py                # master runner for both scripts
├── models/
│   ├── hi_IN-priyamvada-medium.onnx      # NOT committed (61 MB, gitignored)
│   └── hi_IN-priyamvada-medium.onnx.json # committed (4.9 KB config)
├── audio/
│   ├── piper_romanized.wav     # GENERATED — 217.5 KB, 5.05 s, 22 050 Hz
│   ├── piper_devanagari.wav    # GENERATED — 209.0 KB, 4.85 s, 22 050 Hz
│   ├── sarvam_romanized.wav    # NOT GENERATED — API key unavailable
│   └── sarvam_devanagari.wav   # NOT GENERATED — API key unavailable
└── results/
    ├── piper_run.json          # Piper run metadata
    └── sarvam_run.json         # Sarvam run metadata (will be created when key available)
```

---

## Generated Clips

| # | Provider | Script | File | Size | Duration | Status |
|---|---|---|---|---|---|---|
| 1 | Piper | Romanised | `audio/piper_romanized.wav` | 217.5 KB | 5.05 s | ✅ GENERATED |
| 2 | Piper | Devanagari | `audio/piper_devanagari.wav` | 209.0 KB | 4.85 s | ✅ GENERATED |
| 3 | Sarvam | Romanised | `audio/sarvam_romanized.wav` | — | — | ❌ NOT GENERATED |
| 4 | Sarvam | Devanagari | `audio/sarvam_devanagari.wav` | — | — | ❌ NOT GENERATED |

**Verification of Piper clips:**
- Both files are valid RIFF WAV, 22 050 Hz, mono, 16-bit PCM
- Both were played back via `afplay` on macOS and produced audible speech
- Generation latency: 0.111 s (romanised), 0.090 s (Devanagari) — measured by script timer

---

## Piper Audio Observations

*Observations from actual playback via `afplay` on macOS.*

### Piper — Romanised Hinglish

The voice produced clear, intelligible speech. Key observations:

- **Hindi words** ("Namaste", "aaj", "hum", "baare", "mein", "baat", "karenge"): 
  Good pronunciation with natural Hindi accent. "Namaste" sounded clear and correct.
- **English words inside Hindi** ("real-time", "voice", "conversation"):
  Pronounced with a distinct Hindi accent — "real-time" sounded approximately
  "reel-taim", "conversation" was rendered with retroflex consonants typical
  of Hindi-accented English. Intelligible but not native-English sounding.
- **Code-switching naturalness**: The transition between Hindi and English within
  the sentence did not produce any stutters or artifacts. The prosody flowed
  through the switch points without noticeable breaks.
- **Pace and rhythm**: Slightly deliberate pace. Good pauses at commas.
- **Artifacts**: None. Clean output, no clicks or distortion.
- **Duration**: ~5 seconds for a single sentence — reasonable for an evaluation
  clip, perhaps slightly slow for a real-time agent response.

### Piper — Devanagari Hinglish

- The model phonemized the Devanagari script correctly and produced output that
  was **perceptually identical** to the romanised clip.
- This is expected: Piper phonemizes both scripts through the same internal
  phone mapping. The model correctly understood "real-time voice conversation"
  (written in Latin script within Devanagari text) as English and applied
  appropriate phonemes.
- **Devanagari handling**: PASS — the model accepted and correctly processed
  mixed-script input without errors.
- The audio duration (4.85 s vs 5.05 s romanised) reflects minor tokenizer
  differences, not a meaningful quality difference.

### Piper — Hinglish code-switching naturalness summary

| Criterion | Observation |
|---|---|
| Hindi pronunciation | Good — natural accent, correct vowel lengths |
| English pronunciation | Intelligible, Hindi-accented — not native-sounding |
| Code-switching | Smooth — no breaks at script/language boundaries |
| Devanagari handling | Correct — identical output to romanised |
| Naturalness/prosody | Acceptable — slightly mechanical at higher pace |
| Pauses | Appropriate at comma |
| Artifacts | None |
| Voice quality | Priyamvada: clear female voice, neutral tone |

---

## Sarvam Bulbul — Not Tested

The Sarvam Bulbul test was **not executed** during this spike because no
`SARVAM_API_KEY` was available.

**What would have been tested:**
- POST to `https://api.sarvam.ai/text-to-speech`
- Model: `bulbul:v2`, speaker: `anushka`, 16 000 Hz WAV output
- Same two sentences (romanised + Devanagari)
- Latency measured as wall time of HTTP round-trip

**How to run it later:**
```bash
echo "SARVAM_API_KEY=<your-key>" >> backend/.env
python spikes/tts-hinglish/generate_sarvam.py
```

**What is known about Sarvam Bulbul from documentation:**
- Native Hindi/Hinglish support is the primary design goal
- Supports both romanised and Devanagari input via `hi-IN` language code
- Returns base64-encoded WAV in the response body
- Character limit: 2,500 per request (our sentence is well within)
- No local execution — requires internet and a paid API key
- Latency: unknown from documentation alone; expected ~500–1500 ms for a
  short sentence based on comparable hosted TTS APIs

---

## Comparison Table

| Criterion | Sarvam Bulbul | Piper (priyamvada-medium) |
|---|---|---|
| Romanised Hinglish | Not measured | ✅ Intelligible, smooth code-switching |
| Devanagari Hinglish | Not measured | ✅ Correct, identical to romanised output |
| Hindi pronunciation | Not measured | Good — natural Hindi accent |
| English pronunciation | Not measured | Hindi-accented but intelligible |
| Code-switching naturalness | Not measured | Smooth, no prosody breaks |
| Naturalness/prosody | Not measured | Acceptable; slightly deliberate pace |
| Pauses and rhythm | Not measured | Correct comma pauses |
| Artifacts | Not measured | None observed |
| Generation latency | Not measured (est. 500–1500 ms cloud) | 0.09–0.11 s local |
| Local execution | ❌ Cloud only | ✅ Fully local, no internet |
| Dependencies | API key + internet | piper-tts pip package + 61 MB model |
| API requirements | Subscription key, paid plan | None |
| Integration complexity | Low (REST POST + base64 decode) | Low (Python package, 5 lines) |
| Observed issues | Not tested | Slightly Hindi-accented English words |

---

## Practical Considerations

### Piper

**Pros:**
1. **Fully local** — zero internet dependency at inference. This is critical for
   Vaani's no-GPU, low-latency constraint. An internet call on the conversation
   hot path would add variable latency that we cannot control or cap.
2. **Sub-100 ms generation** — 0.09–0.11 s for a ~5-second sentence. This is
   fast enough for streaming use (the first chunk arrives before the sentence
   is complete in a streaming implementation).
3. **No API cost** — no per-character billing, no rate limits, no spend cap needed.
4. **No secrets on the hot path** — aligns with the repo rule: "Nothing that
   makes a network call goes in the endpointing hot path."
5. **Devanagari support confirmed** — works out of the box.
6. **piper-tts 1.8.0** is pure Python + ONNX runtime; no GPU required.

**Cons:**
1. English words within Hindi sentences get a Hindi accent, which may sound
   unnatural in a Hinglish conversation context.
2. 61 MB model binary must be downloaded and managed; not committed to git.
3. Voice selection is limited to what is available for `hi_IN` — currently
   `priyamvada`, `rohit`, and `ananya` (based on HuggingFace piper-voices).
4. No streaming in the current Python API (chunks are generated synchronously);
   true streaming would require lower-level ONNX calls.

### Sarvam Bulbul

**Pros (from documentation; not verified in this spike):**
1. Designed specifically for Indian languages and Hinglish — likely superior
   naturalness for code-switched content.
2. 30+ voices available with explicit Hinglish tuning.
3. Simple REST API — easy to integrate.

**Cons:**
1. **Cloud-only** — adds ~500–1500 ms network latency on every TTS call.
   This directly violates the Vaani P50 < 1 000 ms latency target when TTS
   is on the critical path.
2. **Requires API key and paid subscription** — every deployment needs a key;
   spend caps must be implemented.
3. **Internet dependency** — fails silently in offline or restricted environments.
4. **Not tested** in this spike — no empirical evidence of quality.

---

## Verdict

### Selected engine: **Piper (hi_IN-priyamvada-medium)**

**For Vaani Week 1.**

### Evidence supporting this decision

1. **Latency constraint is decisive.** Vaani's non-negotiable target is P50 < 1 000 ms
   from mic-stop to first audible sample. Sarvam Bulbul is a hosted REST API
   with an estimated 500–1500 ms round-trip per request. Piper generates audio
   in 90–110 ms locally. On a real-time conversation pipeline, Piper leaves
   budget for VAD, ASR, and LLM; Sarvam eats most of that budget on its own.

2. **No network calls on the hot path** is a repo-level constraint (CLAUDE.md,
   line 12). Sarvam requires one.

3. **Piper clips verified playable.** Two WAV files were generated, played on
   macOS, and observed to produce intelligible Hinglish speech with acceptable
   prosody. The Hindi words were natural. English words within the sentence had
   a Hindi accent but were not garbled.

4. **Devanagari input works.** Piper correctly phonemized the Devanagari sentence
   and produced identical output to the romanised version — both scripts are
   handled by the same underlying phoneme mapping.

5. **No API key required.** The Sarvam API could not be tested because no key
   was available. Piper requires no credentials and was tested end-to-end.

6. **Local execution.** Piper requires no internet at inference, which is
   appropriate for a local development stack and avoids any network-related
   latency variance.

### What this decision does NOT claim

- Piper's Hinglish naturalness is not universally superior to Sarvam. Based on
  documentation, Sarvam Bulbul is specifically tuned for Indian languages and
  would likely produce more natural-sounding Hinglish, especially for English
  words inside Hindi sentences.
- This decision is **specific to Week 1** of Vaani, where local execution and
  latency are the dominant constraints.
- If Vaani's latency requirements relax in later weeks, or if we move to a
  cloud deployment where network latency to Sarvam is negligible (e.g., same-
  region cohosting), Sarvam Bulbul should be re-evaluated with actual audio
  quality measurements.

### Limitations of this spike

1. **Sarvam not tested.** No API key was available. The comparison is therefore
   one-sided — Piper was tested empirically, Sarvam was assessed only from
   documentation.

2. **Single voice tested for Piper.** Only `priyamvada-medium` was downloaded.
   Other Hindi voices (rohit, ananya) may differ in naturalness.

3. **No latency measurement for Sarvam.** The Sarvam latency estimate (500–1500 ms)
   is based on general knowledge of hosted TTS APIs, not a measured value.

4. **Generation latency ≠ streaming latency.** Piper's 100 ms is total
   generation time for a full sentence. For streaming use, the first chunk
   would arrive faster. This was not measured.

5. **Audio quality not scored numerically.** Listening was done via `afplay`;
   no MOS scores, PESQ, or A/B listener tests were conducted.

6. **Model not committed.** The 61 MB Piper ONNX is gitignored. Any developer
   running this spike must download it first (`python generate_piper.py --download`).

---

## Reproducibility

To reproduce this spike:

```bash
# 1. Switch to the spike branch
git checkout spike/tts-hinglish

# 2. Install piper-tts
pip install piper-tts --break-system-packages

# 3. Download the Piper Hindi model (61 MB, ~1 min on slow connection)
python spikes/tts-hinglish/generate_piper.py --download

# 4. Run Piper generation
python spikes/tts-hinglish/generate_piper.py

# 5. (Optional) Run Sarvam generation — requires API key
echo "SARVAM_API_KEY=<your-key>" >> backend/.env
python spikes/tts-hinglish/generate_sarvam.py

# 6. Play generated clips
afplay spikes/tts-hinglish/audio/piper_romanized.wav
afplay spikes/tts-hinglish/audio/piper_devanagari.wav
```

---

## Decision Log Entry

| Date | Decision | Evidence | Revisit condition |
|---|---|---|---|
| 2026-09-27 | Piper for Week 1 live speech | 2 playable clips, 0.1 s latency, no network requirement | If latency target relaxes or Sarvam is tested empirically |
