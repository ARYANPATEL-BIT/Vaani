# Spike: speech recognition for Hinglish

Date: 2026-10-02. Engine: faster-whisper 1.2.1 on CTranslate2 4.8.2.
Aryan's original spike (samples A and B), plus two follow-up checks run
during day 10 (sections 4 and 4b).

## 1. The question

Can faster-whisper transcribe **Hinglish**, meaning Hindi and English mixed
inside one sentence, well enough to feed a language model? Which model size,
device and language setting should we use?

## 2. Decisions this spike produced

| Decision | Evidence |
|---|---|
| `small` is unusable for Hinglish, on CPU and GPU alike | Sample B, rows 1–2: near-garbage Devanagari |
| `large-v3` transcribes Hinglish correctly and code-switches (Devanagari for Hindi words, Latin for English words) | Sample B, "forced hi" rows |
| Automatic language detection is not used | Same speaker detected as `la`, `hi` and `ur` across runs |
| `language="en"` is rejected | Sample B "forced en": it **translates**, so the original words are lost |
| `language="hi"` plus a romanized `initial_prompt` is the setting | Sample B "forced hi + roman hint"; section 4 shows it does not break clean English |
| `vad_filter` is always on | 5 s of digital silence took 13 s to decode with it off (section 3.3) |
| `temperature=[0.0]` (single decode) | Section 4: one clip took 62.5 s via (probable) temperature fallback |
| Partials off by default | Section 4b: on cut-off audio, forced `hi` writes English in Devanagari and loops |

## 3. Original spike (Aryan)

### 3.1 Sample A — clean English, human voice, 15 s

| Config | Time | Detected | Transcript |
|---|---|---|---|
| cpu/small | 2856 ms | en | "Hi everyone, how's it going? I hope everything's all great. This GPU and stuff works, and I want this modus to look like a GPU instead of CPUs." |
| cuda/small | 882 ms | en | (near-identical text) |
| cuda/large-v3 | 1192 ms | **la** | "Hi everyone, how's it going?  I hope everything's alright.  This GPU and stuff works.  And I want this modus to work on GPU instead of CPUs." |

`la` is Latin. The detector picked a language nobody spoke. The text was still right,
because both languages use Latin script.

### 3.2 Sample B — Hinglish, human voice, 15 s

**Auto-detect, three model/device combinations:**

| Config | Time | Detected | Transcript |
|---|---|---|---|
| cpu/small | 65531 ms | hi | "जितना जादा क्लीर कोगों नोस में शाध हुए क्माजा लगे से रथ लगे से ये सभार रफ पनमयउप्रिए लगा  minerals । बार्त्लक ठी । फारिंए लुँवन लगे से जादा जिल से प् слуш खोलगा" |
| cuda/small | 4810 ms | hi | "जितना जादा क्लीर कोगी नहीं जादा जीसे ही आज़्ी साँ लिस्पोंड पोड़़ा  बोगट लेख्ट सी एक इस्वालिंगना शाइच लोव पहले से जादा जीसे पीर पोड़़ा  तो शेवब बैटर इस्पोंड पोड़़ा" |
| cuda/large-v3 | 2284 ms | **ur** | "جتنا زیادہ کلیر پولیں گے اس میں شاید اتنا زیادہ اچھے سے ایسا ریسپونٹ کرے گا ..." |

The cpu/small row is not Hindi. It even contains a Cyrillic word (`слуш`) and a
stray English one ("minerals"). The 65 s decode time is the same runaway pattern
that section 4 found.

**Language forcing, cuda/large-v3 only:**

| Setting | Time | Detected | Transcript |
|---|---|---|---|
| auto, no prompt | 2781 ms | ur | (Urdu script, content correct) |
| forced `hi` | 3358 ms | hi | "जितना जादा clear कोई है उसमें शायद उत्पाद जादा अच्छे से ASI respond कोईगा  बट let's see कि इस वाले मुझे शायद लोगा पहले से जादा अच्छे से clear कोईगा  तो शेयर बेटर respond कोईगा" |
| forced `en` | 1054 ms | en | **Translation, not transcription:** "The more clear it is, the better the ASI response will be. But let's see if the ASI response will be as clear as before. Then it will be a better response." |
| forced `hi` + roman hint | 3047 ms | hi | "जितना ज्यादा clear कोईंगे उसमें शायद इतना ज्यादा अच्छे से ASI respond कोईगा  बट let's see कि इस वाले में उन्होंना शायद लोगा पहले से ज्यादा अच्छे से clear कोईगा  तो शेयर बेटर respond कोईगा" |
| auto + roman hint | 1893 ms | ur | (Urdu script, English words in Latin) |

What the hint changed: "जादा" became "ज्यादा" and "कोई है" became "कोईंगे".
The output is closer to standard spelling but still not perfect. English words
("clear", "respond", "let's see") stay in Latin script in every forced-`hi`
row. That is the code-switching we want.

### 3.3 5 s of digital silence, `vad_filter` off

| Config | Time |
|---|---|
| cuda/small | 13047 ms |
| cuda/large-v3 | 870 ms |

Whisper invents words when given silence (a "hallucination") and keeps
decoding them. `small` looped far longer than `large-v3`. Measurement artifact,
but it is the reason `vad_filter` is never turned off.

### 3.4 Word error rate

No ground-truth transcript was written down for sample B. **No measured word
error rate exists.** The "roughly 25–28%" figure is an **eyeball estimate** by
Aryan, against a 20% target. It must not be quoted as a measurement.

