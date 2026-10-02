# Pinned versions

The learning documents cite this file for the exact version of every library
and tool in use. These are the versions resolved into `backend/uv.lock` on
2026-09-22. Regenerate this list after any `uv lock`.

## Toolchain

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11 | Minimum `>=3.11`; local interpreter 3.11.9 |
| uv | 0.11.28 | Package manager; pinned identically in CI |
| Node.js | 18+ | Minimum `>=18`; local runtime v25.8.1 |
| npm | 10+ | Package manager; local version 11.11.0 |

## Backend runtime dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| fastapi | 0.141.1 | MIT | Web framework: routing, validation, ASGI app |
| uvicorn | 0.53.0 | BSD-3-Clause | ASGI server that runs the app |
| pydantic-settings | 2.15.0 | MIT | Typed settings from TOML + environment |
| onnxruntime | 1.30.0 | MIT | Runs the Silero VAD model on CPU (added 2026-09-27) |
| numpy | 2.4.6 | BSD-3-Clause | Audio sample arrays for VAD (added 2026-09-27) |
| faster-whisper | 1.2.1 | MIT | Speech recognition: Whisper on CTranslate2 (added 2026-10-02) |

## Backend optional `gpu` extra (`uv sync --extra gpu`, added 2026-10-02)

Only for `asr.whisper.device = "cuda"`. CI and CPU machines never install these.

| Package | Version | License | Why it is here |
|---|---|---|---|
| nvidia-cublas-cu12 | 12.9.2.10 | NVIDIA proprietary (redistributable EULA) | GPU matrix maths for CTranslate2 |
| nvidia-cudnn-cu12 | 9.27.0.42 | NVIDIA proprietary (redistributable EULA) | GPU neural-network kernels for CTranslate2 |
| nvidia-cuda-nvrtc-cu12 | 12.9.86 | NVIDIA proprietary (redistributable EULA) | Runtime kernel compilation, needed by cuDNN |

## Model files

| Model | Version | License | Source / sha256 |
|---|---|---|---|
| Whisper small, CTranslate2 conversion (committed default) | HF `Systran/faster-whisper-small`, revision `536b0662742c02347bc0e980a01041f333bce120` | MIT | Downloaded on first use into the Hugging Face cache, not committed. The revision is what was downloaded, NOT pinned in config |
| Whisper large-v3, CTranslate2 conversion (GPU override) | HF `Systran/faster-whisper-large-v3`, revision `edaa852ec7e145841d8ffdb056a99866b5f0a478` | MIT | As above |
| Silero VAD (`backend/models/silero_vad.onnx`) | v6.2.3 | MIT | github.com/snakers4/silero-vad tag v6.2.3, `src/silero_vad/data/silero_vad.onnx`; sha256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3` |

## Frontend runtime dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| react | 19.2.8 | MIT | Core UI library for declarative views |
| react-dom | 19.2.8 | MIT | DOM renderer for React |
| react-router-dom | 7.18.4 | MIT | Declarative client-side routing |

## Backend dev/test dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| pytest | 9.1.1 | MIT | Test runner |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client; powers FastAPI's TestClient |
| ruff | 0.16.8 | MIT | Linter and formatter |
| sounddevice | 0.5.6 | MIT | Microphone capture in ad-hoc recording scripts (added 2026-10-02) |
| soundfile | 0.14.0 | BSD-3-Clause | WAV read/write in ad-hoc scripts (added 2026-10-02) |

## Frontend dev dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| vite | 8.3.0 | MIT | Frontend build tool and dev server |
| @vitejs/plugin-react | 6.1.1 | MIT | React Fast Refresh and JSX support |
| eslint | 10.10.0 | MIT | JavaScript linter |
| globals | 17.12.0 | MIT | Global identifier definitions for ESLint |
| eslint-plugin-react-hooks | 7.1.1 | MIT | Enforces Rules of Hooks |
| eslint-plugin-react-refresh | 0.5.6 | MIT | Validates components for Fast Refresh |

## Key transitive dependencies (pulled in automatically)

| Package | Version | Pulled in by |
|---|---|---|
| pydantic | 2.13.5 | fastapi, pydantic-settings |
| pydantic-core | 2.46.5 | pydantic |
| starlette | 1.6.0 | fastapi |
| anyio | 4.15.1 | starlette, httpx |
| python-dotenv | 1.2.3 | pydantic-settings |
| protobuf | 7.36.2 | onnxruntime |
| flatbuffers | 25.12.19 | onnxruntime |
| ctranslate2 | 4.8.2 | faster-whisper (the inference engine; MIT) |
| av | 18.1.0 | faster-whisper (audio file decoding; BSD-3, wheels bundle FFmpeg) |
| tokenizers | 0.23.2 | faster-whisper (Whisper's text tokenizer) |
| huggingface-hub | 1.33.0 | faster-whisper (model download) |

Licenses above are the well-known licenses for these projects. Two need a
note: the NVIDIA libraries are proprietary (free to redistribute under
NVIDIA's EULA, not open source), and the `av` wheels bundle FFmpeg, which is
LGPL; this has not been checked for our distribution case. Verify against each
package's own metadata if a license question becomes important.
