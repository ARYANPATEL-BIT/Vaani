# 08 — Hinglish Test Set — Part 1

## 1. What we built in this branch

Branch: `data/hinglish-test-set`

Official Week 2 Day 3 requirement (from Vaani_4_Week_Build_Plan.docx):
**"Hinglish test set, part 1: script 100 utterances mixing Hindi and English,
record the first half."**
Done when: **"50 recordings with exact ground-truth text are committed."**

This branch delivers:

1. **`docs/test-sets/hinglish-100.json`** — The complete 100-utterance manifest.
   All sentences mix Hindi and English. IDs are H1-001 through H1-100.
   Part 1 (H1-001 to H1-050) is designated for recording this day.
   Part 2 (H1-051 to H1-100) is scripted and ready for Day 4 recording.

2. **`data/hinglish-test-set/record_hinglish.py`** — Interactive CLI recording
   utility. Presents each Part 1 utterance to the speaker, records microphone
   input via sounddevice, and saves 16 kHz mono PCM-16 WAV files to
   `data/hinglish-test-set/audio/`.

3. **`data/hinglish-test-set/validate_hinglish.py`** — Validation script that
   checks every Part 1 recording for existence, format correctness, and
   ground-truth mapping.

4. **`data/hinglish-test-set/audio/`** — Directory where the 50 recordings are
   saved (one per utterance, named `H1-001.wav` through `H1-050.wav`).

> **Recording status:** The 50 recordings are captured through human speech
> using the interactive `record_hinglish.py` script. This document describes
> the procedure; the actual completion state is reflected by running
> `validate_hinglish.py`.

## 2. Why the test set is needed

`docs/findings/perf-1-latency-budget.md` states that the ASR latency numbers
are **preliminary** because they were measured on TTS-synthesised clips, not
real human speech. The finding explicitly calls for "Aryan's 10 Hinglish
recordings" to produce real p50/p95 figures. The official build plan formalised
this into 100 human-recorded utterances split across two days.

The distinction matters because:
- TTS audio has clean, consistent prosody. Human voice has accent, hesitation,
  natural pauses, and varied pace.
- faster-whisper's Silero VAD behaves differently on human speech vs TTS.
- The ASR decode time grows with clip duration; TTS clips were short.
- Without real speech, WER cannot be measured at all.

## 3. Corpus structure — the 100 utterances

All 100 utterances are in **Romanized Hinglish**: Hindi words written in Latin
script, with English words appearing naturally in the same sentence. No
Devanagari script is in the ground-truth text because the speaker reads them
aloud; the ASR output may produce Devanagari for Hindi words, and that is what
the test evaluates.

Example ground truth vs expected ASR output:

| Ground truth (what speaker reads) | Expected ASR script in transcript |
|---|---|
| `Mujhe kal ka meeting schedule check karna hai.` | `मुझे कल का meeting schedule check करना है।` |
| `Yeh app bahut slow hai, update karna padega.` | `यह app बहुत slow है, update करना पड़ेगा।` |

**Note:** `expected ASR script` is the anticipated output from the spike
(`docs/spikes/asr-hinglish.md`). It is NOT a measured result.

### Category distribution

| Category | Count | Example |
|---|---|---|
| conversational | 10 | "Yaar, aaj traffic bahut zyada tha, office late pahuncha." |
| technology | 14 | "Mera laptop restart ho gaya, sab files band ho gayi." |
| work | 10 | "Client call hai ek ghante mein, prepare ho gaye?" |
| college | 5 | "Assignment deadline kal hai, abhi tak complete nahi hua." |
| money | 9 | "Yeh phone kitne ka hai, EMI available hai kya?" |
| scheduling | 6 | "Meeting teen baje hai, conference room book kiya kya?" |
| travel | 5 | "Airport se cab book karo, flight six baje land karti hai." |
| question | 5 | "Samajh nahi aaya, thoda aur explain kar sakte ho?" |
| command | 3 | "Please presentation ka PDF share kar do abhi." |
| food | 5 | "Lunch mein kya order karein, pizza ya biryani?" |
| health | 4 | "Gym membership join karna hai, monthly fee kitni hai?" |
| entertainment | 8 | "Netflix par koi acchi series recommend karo please." |
| family | 9 | "Bhai ka birthday gift online order kiya, delivery track karo." |
| code-switch-heavy | 1 | "Vaani app ka beta version release ho gaya kya, testing kab shuru karein?" |

### Length distribution

- **Short** (under 8 words): ~40 utterances — quick commands, questions
- **Medium** (8–14 words): ~60 utterances — full conversational sentences

All utterances are suitable for a single-turn voice assistant exchange.

## 4. Recording format

| Property | Value |
|---|---|
| Format | WAV |
| Sample rate | 16,000 Hz |
| Channels | 1 (mono) |
| Bit depth | 16-bit signed PCM |
| Byte order | Little-endian |
| Naming | `H1-NNN.wav` (zero-padded 3-digit number) |
| Location | `data/hinglish-test-set/audio/` |

This matches the project's existing audio format (`contracts.md`, section 2.1:
"Raw PCM, 16-bit signed little-endian, 16,000 Hz, 1 channel").

## 5. Recording procedure

1. Run from the repo root:
   ```
   python3 data/hinglish-test-set/record_hinglish.py
   ```
2. The script reads the manifest, identifies unrecorded Part 1 utterances, and
   prompts them one at a time.
