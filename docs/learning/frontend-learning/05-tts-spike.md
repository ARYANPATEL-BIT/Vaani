# Week 1 Friday — Live Speech Engine Spike: Piper vs Sarvam Bulbul

## In one minute

This spike compares two TTS (text-to-speech) engines to decide which one
Vaani will use for live speech synthesis. The two candidates are Piper
(local neural TTS, runs on-device) and Sarvam Bulbul (cloud-hosted REST
API, tuned for Indian languages). The comparison used Hinglish sentences
in both romanised and Devanagari script. Piper was tested successfully;
Sarvam was not testable (no API key during the spike). Based on latency,
local execution, and the repo's non-negotiable constraints, **Piper was
selected for Week 1.**

---

## Files

| File | Responsibility |
|---|---|
| `spikes/tts-hinglish/generate_piper.py` | Generates Piper audio clips locally |
| `spikes/tts-hinglish/generate_sarvam.py` | Would generate Sarvam clips (requires key) |
| `spikes/tts-hinglish/run_spike.py` | Runs both scripts in sequence |
| `spikes/tts-hinglish/VERDICT.md` | Full evidence table and decision |
| `spikes/tts-hinglish/audio/piper_romanized.wav` | Piper — romanised Hinglish clip |
| `spikes/tts-hinglish/audio/piper_devanagari.wav` | Piper — Devanagari Hinglish clip |
| `spikes/tts-hinglish/results/piper_run.json` | Piper run metadata |
| `spikes/tts-hinglish/models/hi_IN-priyamvada-medium.onnx.json` | Voice model config (committed) |

---

## How it works

### What TTS is

TTS (text-to-speech) converts a text string into an audio waveform containing
speech. A TTS engine must perform two steps internally:
1. **Phonemization**: convert the text into a sequence of phonemes (the minimal
   sound units of a language, e.g., "cat" → /k æ t/).
2. **Synthesis**: convert the phoneme sequence into audio samples — waveform
   data that a speaker or DAC can play.

Modern neural TTS engines (like Piper) train a neural network on recordings
of one voice. The network learns the mapping from phonemes to waveform. At
inference, the network runs on new text and produces audio without the original
speaker present.

### Piper

Piper is an open-source offline neural TTS engine developed by Rhasspy. It
uses an ONNX model (a portable neural network format) to run on any platform
with an ONNX runtime — no GPU, no internet.

The Python package (`piper-tts`) wraps the ONNX inference and the phonemizer.
In version 1.8.0 (the version installed here), `PiperVoice.synthesize()` is
a generator that yields `AudioChunk` objects. Each chunk contains:
- `audio_int16_bytes`: the raw 16-bit PCM audio for that chunk
- `sample_rate`, `sample_width`, `sample_channels`: WAV header metadata

To save a WAV file we collect the chunks, open a `wave.Wave_write`, set the
header, and write each chunk's raw bytes:

```python
# from spikes/tts-hinglish/generate_piper.py
chunks = list(voice.synthesize(text))

with wave_module.open(buf, "wb") as wav_file:
    wav_file.setnchannels(chunks[0].sample_channels)   # 1 — mono
    wav_file.setsampwidth(chunks[0].sample_width)       # 2 — 16-bit
    wav_file.setframerate(chunks[0].sample_rate)        # 22050 Hz
    for chunk in chunks:
        wav_file.writeframes(chunk.audio_int16_bytes)
```

The ONNX model file (`hi_IN-priyamvada-medium.onnx`, 61 MB) is downloaded
from HuggingFace once and stored locally. It is gitignored because its size
would bloat the repository.

### Sarvam Bulbul

Sarvam Bulbul is a hosted TTS API specialised for Indian languages. The call
pattern is:

```python
# from spikes/tts-hinglish/generate_sarvam.py
payload = {
    "inputs": [text],
    "target_language_code": "hi-IN",
    "speaker": "anushka",
    "model": "bulbul:v2",
    "speech_sample_rate": 16000,
}
response = urllib.request.urlopen(req)          # HTTP POST
audio_b64 = json.loads(response.read())["audios"][0]
audio_bytes = base64.b64decode(audio_b64)       # base64 → WAV bytes
```

The `audios` field in the response is a list of base64-encoded WAV strings,
one per input sentence. This was not run because no API key was available.

---

## New concepts

### ONNX (Open Neural Network Exchange)

ONNX is a file format for storing trained neural networks in a way that is
portable across frameworks. A PyTorch model can be exported to ONNX; then
the same file runs inside a C++ runtime, a Python runtime, or a browser.
Piper uses ONNX because it means the model runs on ARM macOS, Linux x86,
Raspberry Pi — without any GPU or framework-specific installation.

