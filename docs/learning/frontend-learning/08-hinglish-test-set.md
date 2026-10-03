# 08 — Hinglish Test Set & Benchmark Manifest

## 1. What we built in this branch

Branch: `data/hinglish-test-set`

Official Week 2 Day 3 & Day 4 requirements (from `Vaani_4_Week_Build_Plan.docx`):
- **Day 3 Task**: *"Hinglish test set, part 1: script 100 utterances mixing Hindi and English, record the first half."*
- **Day 4 Task**: *"Hinglish test set, part 2: record the remaining 50, and write the manifest."*
- **Done when**: *"100 recordings plus manifest are ready for Aryan's benchmark."*

This branch delivers:

1. **`docs/test-sets/hinglish-100.json`** — The complete 100-utterance primary manifest.
   All sentences mix Hindi and English naturally. IDs are `H1-001` through `H1-100`.
   Each utterance maps to its designated audio file, exact ground-truth text, category, and length classification.

2. **`data/hinglish-test-set/manifest.json` & `manifest.jsonl`** — Dedicated benchmark manifests.
   Provides direct input for Aryan's ASR benchmarking script (`measure_asr.py`).
   Links each audio recording path directly to its reference transcript and acoustic specification.

3. **`data/hinglish-test-set/record_hinglish.py`** — Interactive CLI recording utility.
   Captures real human microphone input via `sounddevice`, computes RMS energy and duration,
   and saves 16 kHz mono PCM-16 WAV files to `data/hinglish-test-set/audio/`.
   Supports `--part {1,2,all}`, `--id <ID>`, `--start <ID>`, and `--list`.

4. **`data/hinglish-test-set/validate_hinglish.py`** — Comprehensive validator for all 100 utterances.
   Verifies manifest completeness, WAV file readability, 16kHz mono 16-bit format compliance,
   minimum duration, acoustic speech energy (RMS > 0.003 to prevent empty/muted files),
   and 1:1 ground-truth mapping.

5. **`data/hinglish-test-set/audio/`** — Directory housing the recordings (`H1-001.wav` through `H1-100.wav`).

## 2. Why the test set is needed

`docs/findings/perf-1-latency-budget.md` established that the initial ASR latency and accuracy figures
were preliminary because they relied on TTS-synthesized clips rather than authentic human speech.
Evaluating faster-whisper on real conversational Hinglish speech is essential because:

- **Acoustic variance**: Human speech includes accents, natural pauses, hesitation, varied speaking rates, and background room reflections.
- **VAD segmentation**: Silero VAD responds differently to human voice dynamics compared to flat synthetic speech.
- **Code-switching fidelity**: Hinglish transitions between Hindi syntax and English loanwords test the tokenization and language modeling capabilities of Whisper (`large-v3`, `language=hi`).
- **WER baseline**: Real ground-truth text compared against ASR transcripts provides an empirical Word Error Rate baseline for the project.

## 3. Corpus structure — the 100 utterances

All 100 utterances are scripted in **Romanized Hinglish** (Latin transliteration for Hindi terms, combined with standard English).
This ensures the speaker can read each line naturally without deciphering complex Devanagari orthography.

### Category distribution

| Category | Count | Example |
|---|---|---|
| conversational | 10 | *"Yaar, aaj traffic bahut zyada tha, office late pahuncha."* |
| technology | 14 | *"Yeh bug kab se hai, server logs mein check kiya?"* |
| work | 10 | *"Client call hai ek ghante mein, prepare ho gaye?"* |
| college | 5 | *"Assignment deadline kal hai, abhi tak complete nahi hua."* |
| money | 9 | *"Yeh phone kitne ka hai, EMI available hai kya?"* |
| scheduling | 6 | *"Meeting teen baje hai, conference room book kiya kya?"* |
| travel | 5 | *"Airport se cab book karo, flight six baje land karti hai."* |
| question | 5 | *"Samajh nahi aaya, thoda aur explain kar sakte ho?"* |
| command | 3 | *"Please presentation ka PDF share kar do abhi."* |
| food | 5 | *"Lunch mein kya order karein, pizza ya biryani?"* |
| health | 4 | *"Gym membership join karna hai, monthly fee kitni hai?"* |
| entertainment | 8 | *"Netflix par koi acchi series recommend karo please."* |
| family | 9 | *"Bhai ka birthday gift online order kiya, delivery track karo."* |
| code-switch-heavy | 7 | *"Vaani app ka beta version release ho gaya kya, testing kab shuru karein?"* |

