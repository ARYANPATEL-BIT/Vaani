"""Tests for GroqProvider with a stubbed HTTP layer — no network access.

Same approach as test_gemini.py: httpx.MockTransport hands every request to a
function we write, and FakeStream is a response body delivered piece by piece.
"""

import asyncio
import json
import logging
import traceback

import httpx
import pytest
from pydantic import SecretStr

from vaani.config import GroqSettings
from vaani.providers.base import (
    AuthenticationError,
    Message,
    ProviderError,
    ProviderFailedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
)
from vaani.providers.groq import GroqProvider
from vaani.spend import RequestCap

KEY = "gsk-test-secret-DO-NOT-LEAK"
SETTINGS = GroqSettings(
    model="test-model", base_url="https://groq.example/openai/v1", timeout_s=5.0
)
ASK = [Message(role="user", content="hi")]
DONE = b"data: [DONE]\n\n"


class FakeStream(httpx.AsyncByteStream):
    def __init__(self, pieces: list[bytes]) -> None:
        self.pieces = pieces
        self.closed = False

    async def __aiter__(self):
        for piece in self.pieces:
            yield piece

    async def aclose(self) -> None:
        self.closed = True


def event(text: str | None, model: str = "test-model") -> bytes:
    """One OpenAI-style streaming event whose delta carries `text`."""
    delta = {} if text is None else {"content": text}
    payload = {"model": model, "choices": [{"index": 0, "delta": delta}]}
    return f"data: {json.dumps(payload)}\n\n".encode()


def make(handler, settings: GroqSettings = SETTINGS) -> GroqProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GroqProvider(settings, SecretStr(KEY), RequestCap(10), client)


def run(provider: GroqProvider, messages=ASK) -> list:
    async def collect() -> list:
        return [c async for c in provider.stream(messages, asyncio.Event())]

    return asyncio.run(collect())


def ok(*pieces: bytes):
    return lambda request: httpx.Response(200, stream=FakeStream(list(pieces)))


def test_chunks_yielded_in_order_and_done_ends_stream() -> None:
    # A role-only first delta and a usage-only last event carry no text.
    usage = b'data: {"choices": [], "usage": {"total_tokens": 3}}\n\n'
    chunks = run(make(ok(event(None), event("Hel"), event("lo"), usage, DONE)))

    assert [c.text for c in chunks] == ["Hel", "lo"]
    assert chunks[0].model == "test-model"


def test_request_shape_key_in_header_and_system_stays_a_message() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, stream=FakeStream([event("ok"), DONE]))

    messages = [
        Message(role="system", content="be brief"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="hello"),
    ]
    run(make(handler), messages)
    request = seen["request"]
    body = json.loads(request.content)

    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in str(request.url)
    assert request.url.path.endswith("/openai/v1/chat/completions")
    assert body["model"] == "test-model" and body["stream"] is True
    # Unlike Gemini: system is a normal message, roles pass through unchanged.
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant"]
    # Reasoning fields are not configured here, so they are not sent.
    assert "reasoning_effort" not in body and "include_reasoning" not in body


def test_reasoning_fields_sent_only_when_configured() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, stream=FakeStream([DONE]))

    settings = SETTINGS.model_copy(
        update={"reasoning_effort": "low", "include_reasoning": False}
    )
    run(make(handler, settings))

    assert seen["body"]["reasoning_effort"] == "low"
    assert seen["body"]["include_reasoning"] is False


def test_reasoning_text_is_never_yielded() -> None:
    thinking = b'data: {"choices": [{"delta": {"reasoning": "hmm"}}]}\n\n'
    chunks = run(make(ok(thinking, event("answer"), DONE)))
    assert [c.text for c in chunks] == ["answer"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, RateLimitedError),
        (401, AuthenticationError),
        (403, AuthenticationError),
        (504, ProviderTimeoutError),
        (498, ProviderUnavailableError),  # Groq: flex capacity exceeded
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
        (400, ProviderFailedError),
        (404, ProviderFailedError),
    ],
)
def test_status_codes_map_to_typed_errors(status, expected) -> None:
    body = {"error": {"message": "nope", "type": "x"}}
    with pytest.raises(expected):
        run(make(lambda request: httpx.Response(status, json=body)))


def test_connection_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailableError):
        run(make(handler))


def test_error_inside_stream_raises_failed_error() -> None:
    err = b'data: {"error": {"message": "model crashed", "type": "server"}}\n\n'
    with pytest.raises(ProviderFailedError, match="stream error"):
        run(make(ok(event("par"), err)))


def test_empty_key_is_refused_up_front() -> None:
    with pytest.raises(AuthenticationError):
        GroqProvider(SETTINGS, SecretStr(""), RequestCap(1))


def test_key_never_in_logs_or_exceptions(caplog) -> None:
    echo = {"error": {"message": f"Invalid API Key {KEY}", "type": "auth"}}

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    handlers = [
        ok(event("ok"), DONE),
        lambda request: httpx.Response(429, json={}),
        lambda request: httpx.Response(401, json=echo),
        timeout,
    ]
    texts = []
    with caplog.at_level(logging.DEBUG):
        for handler in handlers:
            try:
                run(make(handler))
            except ProviderError as exc:
                texts.append("".join(traceback.format_exception(exc)))

    assert len(texts) == 3
    assert KEY not in caplog.text
    assert all(KEY not in text for text in texts)
