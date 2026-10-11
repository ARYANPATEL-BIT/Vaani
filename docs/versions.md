# Pinned versions

The learning documents cite this file for the exact version of every library
and tool in use. Generated 2026-10-11 from `backend/uv.lock` and
`frontend/package-lock.json`: every version below is the one those lock files
pin, nothing else. Regenerate this file after any `uv lock` or `npm install`
that changes a lock file.

Licences are not in the lock files. Backend licences come from each installed
package's metadata (`License-Expression`, else `License`, else its licence
classifier); frontend licences come from the `license` field that
`package-lock.json` records for each package.

## Toolchain

| Tool | Version | Where it is pinned |
|---|---|---|
| Python | 3.11 | `backend/.python-version`; `pyproject.toml` requires `>=3.11` |
| uv | 0.11.28 | `.github/workflows/ci.yml` |
| Node.js | `^20.19.0 \|\| ^22.13.0 \|\| >=24` | Not pinned. This is what the locked vite 8.3.0 (`^20.19.0 \|\| >=22.12.0`) and eslint 10.11.0 (`^20.19.0 \|\| ^22.13.0 \|\| >=24`) both accept |
| npm | Not pinned | `package-lock.json` is lockfileVersion 3, which npm 7 and later read |

## Backend runtime dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| fastapi | 0.141.1 | MIT | Web framework: routing, validation, ASGI app |
| uvicorn (`[standard]` extra) | 0.53.0 | BSD-3-Clause | ASGI server that runs the app; the extra adds WebSocket support |
| pydantic-settings | 2.15.0 | MIT | Typed settings from TOML + environment |
| httpx | 0.28.1 | BSD-3-Clause | Async HTTP client: the LLM providers' streaming calls, and FastAPI's TestClient |
| onnxruntime | 1.30.0 | MIT | Runs the Silero VAD model on CPU |
| numpy | 2.4.6 on Python 3.11 (2.5.3 on 3.12+) | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Audio sample arrays |
| faster-whisper | 1.2.1 | MIT | Speech recognition: Whisper on CTranslate2 |
| piper-tts | 1.8.0 | GPL-3.0-or-later | Speech synthesis: Piper voices on ONNX Runtime |

## Backend optional `gpu` extra (`uv sync --extra gpu`)

Only for `asr.whisper.device = "cuda"`. CI and CPU machines never install these.

| Package | Version | License | Why it is here |
|---|---|---|---|
| nvidia-cublas-cu12 | 12.9.2.10 | LicenseRef-NVIDIA-Proprietary | GPU matrix maths for CTranslate2 |
| nvidia-cudnn-cu12 | 9.27.0.42 | LicenseRef-NVIDIA-Proprietary | GPU neural-network kernels for CTranslate2 |
| nvidia-cuda-nvrtc-cu12 | 12.9.86 | LicenseRef-NVIDIA-Proprietary | Runtime kernel compilation, needed by cuDNN |

## Backend dev/test dependencies (direct, `dev` group)

| Package | Version | License | Why it is here |
|---|---|---|---|
| pytest | 9.1.1 | MIT | Test runner |
| ruff | 0.16.8 | MIT | Linter and formatter |
| sounddevice | 0.5.6 | MIT | Microphone capture in ad-hoc recording scripts |
| soundfile | 0.14.0 | BSD-3-Clause | WAV read/write in ad-hoc scripts |
| websockets | 17.1 | BSD-3-Clause | WebSocket client in `scripts/fake_client.py` (uvicorn's `[standard]` extra also pulls it in) |

## Key backend transitive dependencies (pulled in automatically)

| Package | Version | Pulled in by |
|---|---|---|
| pydantic | 2.13.5 | fastapi, pydantic-settings |
| pydantic-core | 2.46.5 | pydantic |
| starlette | 1.6.0 | fastapi |
| anyio | 4.15.1 | starlette, httpx |
| python-dotenv | 1.2.3 | pydantic-settings |
| protobuf | 7.36.2 | onnxruntime |
| flatbuffers | 25.12.19 | onnxruntime |
| ctranslate2 | 4.8.2 | faster-whisper (the inference engine) |
| av | 18.1.0 on Python 3.11 (19.0.0 on 3.12+) | faster-whisper (audio file decoding; wheels bundle FFmpeg) |
| tokenizers | 0.23.2 | faster-whisper (Whisper's text tokenizer) |
| huggingface-hub | 1.33.0 | faster-whisper (model download) |

## Frontend runtime dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| react | 19.3.0 | MIT | Core UI library for declarative views |
| react-dom | 19.3.0 | MIT | DOM renderer for React |
| react-router-dom | 7.18.4 | MIT | Client-side routing |
| lucide-react | 1.52.0 | ISC | Icons |

## Frontend dev dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| vite | 8.3.0 | MIT | Frontend build tool and dev server |
| @vitejs/plugin-react | 6.1.1 | MIT | React Fast Refresh and JSX support |
| eslint | 10.11.0 | MIT | JavaScript linter |
| @eslint/js | 10.0.1 | MIT | ESLint's recommended rule set |
| globals | 17.12.0 | MIT | Global identifier definitions for ESLint |
| eslint-plugin-react-hooks | 7.1.1 | MIT | Enforces the Rules of Hooks |
| eslint-plugin-react-refresh | 0.5.7 | MIT | Validates components for Fast Refresh |
| @types/react | 19.3.0 | MIT | React type definitions, for the editor |
| @types/react-dom | 19.3.0 | MIT | React DOM type definitions, for the editor |

## Model files

Not in either lock file. Pinned in `backend/config.toml` where a pin exists.

| Model | Pinned by | License | Notes |
|---|---|---|---|
| Silero VAD (`backend/models/silero_vad.onnx`) | Committed file; sha256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3` in `[vad]` | MIT | github.com/snakers4/silero-vad tag v6.2.3 |
| Piper voices: `hi_IN-priyamvada-medium`, `hi_IN-pratham-medium`, `en_US-kristin-medium`, `en_US-norman-medium` | `[tts.piper] voices_url` (piper-voices revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`) and a sha256 per voice in `[tts.piper.voices]` | Dataset licence per voice: see the comment above `[tts.piper.voices]` in `config.toml` | `.onnx` fetched by `scripts/fetch_models.py`; `.onnx.json` committed |
| Whisper `small` (committed default), CTranslate2 conversion | **Not pinned.** `config.toml` names only `model = "small"`; faster-whisper downloads it from Hugging Face on first use | MIT | Whichever revision Hugging Face serves at download time |

Two licences need a note: the NVIDIA libraries are proprietary (free to
redistribute under NVIDIA's EULA, not open source), and the `av` wheels bundle
FFmpeg, which is LGPL. piper-tts is GPL-3.0-or-later, a copyleft licence. None
of these has been checked for our distribution case.
