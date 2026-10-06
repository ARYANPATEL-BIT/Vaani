# 08 — Hinglish Test Set

## 1. What we built in this branch

Branch: `feat/hinglish-test-set-1`

This branch creates the first structured evaluation input corpus for Vaani's
speech pipeline: `docs/test-sets/hinglish-part-1.json`. It contains 14 human
speech test cases designed to be recorded by a speaker and fed into the
faster-whisper ASR pipeline to produce the real p50/p95 latency and accuracy
numbers that `docs/findings/perf-1-latency-budget.md` explicitly calls for
("Aryan's 10 Hinglish recordings"). Before this branch, no test corpus existed:
latency measurements used TTS-synthesised clips and one committed WAV fixture
(`backend/tests/fixtures/speech_16k_mono.wav`). The test set makes it possible
to benchmark ASR on natural, conversational Hinglish speech — the actual user
input the system must handle — for the first time.

No React components, no hooks, and no backend code were modified.

## 2. What we used to build it

**Hinglish** — Hindi and English mixed in the same sentence. Spoken by hundreds
of millions of people in urban India. It switches language mid-sentence at the
word, phrase, and clause level. Because Vaani's target user speaks Hinglish, the
ASR engine must handle it.

**Code-switching** — Changing language within one utterance. In Hinglish this
produces mixed-script text: Devanagari for Hindi words, Latin script for English
words. `large-v3` with `language="hi"` was shown to produce this in
`docs/spikes/asr-hinglish.md`. `small` does not.

**`docs/spikes/asr-hinglish.md`** — The project's existing experimental record
for Hinglish ASR. It ran faster-whisper against two human-voice clips and
established which model, device, and language setting work. Used here as the
primary source of ground-truth sentences, known failure modes, and the baseline
expected output format.

**`docs/findings/perf-1-latency-budget.md`** — The project's latency analysis.
It explicitly states the real ASR measurement is "preliminary" and "waits on
Aryan's 10 Hinglish recordings". This branch defines those recordings.

**JSON** — Chosen for the test-set format because it is machine-readable (a
future script can iterate over the cases and run them through the ASR pipeline
automatically), schema-validatable, and easy to read by hand. No test runner
currently reads this file; it is input data, not executable code.

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| Test set format | JSON at `docs/test-sets/hinglish-part-1.json` | Markdown table in a `.md` file | Markdown cannot be iterated by a script without parsing. When the measurement script is written (Day 4+), it will read the JSON directly. | Human-only readability; markdown is slightly easier to read without a viewer |
| Test case count | 14 cases | 10 (as mentioned in perf-1), 20+ | perf-1-latency-budget.md mentions "10 Hinglish recordings" but does not define what they cover. 14 gives full category coverage (6 categories) without padding. More than 20 would take too long to record in a single session. | Matching the exact number cited in the latency finding |
| Location | `docs/test-sets/` (new directory) | `backend/tests/fixtures/` | Fixtures holds WAV audio files, not text input corpora. A separate directory separates concerns: fixtures = audio blobs; test-sets = input sentences | No existing precedent for text-based corpora |
| `expected_script` field | Anticipated behaviour from spike, clearly labelled not measured | Omit the field; add only after measurement | Without guidance, the person recording will not know what to look for or how to judge the output | The risk that an incorrect anticipation is read as a claim |
| Sentences: spike reuse | Two sentences from spike (H1-HM-01, H1-HM-03) included verbatim | All-new sentences | Spike sentences have a known reference output, making comparison between human voice and TTS clips possible. | Slightly less diversity in the sentence set |
| Frontend code changes | None | Add a test-set loader component to the React UI | Day 3 is explicitly about the corpus only. Adding UI without a use case is premature. The first user of this data is the measurement script, not the browser. | No interactive test runner in the frontend yet |

## 4. Where things live

| What | File | Function or class |
|---|---|---|
| Test case corpus | `docs/test-sets/hinglish-part-1.json` | `cases[]` array, 14 items |
| Recording format spec | `docs/test-sets/hinglish-part-1.json` | `meta.recording_spec` |
| Category list | `docs/test-sets/hinglish-part-1.json` | `meta.categories` |
| ASR spike (source of ground truth) | `docs/spikes/asr-hinglish.md` | Sections 3.2 and 4 |
| Latency budget (motivation) | `docs/findings/perf-1-latency-budget.md` | "What would change these numbers" |
| Existing WAV fixture (backend) | `backend/tests/fixtures/speech_16k_mono.wav` | English-only, 5.5 s |
| ASR config (language, model, prompt) | `backend/config.toml` | `[asr]`, `[asr.whisper]` |
| Frontend | none | No frontend files changed |
| Backend | none | No backend files changed |

