# Pinned versions

The learning documents cite this file for the exact version of every library
and tool in use. Generated 2026-10-11 from `backend/uv.lock` and
`frontend/package-lock.json`: every version below is the one those lock files
pin, nothing else (the tzdata row was added on 2026-10-14, and the google-auth,
requests and their transitive rows on 2026-11-16, from the same
`backend/uv.lock`). Regenerate this file after any `uv lock` or `npm install`
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
| tzdata | 2026.5 | Apache-2.0 | IANA time zones for `zoneinfo` (`[llm].timezone`, the date and time line in every system prompt); Windows has no zone database of its own. Added in feat/guardrails |
| google-auth | 2.62.2 | Apache-2.0 | Verifies Google sign-in ID tokens (signature, audience, issuer, expiry); imported only in `backend/vaani/auth.py`. Added in feat/google-auth |
| requests | 2.34.2 | Apache-2.0 | google-auth's HTTP transport, to download Google's certificates (google-auth has no httpx transport). Added in feat/google-auth |

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
| cryptography | 50.0.2 | google-auth |
| pyasn1, pyasn1-modules | 0.6.5, 0.4.2 | google-auth |
| urllib3, charset-normalizer | 2.8.0, 3.5.2 | requests |

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

## Voice studio (`studio/uv.lock`, feat/voice-studio)

Its own lock file, resolved separately from `backend/uv.lock`, so a package can
have a different version here (fastapi 0.163.2 here, 0.141.1 in the backend). The
backend package `vaani` itself is installed into it, editable, from `../backend`.
Licences from each installed package's metadata, as above.

| Package | Version | License | Why it is here |
|---|---|---|---|
| Python | 3.12 | | `studio/.python-version`; the version the spike ran Chatterbox on |
| chatterbox-tts | 0.1.7 metadata, GitHub commit `ab55923c27757c90cfcc407baa57dc25a7d25217` | MIT | Chatterbox Multilingual v3 (not on PyPI) |
| resemble-perth | 1.1.0, GitHub master at `ff1c8ac55a976971245cdd53c18d6131ca00d993` (chatterbox asks for master unpinned; the lock pins this commit) | MIT | The Perth watermark |
| torch | 2.8.0+cu128 | BSD-3-Clause | Runs the model; overrides chatterbox's 2.6.0 pin |
| torchaudio | 2.8.0+cu128 | BSD | Paired with torch |
| transformers | 5.2.0 | Apache-2.0 | Chatterbox's Llama backbone (pinned by chatterbox) |
| huggingface-hub | 1.33.0 | Apache-2.0 | Downloads the weights at a pinned revision |
| av | 19.0.2 | BSD-3-Clause (bundles FFmpeg, LGPL) | Decodes WebM, M4A, MP3, WAV uploads |
| soundfile | 0.14.0 | BSD-3-Clause | WAV read and write |
| numpy | 1.26.4 | BSD | Chatterbox needs 1.x on Python 3.12 |
| fastapi | 0.163.2 | MIT | The studio's web app |
| uvicorn | 0.54.0 | BSD-3-Clause | Runs it |
| pydantic-settings | 2.16.3 | MIT | `studio/config.toml` + env |
| python-multipart | 0.0.34 | Apache-2.0 | FastAPI's multipart (file upload) parser |
| setuptools | 80.10.2 | MIT | Below 81: perth imports `pkg_resources` |
| faster-whisper / ctranslate2 | 1.2.1 / 4.9.1 | MIT | Via `vaani`; the challenge phrase check |
| gradio, diffusers, librosa | 6.8.0, 0.29.0, 0.11.0 | Apache-2.0, Apache-2.0, ISC | Required by chatterbox-tts; the studio does not use gradio |
| pytest, ruff (dev) | 9.2.0, 0.17.6 | MIT | Tests and lint |

| Model | Pinned by | License | Notes |
|---|---|---|---|
| `ResembleAI/chatterbox`: `ve.pt`, `t3_mtl23ls_v3.safetensors`, `s3gen.pt`, `grapheme_mtl_merged_expanded_v1.json`, `Cangjie5_TC.json` | `hf_revision = "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"` in `studio/config.toml` | MIT | Downloaded on first use into the Hugging Face cache |
| Whisper `small` for the challenge | **Not pinned**, as in the backend | MIT | `[whisper]` in `studio/config.toml` |

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