### Phonemization (mixed-script)

Piper's Hindi model handles both Devanagari and romanised input through the
same internal phonemizer. The phonemizer converts both `"Namaste"` and
`"नमस्ते"` to the same phoneme sequence, so the audio output is identical.
English words embedded in the sentence (`"real-time voice conversation"`)
are phonemized using English rules even when surrounded by Hindi text,
because the phonemizer detects the Latin script.

### WAV file structure (RIFF)

A WAV file is a RIFF container with a header block and a raw PCM data block.
The header specifies: number of channels, sample width (bytes per sample),
and frame rate (samples per second). Python's `wave` module requires these
three parameters to be set before any audio frames are written — otherwise
it raises "# channels not specified". In Piper 1.8.0, these values come from
the `AudioChunk` metadata rather than the model config object.

---

## Why this and not that

| Choice | Picked | Alternative | Why not the alternative |
|---|---|---|---|
| Local Piper over Sarvam | Piper | Sarvam Bulbul | Sarvam adds 500–1 500 ms network round-trip; breaks P50 < 1 000 ms target |
| `priyamvada-medium` voice | priyamvada | Other Hindi voices | First available voice; medium quality is a good balance for an evaluation |
| Python piper-tts package | pip package | Piper CLI binary | The package integrates cleanly into Python scripts; no subprocess needed |
| Collect all chunks before writing | `list(voice.synthesize(...))` | Streaming chunk-by-chunk | Simpler for a spike; streaming would need a concurrent write pattern |

---

## When things go wrong

| Failure | What the code does |
|---|---|
| `SARVAM_API_KEY` not set | `generate_sarvam.py` prints a clear error and exits with code 1 |
| Piper model `.onnx` missing | `generate_piper.py` checks the file size and exits with instructions to run `--download` |
| Piper returns 0 chunks | Raises `RuntimeError("Piper returned 0 audio chunks")` |
| HTTP error from Sarvam | `urllib.request.urlopen` raises `HTTPError`; caught and logged in `run_log` |
| Wave file write fails | Exception propagates; clip logged as `"status": "failed"` in JSON |

---

## Questions you could be asked

**Where is the code that calls Piper?**  
`spikes/tts-hinglish/generate_piper.py`, function `synthesise()`.

**Where are the audio clips?**  
`spikes/tts-hinglish/audio/` — `piper_romanized.wav` and `piper_devanagari.wav`.

**Why was Sarvam not tested?**  
No `SARVAM_API_KEY` was available during the spike session.
The script (`generate_sarvam.py`) is ready to run once a key is provided.

**What happens if Piper produces 0 audio chunks?**  
The script raises a `RuntimeError` with a descriptive message. This would
happen if the phonemizer failed to parse the input text.

**Why not just use the Piper CLI binary instead of the Python package?**  
The Python package integrates directly into the script without a subprocess.
The CLI binary would require `subprocess.run(["piper", ...])` and piping
stdin/stdout, which is more fragile in a spike script.

**Why is the Piper model gitignored?**  
At 61 MB, the ONNX binary would bloat git history and is not source code.
Developers download it on demand. The JSON config (4.9 KB) is committed
because it is needed to understand the model without downloading the binary.

**What is the latency advantage of Piper over Sarvam?**  
Piper generated a 5-second clip in 90–110 ms. Sarvam would require a
network round-trip estimated at 500–1 500 ms. On the Vaani hot path, Piper
is 5–15× faster.

**Why not score audio quality numerically?**  
MOS (Mean Opinion Score) or PESQ require multiple listeners or a reference
signal. Neither was available in this spike. Observations are from single-
listener playback and are described honestly as such.

**What would make us switch to Sarvam?**  
If Vaani's latency target is relaxed (e.g., P50 moves to 3 000 ms), or if
we measure that Sarvam's naturalness meaningfully reduces user drop-off, or
if the production backend is co-hosted with Sarvam's API region to cut
network latency below 100 ms.

**What is the meaning of 22 050 Hz vs 16 000 Hz?**  
Piper's priyamvada-medium model outputs at 22 050 Hz (standard for speech
TTS). The Vaani pipeline contracts specify 16 000 Hz (contracts.md). If
Piper audio is used on the real pipeline, it will need to be resampled. For
the spike this does not matter — the goal is to evaluate quality, not to
integrate with the pipeline.

---

## Check yourself

1. Where is the Piper audio synthesis code, and what function does it call?
2. Why was Piper selected over Sarvam given that Sarvam is purpose-built for Hinglish?
3. What would you need to do before running `generate_sarvam.py` successfully?