## 5. How it works

The test set is input data. Its lifecycle is:

```
[Human speaker reads a case from the JSON]
         |
         v
[Recorded as 16 kHz mono WAV at quiet indoor conditions]
         |
         v
[WAV fed into scripts/measure_asr.py (backend, not yet written for this set)]
         |
         v
[faster-whisper transcribes: large-v3, language=hi, vad_filter=True, temperature=[0.0]]
         |
         v
[Actual transcript text + decode time recorded, compared against expected_script]
```

The JSON structure per case is:

```json
{
  "id": "H1-LM-01",
  "category": "light-mix",
  "label": "Light mix — English noun embedded in Hindi sentence",
  "text": "मुझे कल एक meeting attend करनी है।",
  "romanized": "Mujhe kal ek meeting attend karni hai.",
  "language_mix": "mixed",
  "duration_budget_s": 3,
  "expected_script": "Devanagari for Hindi words; Latin for meeting and attend",
  "what_it_checks": "...",
  "notes": "..."
}
```

- **`text`** — The sentence as it would appear in Devanagari or mixed script.
  This is the source for the recording, not the expected ASR output.
- **`romanized`** — A reading guide for the speaker. `null` for English-only
  cases where no transliteration is needed.
- **`expected_script`** — What the spike and ASR config predict the model will
  produce. This is an anticipation, not a measured result. The label in
  `meta.notes[0]` says so explicitly.
- **`duration_budget_s`** — Recording target. A 3 s budget means: say the
  sentence naturally, do not rush, but also do not add a 10-second preamble.

### Categories and why each matters

| Category | Cases | What it covers |
|---|---|---|
| `pure-hindi` | H1-PH-01, H1-PH-02 | Baseline: does Devanagari come out right with no English mixed in? |
| `pure-english` | H1-PE-01, H1-PE-02 | Regression guard: does forcing `language=hi` break English-only speakers? |
| `light-mix` | H1-LM-01, H1-LM-02, H1-LM-03 | Most common Hinglish pattern: Hindi sentence, 1–2 English words |
| `heavy-mix` | H1-HM-01, H1-HM-02, H1-HM-03 | Dense switching; sentence-level alternation |
| `numbers-dates` | H1-ND-01, H1-ND-02 | How numbers, dates, and currency are rendered |
| `question` | H1-QU-01, H1-QU-02 | Short and mid-length question forms; boundary code-switching |

Two cases are exact sentences from the spike or Day 11 measurement:

- **H1-HM-01** — Spike sample B sentence ("जितना ज़्यादा clear करोगे…"). The
  spike produced a known reference output on a TTS clip. A human recording of
  the same sentence lets us compare and see how much real voice differs from TTS
  input.
- **H1-HM-03** — The Piper TTS sentence used in the Day 11 end-to-end run,
  which produced a 1,188 ms ASR decode time. A human recording of the same
  sentence will show whether that 1,188 ms was driven by clip length or by
  something specific to TTS audio.

## 6. When things go wrong

| What fails | What the code does | What the evaluator sees |
|---|---|---|
| Speaker does not follow the recording spec (wrong sample rate, stereo) | The WAV is fed to faster-whisper, which silently resamples via `av`; results may be noisier | Unexpected transcription errors or hallucinations |
| Speaker pauses mid-sentence (long gap) | VAD may end the utterance early and produce two transcripts instead of one | Case H1-QU-01 is the highest risk; noted in its `notes` field |
| The model writes the English words in Devanagari | Script output does not match `expected_script` | Record the actual output; this is data, not failure |
| `small` model is used instead of `large-v3` | Most Hinglish cases produce garbage output (spike section 3.2 shows this) | Everything in the heavy-mix category is unreadable |
| `language` is not set to `"hi"` | Auto-detect produces `ur`, `la`, or `hi` randomly across runs (spike section 3.1) | Results are not reproducible |