## 4. Follow-up: does forcing `language="hi"` mangle clean English?

Our personas must serve English-only speakers too. If forcing Hindi broke clean
English, we would need per-utterance language routing instead of one config
value.

**Setup:** clips were the committed test fixture `backend/tests/fixtures/speech_16k_mono.wav`
(a human voice, 5.5 s) plus three sentences generated with Windows text-to-speech
(the default Windows voice, 16 kHz mono). Every run used `task="transcribe"`,
`vad_filter=True`, `beam_size=5`, and faster-whisper's default temperature schedule.
The "roman hint" in this run was a placeholder prompt, not the final committed one.

| Config | Clip | `en` | `hi`, no prompt | `hi` + roman hint |
|---|---|---|---|---|
| cuda/large-v3 (float16) | fixture (human) | ✅ 1696 ms* | ✅ 526 ms | ✅ 548 ms |
| cuda/large-v3 | 3 TTS clips | ✅ 539–568 ms | ✅ 529–565 ms | ✅ 541–566 ms |
| cpu/small (int8) | fixture (human) | ✅ 2766 ms* | ❌ **62561 ms**, garbage | ✅ 2525 ms |
| cpu/small | 3 TTS clips | ✅ 1666–1996 ms | ✅ 1734–1867 ms | ✅ 1747–1867 ms |

\* First call on a freshly loaded model, so it includes warm-up.

The fixture's expected text is "Hello, this is a short test of voice activity
detection for the Vaani project." What came out:

- cuda/large-v3, `hi`, no prompt: "Hello, this is a short test of voice activity detection for the Vani project."
- cpu/small, `hi`, no prompt: "invite worship the quality that you are this I will be I will be in contact you 8 that they are this they are also this 10 but I know you are a very"
- cpu/small, `hi` + hint: "Hello, this is a short test of voice activity detection for the Vaani project."
- cuda/large-v3, `hi`, TTS clip 1: "Can you book me a table for 2 at 8 tonight, somewhere near the station?" (`en` wrote "two" and "eight")

**Conclusion:** on `large-v3`, forcing `hi` leaves clean English intact, so the
design stays one config value. On `small`, the prompt is load-bearing: without
it, one human English clip became garbage and took 62.5 s. We have not verified
the cause. The likely cause is faster-whisper's temperature fallback, which
re-decodes the audio up to five more times at higher temperatures when the
output looks bad. We therefore set `temperature=[0.0]` (one decode) and a
hard inference timeout.

## 4b. Follow-up: forced `hi` on English cut off mid-word (partials)

A partial transcript is a re-decode of the utterance *so far*, so its audio
usually ends mid-word. We ran this on day 10 with the shipped prompt, cuda/large-v3
and `temperature=[0.0]`. The clip was TTS clip 2 ("The quarterly report is due on Friday, so
please send me your numbers by Wednesday afternoon"), cut to the first N
seconds. Each prefix was decoded twice; both runs gave identical text.

| Prefix | Time | Transcript |
|---|---|---|
| 1.0 s | 1429 ms | "कि द क्वार्टरली रूप" |
| 2.0 s | 1785 ms | "कि द क्वार्टरली रिपोर्ट इस डू ऑन फ्रॉम्स कर दो कर दो कर दो कर दो कर दो कर दो कर दो" |
| 2.5 s | 415 ms | "The quarterly report is due on Friday" |
| 3.5 s | 1840 ms | "कि विकॉर्टर ली रिपोर्ट इस डू ऑन फ्राइड़ ए सो प्लीज से कर दो कर दो कर दो कर दो कर दो कर दो" |
| 5.5 s (full) | 582 ms | "the quarterly report is due on friday, so please send me your numbers by wednesday afternoon" |

On cut-off audio, forcing `hi` makes Whisper **write English words in
Devanagari** and **fall into a repetition loop** ("कर दो कर दो …"). The loop
is also why those decodes take about 3× longer than the full clip. Section 4's conclusion
holds for whole utterances only. Consequences:

- partials can disagree with the final in script, not just in words;
- partials are off by default (`partial_interval_ms = 0`). The cost numbers are in
  `docs/learning/backend-learning/10-asr.md`;
- a final whose audio was cut off by the 30 s cap (`max_utterance_ms`) could
  hit the same loop. The 5 s hard timeout bounds the wait. Nothing yet
  bounds the loop itself. Whisper's `no_repeat_ngram_size` or a
  `max_new_tokens` cap are the untested candidates.

## 5. Limitations

**One human voice and three Windows TTS clips is thin.** The TTS clips are
the easiest possible English: no accent, no noise, perfect diction. Before this
result is relied on, 3–5 real English utterances from a speaker who does not
speak Hindi should be run through `large-v3` with `language="hi"`.

Also:

- Samples A and B are one speaker each, 15 s each, one recording session.
- No word error rate was measured for anything (section 3.4).
- Timings are single runs, not percentiles. Day-10's `scripts/measure_asr.py`
  produces p50/p95.
- The roman hint used in section 4 is not the shipped prompt. The shipped
  prompt is "mujhe kal subah ek meeting hai, toh please mujhe 8 baje remind
  kar dena".
- GPU timings come from Aryan's machine (one NVIDIA GPU). They are not a
  property of the model.
- Section 4b is one TTS clip cut at five lengths. It shows that the failure
  exists. It does not show how often it happens.
