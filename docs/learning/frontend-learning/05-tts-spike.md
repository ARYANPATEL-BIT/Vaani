# Week 1 Friday — Live Speech Engine Spike: Piper & TTS Provider Architecture

## In one minute

This spike establishes the live speech synthesis (TTS) engine for Vaani.
We selected and implemented **Piper** (an open-source local neural TTS engine running
on-device via ONNX) as our primary live engine. Piper was verified using Hinglish sentences
in both Romanised and Devanagari script.

To ensure future extensibility without vendor lock-in, the codebase implements a
**provider/adapter pattern** (`spikes/tts-hinglish/providers/`):
- `TTSProvider` base contract and domain errors.
- `PiperTTSProvider`: Active, offline implementation (requires zero API keys, generates audio in ~100 ms).
- `SarvamTTSProvider`: Future adapter boundary stub for Sarvam Bulbul (no network calls made in Day 5; will be integrated later without rewriting Piper).

---

## Files

| File | Responsibility |
|---|---|
| `spikes/tts-hinglish/providers/base.py` | Abstract `TTSProvider` contract, `TTSResult`, and error types |
| `spikes/tts-hinglish/providers/piper.py` | Active Piper TTS provider implementation using local ONNX |
| `spikes/tts-hinglish/providers/sarvam.py` | Future Sarvam Bulbul adapter boundary (stubbed, no network calls) |
| `spikes/tts-hinglish/providers/__init__.py` | Provider factory (`get_tts_provider`) defaulting to Piper |
| `spikes/tts-hinglish/generate_piper.py` | Generates Piper audio clips locally via provider |
| `spikes/tts-hinglish/test_providers.py` | Unit tests for provider decoupling and boundary checks |
| `spikes/tts-hinglish/run_spike.py` | Master runner verifying generation and audio properties |
| `spikes/tts-hinglish/VERDICT.md` | Decision record, listening observations, and benchmark results |
| `spikes/tts-hinglish/audio/piper_romanized.wav` | Piper — romanised Hinglish clip (222.8 KB, 5.05 s) |
| `spikes/tts-hinglish/audio/piper_devanagari.wav` | Piper — Devanagari Hinglish clip (215.1 KB, 4.88 s) |
| `spikes/tts-hinglish/results/piper_run.json` | Piper run metadata |
| `spikes/tts-hinglish/models/hi_IN-priyamvada-medium.onnx.json` | Voice model config (committed) |

---

## How it works

### What TTS is

TTS (text-to-speech) converts a text string into an audio waveform containing
speech. A TTS engine must perform two steps internally:
1. **Phonemization**: convert the text into a sequence of phonemes (minimal sound units, e.g., "cat" → /k æ t/).
2. **Synthesis**: convert the phoneme sequence into audio samples — waveform data that a speaker can play.

### The Provider / Adapter Pattern

Similar to how LLMs are decoupled in `vaani.providers.base`, live speech TTS uses a clean interface:

```python
class TTSProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def synthesize(self, text: str) -> TTSResult: ...

    @abstractmethod
    def is_available(self) -> bool: ...
```

Callers interact with `get_tts_provider("piper")` and receive a `TTSResult`. When Sarvam Bulbul is integrated in a future phase, it implements `TTSProvider` in `providers/sarvam.py` with zero changes to caller code or Piper logic.

### Piper Implementation

Piper runs an ONNX neural model on CPU:
- Uses `hi_IN-priyamvada-medium.onnx` (61 MB, gitignored).
- `PiperVoice.synthesize()` produces `AudioChunk` objects with 16-bit PCM audio.
- Chunks are assembled into standard RIFF WAV format (22,050 Hz, 16-bit mono).
- Generation latency is ~90–110 ms locally on Apple Silicon.

### Future Sarvam Bulbul Adapter

Sarvam Bulbul is a planned cloud TTS provider tuned for Indian languages. In Day 5:
- It is represented by `SarvamTTSProvider` as an architectural boundary.
- **Zero network requests** are executed.
- No API keys are required or collected.
- Unconfigured execution cleanly raises `AuthenticationError` without touching external endpoints.

---

## New concepts

### ONNX (Open Neural Network Exchange)

ONNX is an open format for machine learning models. A model trained in PyTorch or TensorFlow is exported to ONNX and runs across macOS, Linux, and Windows without framework overhead or GPU requirements.

### Mixed-Script Phonemization

Piper's Hindi voice model processes both Devanagari and Latin/Romanised text through the same phonetic representation:
- "Namaste" and "नमस्ते" map to equivalent phonetic tokens.
- Embedded English terms ("real-time voice conversation") are detected and phonemized using Latin rules, producing natural code-switching.

### WAV (RIFF) Header Specification

RIFF WAV files contain:
- Audio format code (1 = PCM)
- Channel count (1 = mono, 2 = stereo)
- Sample rate (22,050 Hz for Piper)
- Byte rate and block align
- Bits per sample (16-bit)
Python's `wave` module constructs this header before audio data frames are written.

---

## Why this and not that

| Choice | Picked | Alternative | Why not the alternative |
|---|---|---|---|
| Local Piper over Sarvam | Piper | Sarvam Bulbul | Sarvam adds 500–1,500 ms network round-trip; breaks P50 < 1,000 ms target |
| Provider / Adapter pattern | `TTSProvider` abstraction | Hardcoded engine calls | Hardcoding would force rewrites when adding cloud providers |
| `priyamvada-medium` voice | priyamvada | Other voices | Good balance of naturalness and inference speed (61 MB) |
| Python package | `piper-tts` | Piper CLI binary | Direct memory buffers; no subprocess pipes |

---

## When things go wrong

| Failure | What the code does |
|---|---|
| Piper model `.onnx` missing | Raises `ModelNotFoundError` with download instructions |
| Piper returns 0 chunks | Raises `SynthesisError` ("failed to phonemize input") |
| Sarvam called without key | Raises `AuthenticationError` without executing network requests |
| Wave file corrupted | `wave.open` in verification step flags truncated frames |

---

## Questions you could be asked

**1. Where is the active TTS provider implemented?**  
`spikes/tts-hinglish/providers/piper.py` (`PiperTTSProvider`).

**2. How do you swap or extend TTS providers in the future?**  
Implement `TTSProvider` from `providers/base.py`, register it in `providers/__init__.py` under `get_tts_provider()`.

**3. Does the current Piper implementation require any API key?**  
No. Piper runs 100% locally on CPU/ONNX with zero internet access and zero credentials.

**4. Was the Sarvam API called during Day 5?**  
No. Sarvam is modeled as a future provider boundary stub. No network calls were made and no keys were required.

**5. How fast is Piper generation?**  
~90–110 ms for a 5-second Hinglish sentence on Apple Silicon, well within Vaani's latency budget.

**6. How does Piper handle code-switched Hinglish?**  
The phonemizer detects Latin characters inside Hindi sentences and applies phonetic mappings smoothly without pauses or distortions.
