"""GroqRecognizer with a stubbed HTTP layer: no test here ever calls Groq.

httpx.MockTransport hands every request the recogniser makes to a function we
write (the "handler"), which inspects it and returns a canned response. So
these tests check exactly what would go over the wire, and how each kind of
answer (or failure) comes back, without a network or an API key.
"""

import asyncio
import io
import logging
import subprocess
import sys
import wave
from pathlib import Path
from time import perf_counter

import httpx
import pytest
from pydantic import SecretStr

from vaani.asr import AsrError, Transcript, build_recognizer
from vaani.asr.groq import GroqRecognizer, pcm_to_wav
from vaani.asr.runner import AsrRunner
from vaani.config import Settings
from vaani.protocol import ErrorCode
from vaani.spend import RequestCap
from vaani.telemetry import Telemetry

KEY = "gsk-test-secret-DO-NOT-LEAK"
PCM = b"\x01\x00\x02\x00" * 8000  # 1 s of 16 kHz 16-bit audio
BACKEND = Path(__file__).resolve().parent.parent


def groq_cfg(pick: bool = False, **update):
    # _env_file=None: a developer's backend/.env must not change these tests.
    # pick_language off unless asked: these tests are about ONE request; the
    # two-request pick is tested in test_asr_language_pick.py.
    base = Settings(_env_file=None).asr
    groq = base.groq.model_copy(update={"pick_language": pick})
    return base.model_copy(
        update={"enabled": True, "engine": "groq", "groq": groq, **update}
    )


def make(handler, cap: RequestCap | None = None, **cfg) -> GroqRecognizer:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GroqRecognizer(
        groq_cfg(**cfg), 16000, SecretStr(KEY), cap or RequestCap(10), client
    )


def ok(text: str = " haan ji, kal milte hain "):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": text, "x_groq": {"id": "req_1"}})

    return handler