3. The speaker reads the displayed sentence aloud (in the quiet indoor
   environment), pressing Enter to start and Enter again to stop.
4. The script saves the WAV, prints duration and format properties, and advances
   to the next utterance.
5. `s` + Enter skips an utterance (can return later). `q` + Enter quits; the
   script resumes from where it left off on next run.
6. Run `validate_hinglish.py` at any point to check progress.

## 6. Ground-truth format

The ground truth for each utterance is the `text` field in
`docs/test-sets/hinglish-100.json`. It is the EXACT sentence the speaker reads.
It is not an ASR output, not an approximation, and must not be modified unless
the recording is re-recorded.

The manifest maps recording to ground truth unambiguously:

```json
{
  "id": "H1-001",
  "part": 1,
  "category": "conversational",
  "text": "Mujhe kal ka meeting schedule check karna hai.",
  "length": "short"
}
```

The corresponding WAV is `data/hinglish-test-set/audio/H1-001.wav`.
Aryan's later benchmark script reads `text` from the manifest, runs ASR on the
WAV, and computes WER against that `text`.

## 7. Validation performed

Run `validate_hinglish.py` to check:

| Check | What is verified |
|---|---|
| 100 utterances scripted | `len(utterances) == 100` |
| No duplicate IDs | `len(set(ids)) == 100` |
| No duplicate texts | `len(set(texts)) == 100` |
| 50 WAV files present | H1-001.wav through H1-050.wav all exist |
| Sample rate | 16,000 Hz |
| Channels | 1 (mono) |
| Bit depth | 16 bit |
| Duration | >= 0.5 s (warn if shorter) |
| Ground-truth coverage | Every recorded ID has a non-empty `text` |

## 8. When things go wrong

| What fails | What to do |
|---|---|
| `sounddevice` import error | `pip3 install sounddevice --break-system-packages` |
| Recording is too short | Re-record: delete the WAV, run the script again |
| Speaker pauses too long mid-sentence | VAD in ASR may split into two turns — re-record as one continuous utterance |
| WAV is stereo (wrong mic) | Check macOS audio settings; switch to a mono or mono-configured input |
| Missed some utterances | Run `record_hinglish.py` again; it skips already-recorded files |
| validate_hinglish.py reports missing | The count of missing files is the remaining blocker |

## 9. What is different from the earlier feat/hinglish-test-set-1 attempt

The earlier attempt (`feat/hinglish-test-set-1`, commit `d54cd2d`) created:
- 14 test cases with category-based IDs (H1-PH-01 style)
- No recordings whatsoever

The current branch (`data/hinglish-test-set`) follows the official plan exactly:
- 100 utterances (10× more)
- Sequential IDs (H1-001 through H1-100)
- Interactive recording script
- Validation script
- Correct directory structure with audio stored in `data/hinglish-test-set/audio/`

## 10. Limitations

- One speaker only (Samyak). WER on one speaker reflects one accent/style.
  Part 2 or a follow-up sprint should add a second speaker for robustness.
- No background noise cases in Part 1. Real-world usage includes street noise,
  fan hum, and overlapping speech. Part 2 could add a noisy subset.
- All utterances are Romanized. The speaker has no Devanagari text to read.
  The ASR evaluation tests the model's code-switching ability, not the speaker's
  ability to produce Devanagari phonetics.
- Measuring WER against the ground-truth requires Aryan's `measure_asr.py`
  script to be extended to accept a JSON manifest input. That work is not part
  of Day 3.

## 11. Questions you could be asked

1. **Where is the ground-truth text for H1-023?**
   `docs/test-sets/hinglish-100.json`, `utterances` array, object with
   `"id": "H1-023"`, `text` field:
   `"Train saat baje hai, ghar se paanch baje nikalna padega."`

2. **Where is the recording for H1-023?**
   `data/hinglish-test-set/audio/H1-023.wav`

3. **Why are all sentences in Roman script, not Devanagari?**
   The speaker reads Roman transliteration and speaks Hindi. The ASR system's
   job is to produce the correct Devanagari/Latin mixed output. If the prompt
   were Devanagari, the speaker could not read it reliably during recording.

4. **Why 16 kHz mono 16-bit?**
   This matches `contracts.md` section 2.1 exactly — it is the wire format
   the frontend sends over WebSocket. Using the same format means ASR test
   inputs match what the production pipeline receives.

5. **What is WER and how will it be measured?**
   Word error rate: `(substitutions + deletions + insertions) / reference_words`.
   It requires the ASR to produce a transcript, which is then compared word-by-word
   against the ground-truth `text` field. This measurement is not done in Day 3.

6. **What prevents the recordings from being TTS?**
   The recording script captures only microphone input (sounddevice InputStream
   from the default input device). No synthesis call is made. The validator
   checks that files exist and are non-trivially short; it cannot
   cryptographically distinguish human from TTS, so the process relies on the
   speaker's honesty.

7. **Did we modify any backend or frontend code?**
   No. Only new files were created under `docs/test-sets/` and
   `data/hinglish-test-set/`. No existing files were modified.

## 12. Check yourself

1. What does the `text` field in `hinglish-100.json` represent, and what does it NOT represent?
2. How does Aryan's benchmark script know which WAV file corresponds to which ground-truth text?
3. What would a WER of 0% mean, and why would that be suspicious?