## 7. New terms

**Word error rate (WER)** — The fraction of words in a transcript that are
wrong (substituted, deleted, or inserted), compared against a reference
transcript. Formula: `(S + D + I) / N` where S = substitutions, D = deletions,
I = insertions, N = words in reference. We do not measure WER in Part 1 because
we have no reference transcripts yet — the test set is the input, not the
evaluation harness. `docs/spikes/asr-hinglish.md` section 3.4 notes that the
"~25–28%" WER figure from the spike is an eyeball estimate, not a measurement.

**Evaluation corpus** — A set of known inputs used to measure a system's
behaviour. Different from a unit test: a unit test asserts a specific output;
an evaluation corpus records what the system actually produces so you can compare
it over time and across configurations. This test set is an evaluation corpus.

**TTS clip vs human voice** — Text-to-speech clips (like the Piper WAVs in
`spikes/tts-hinglish/audio/`) have clean, consistent prosody and no hesitation.
Human voice has natural variation: filler sounds, micro-pauses, accent drift,
and inconsistent emphasis. ASR engines trained on real speech usually perform
better on human voice than on certain TTS outputs, but this varies by engine.
The project's ASR latency numbers were measured on TTS clips; this test set
provides human-voice recordings to check whether those numbers hold in practice.

**`initial_prompt`** — A short text string passed to faster-whisper before
decoding. Whisper's decoder starts from this text, which biases the tokeniser
toward the vocabulary and script in the prompt. The committed prompt is
`"mujhe kal subah ek meeting hai, toh please mujhe 8 baje remind kar dena"`
(all romanised Hinglish), which nudges the model to use Devanagari for Hindi
and Latin for English in its output. Changing this prompt changes transcription
quality. See `docs/spikes/asr-hinglish.md` section 3.2.

## 8. Questions you could be asked

1. **Where is the test set data?**
   `docs/test-sets/hinglish-part-1.json`. It is a JSON array of 14 cases under
   the `cases` key.

2. **Why 14 cases when perf-1-latency-budget.md says 10 recordings?**
   The latency budget document mentions "10 Hinglish recordings" informally, without
   defining their categories. 14 cases give full coverage of all 6 categories.
   When recording time is limited, the recorder may prioritise the 3 heavy-mix and
   3 light-mix cases; the 2 pure-english cases are regression guards and the
   2 question cases are lower priority.

3. **What happens if the actual ASR output does not match `expected_script`?**
   The result is recorded as-is. `expected_script` is an anticipation from the
   spike, not a pass/fail criterion. Deviations are data: they tell us where the
   model struggles.

4. **Why not add a React component that loads and displays the test set?**
   There is no use case yet. The first consumer of this data is a backend
   measurement script. Adding frontend UI before there is a use case is the
   kind of premature abstraction CLAUDE.md explicitly forbids.

5. **What is the difference between H1-HM-01 and H1-HM-03?**
   H1-HM-01 is the exact sentence from the ASR spike sample B — used to compare
   human voice against the spike's TTS-clip reference output. H1-HM-03 is the
   Piper TTS sentence from the Day 11 end-to-end measurement run — included to
   compare human-voice ASR latency against the 1,188 ms TTS-clip result.

6. **What is code-switching and why does it matter for ASR?**
   Code-switching is changing language mid-sentence. In Hinglish this means
   Devanagari and Latin script appear in the same transcript. Most ASR engines
   either collapse all output to one script or produce garbled mixed output. The
   spike showed `large-v3` with `language=hi` handles this correctly for whole
   utterances. The test set verifies that this holds across different mixing
   densities and sentence lengths.

7. **Did we modify any frontend or backend code?**
   No. Only two new files were created: `docs/test-sets/hinglish-part-1.json`
   and this learning document.

8. **What would be done differently in Part 2?**
   Part 2 should cover: longer utterances (8–15 s), multi-speaker variation
   (more than one human recording the same sentence), actual WER measurement
   against reference transcripts, and cases with background noise. Part 1 stays
   within short-to-medium utterances with one speaker.

## 9. Check yourself

1. What does `expected_script` mean in each test case, and what does it NOT mean?
2. Why do pure-English cases appear in a Hinglish test set?
3. Which two cases are reused from existing project data, and what additional
   information does a human recording of those cases provide?