def form_fields(request: httpx.Request) -> dict[str, bytes]:
    """Split a multipart/form-data body into {field name: raw value}."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields = {}
    for part in request.content.split(b"--" + boundary)[1:-1]:
        head, _, value = part.partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields[name] = value[: -len(b"\r\n")]  # each part ends with CRLF
    return fields


def run(coro):
    return asyncio.run(coro)


# --- What goes over the wire ------------------------------------------------


def test_pcm_to_wav_is_16k_mono_16bit_with_the_same_samples() -> None:
    with wave.open(io.BytesIO(pcm_to_wav(PCM, 16000)), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.readframes(wav.getnframes()) == PCM


def test_request_carries_model_language_prompt_temperature_and_wav() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok()(request)

    # Values that are not the committed defaults, so passing proves each one
    # is read from config rather than hardcoded.
    cfg = groq_cfg(language="mr", initial_prompt="kal milte hain")
    cfg.groq = cfg.groq.model_copy(update={"model": "whisper-x", "temperature": 0.3})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    rec = GroqRecognizer(cfg, 16000, SecretStr(KEY), RequestCap(10), client)
    run(rec.transcribe(PCM, asyncio.Event()))

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
    fields = form_fields(request)
    assert fields["model"] == b"whisper-x"
    assert fields["language"] == b"mr"
    assert fields["prompt"] == b"kal milte hain"
    assert fields["temperature"] == b"0.3"
    assert fields["response_format"] == b"json"
    assert fields["file"] == pcm_to_wav(PCM, 16000)


def test_key_goes_only_in_the_authorization_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok()(request)

    run(make(handler).transcribe(PCM, asyncio.Event()))
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in str(seen[0].url)
    assert KEY.encode() not in seen[0].content


def test_text_is_stripped_and_language_is_the_forced_one() -> None:
    result = run(make(ok()).transcribe(PCM, asyncio.Event()))
    # Groq does not report a language in its json response; faster-whisper
    # with a forced language reports that same forced code (protocol.py).
    assert result == Transcript("haan ji, kal milte hain", "hi")


# --- Failures map to AsrError, with no secret and no vendor detail ----------


def status(code: int, headers: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"error": {"message": f"bad key {KEY} for org_123", "type": "x"}}
        return httpx.Response(code, json=body, headers=headers or {})

    return handler


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (429, "rate limited (HTTP 429), retry after 7 s"),
        (401, "API key rejected (HTTP 401); check VAANI_GROQ_API_KEY"),
        (404, "model 'whisper-large-v3' not found (HTTP 404)"),
        (500, "HTTP 500"),
    ],
)
def test_http_errors_become_short_asr_errors(code, expected, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="vaani.asr")
    headers = {"retry-after": "7"} if code == 429 else None
    with pytest.raises(AsrError) as info:
        run(make(status(code, headers)).transcribe(PCM, asyncio.Event()))
    message = str(info.value)
    assert message == f"groq stt: {expected}"
    # The browser sees this message: Groq's own text (org IDs...) stays out.
    assert "org_123" not in message
    # The log keeps Groq's detail for us, with the key redacted.
    assert "org_123" in caplog.text
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.ReadTimeout, "groq stt: no response within 5.0 s"),
        (httpx.ConnectError, "groq stt: unreachable (ConnectError)"),
    ],
)
def test_network_failures_become_asr_errors(exc, expected) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc("boom", request=request)

    with pytest.raises(
        AsrError, match=expected.replace("(", r"\(").replace(")", r"\)")
    ):
        run(make(handler).transcribe(PCM, asyncio.Event()))


def test_malformed_body_is_an_asr_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(AsrError, match="malformed response"):
        run(make(handler).transcribe(PCM, asyncio.Event()))


# --- Cancellation and the spend cap -----------------------------------------


def test_cancel_mid_request_returns_none_at_once() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)  # Groq "thinking"; the cancel must not wait
        return httpx.Response(200, json={"text": "never"})

    async def scenario() -> tuple[object, float]:
        cancel = asyncio.Event()
        task = asyncio.create_task(make(handler).transcribe(PCM, cancel))
        await asyncio.sleep(0.05)
        started = perf_counter()
        cancel.set()
        return await task, perf_counter() - started

    result, waited_s = run(scenario())
    assert result is None
    assert waited_s < 0.5


def test_already_cancelled_sends_nothing() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok()(request)

    cancel = asyncio.Event()
    cancel.set()
    assert run(make(handler).transcribe(PCM, cancel)) is None
    assert seen == []


def test_cap_is_checked_before_the_request_is_sent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok()(request)

    rec = make(handler, cap=RequestCap(1))
    run(rec.transcribe(PCM, asyncio.Event()))
    # An AsrError, not SpendCapExceededError: the runner only turns AsrError
    # into ASR_FAILED; anything else would leave the turn waiting forever.
    with pytest.raises(AsrError, match="request cap reached: 1/1"):
        run(rec.transcribe(PCM, asyncio.Event()))
    assert len(seen) == 1


# --- Through the real AsrRunner ---------------------------------------------


def test_a_groq_failure_reaches_the_browser_as_asr_failed() -> None:
    """The runner's existing ASR_FAILED path works unchanged for Groq."""
    sent: list[dict] = []
    finals: list[tuple[str, str | None]] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    async def on_final(turn_id: str, text: str | None, picked: str | None) -> None:
        finals.append((turn_id, text))

    async def scenario() -> None:
        cfg = groq_cfg()
        rec = make(status(503))
        runner = AsrRunner(rec, cfg, 20, send, Telemetry("s1"), on_final)
        runner.request_final("t1", PCM, 1000, perf_counter())
        while not finals:
            await asyncio.sleep(0.001)
        await runner.close()

    run(scenario())
    assert sent == [
        {
            "type": "error",
            "code": ErrorCode.ASR_FAILED,
            "message": "transcription failed: groq stt: HTTP 503",
        }
    ]
    assert finals == [("t1", None)]


# --- Startup: build_recognizer ----------------------------------------------


def test_missing_key_refuses_to_start_naming_the_variable() -> None:
    with pytest.raises(AsrError, match="VAANI_GROQ_API_KEY is not set"):
        build_recognizer(groq_cfg(), 16000, None)
    with pytest.raises(AsrError, match="VAANI_GROQ_API_KEY is not set"):
        build_recognizer(groq_cfg(), 16000, SecretStr(""))


def test_partials_with_groq_refuse_to_start() -> None:
    with pytest.raises(AsrError, match="partial_interval_ms"):
        build_recognizer(groq_cfg(partial_interval_ms=1000), 16000, SecretStr(KEY))


def test_groq_engine_builds_a_groq_recognizer() -> None:
    rec = build_recognizer(groq_cfg(), 16000, SecretStr(KEY))
    assert isinstance(rec, GroqRecognizer)


def test_groq_engine_never_imports_faster_whisper() -> None:
    """In a fresh interpreter: this test process has faster-whisper loaded
    already (test_asr_whisper.py imports it), so only a new process can show
    that the groq path does not pull it in."""
    code = (
        "import sys\n"
        "from pydantic import SecretStr\n"
        "from vaani.asr import build_recognizer\n"
        "from vaani.config import Settings\n"
        "cfg = Settings(_env_file=None).asr.model_copy(update={'engine': 'groq'})\n"
        "build_recognizer(cfg, 16000, SecretStr('k'))\n"
        "print(sorted(m for m in ('faster_whisper', 'ctranslate2') "
        "if m in sys.modules))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "[]"