### Length distribution

- **Short** (< 8 words): 40 utterances — commands, queries, quick status questions.
- **Medium** (8–15 words): 60 utterances — compound conversational sentences.

## 4. Recording specification

| Property | Requirement | Rationale |
|---|---|---|
| Format | WAV (PCM) | Uncompressed, standard audio container |
| Sample rate | 16,000 Hz | Native sample rate for Whisper and Vaani audio pipeline |
| Channels | 1 (mono) | Single audio channel per `contracts.md` section 2.1 |
| Bit depth | 16-bit signed PCM | Little-endian signed 16-bit integer samples |
| Audio path | `data/hinglish-test-set/audio/H1-NNN.wav` | Deterministic naming mapped to manifest IDs |
| Source | Live human speech | Zero TTS, zero synthetic audio, zero silent placeholders |

## 5. Manifest format

The test set manifest is published in both JSON and JSONL formats for interoperability with Aryan's benchmark:

### `data/hinglish-test-set/manifest.json`
```json
{
  "name": "Vaani Hinglish ASR Test Set",
  "version": "2.0.0",
  "total_utterances": 100,
  "spec": {
    "sample_rate_hz": 16000,
    "channels": 1,
    "bit_depth": 16,
    "format": "WAV"
  },
  "recordings": [
    {
      "id": "H1-001",
      "audio_file": "audio/H1-001.wav",
      "text": "Mujhe kal ka meeting schedule check karna hai.",
      "category": "conversational",
      "part": 1,
      "length": "short"
    }
  ]
}
```

### `data/hinglish-test-set/manifest.jsonl`
```jsonl
{"id": "H1-001", "audio_filepath": "data/hinglish-test-set/audio/H1-001.wav", "text": "Mujhe kal ka meeting schedule check karna hai.", "category": "conversational", "part": 1, "length": "short"}
```

## 6. Recording & validation workflow

### Recording interactive sessions
Run the recorder from repo root:
```bash
# Record all unrecorded utterances across the corpus
python3 data/hinglish-test-set/record_hinglish.py

# Or record Part 2 specifically (H1-051 to H1-100)
python3 data/hinglish-test-set/record_hinglish.py --part 2

# Or record a single utterance
python3 data/hinglish-test-set/record_hinglish.py --id H1-051
```

Controls:
- `Enter`: Start recording stream.
- `Enter` (again): Stop recording.
- `Enter` (prompt): Accept recording and advance.
- `r`: Re-record current utterance immediately.
- `s`: Skip utterance.
- `q`: Save progress and quit.

### Validation
Run the validator:
```bash
python3 data/hinglish-test-set/validate_hinglish.py
```

The validator verifies:
1. All 100 utterances exist in the manifest without duplicates.
2. All 100 WAV files exist in `data/hinglish-test-set/audio/`.
3. Audio files conform to 16 kHz mono 16-bit PCM.
4. Audio durations are non-trivial (>= 0.5 seconds).
5. Audio contains real speech energy (RMS energy >= 0.003).
6. Ground-truth text is non-empty and maps 1:1 with audio files.

## 7. Handover to Aryan's benchmark

Once all 100 recordings are present and validated, Aryan's benchmark script (`measure_asr.py`) runs:
1. Iterate over each recording in `data/hinglish-test-set/manifest.json`.
2. Feed audio into `faster-whisper` (`large-v3`, `language="hi"`).
3. Compute decode latency, realtime factor (RTF), and Word Error Rate (WER) against the ground-truth `text`.
