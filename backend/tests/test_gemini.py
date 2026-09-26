"""Tests for GeminiProvider with a stubbed HTTP layer — no network access.

httpx.MockTransport replaces the real network: every request the provider
makes is handed to our `handler` function, which returns whatever response the
test wants (or raises, to simulate a timeout). FakeStream is the response
body; it hands out one SSE event at a time and records whether it was closed.
"""

import asyncio
import json
import logging
import traceback

import httpx
import pytest
from pydantic import SecretStr

from vaani.config import GeminiSettings
from vaani.providers.base import (
    AuthenticationError,
    Message,
    ProviderError,
    ProviderFailedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
)
from vaani.providers.gemini import GeminiProvider
from vaani.spend import RequestCap, SpendCapExceededError

KEY = "AIza-test-secret-DO-NOT-LEAK"
SETTINGS = GeminiSettings(
    model="test-model",
    base_url="https://gemini.example/v1beta",
    timeout_s=5.0,
    thinking_level="minimal",
)
ASK = [Message(role="user", content="hi")]


class FakeStream(httpx.AsyncByteStream):
    """A response body delivered piece by piece, like a real stream."""

    def __init__(self, pieces: list[bytes]) -> None:
        self.pieces = pieces
        self.closed = False

    async def __aiter__(self):
        for piece in self.pieces:
            yield piece

    async def aclose(self) -> None:
        self.closed = True


def event(text: str, model: str = "test-model-001") -> bytes:
    """One Gemini SSE event carrying `text`."""
    payload = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}],
        "modelVersion": model,
    }
    return f"data: {json.dumps(payload)}\r\n\r\n".encode()


def make(handler, cap: RequestCap | None = None) -> GeminiProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiProvider(SETTINGS, SecretStr(KEY), cap or RequestCap(10), client)


def run(provider: GeminiProvider, cancel: asyncio.Event | None = None) -> list:
    """Collect every chunk the provider yields (errors propagate)."""

    async def collect() -> list:
        return [c async for c in provider.stream(ASK, cancel or asyncio.Event())]

    return asyncio.run(collect())


def error_response(status: int, body: dict | None = None):
    return lambda request: httpx.Response(status, json=body or {})


# --- Streaming --------------------------------------------------------------


def test_chunks_yielded_in_order_with_model() -> None:
    body = FakeStream([event("Hel"), event("lo"), event(" world")])
    chunks = run(make(lambda request: httpx.Response(200, stream=body)))

    assert [c.text for c in chunks] == ["Hel", "lo", " world"]
    assert chunks[0].model == "test-model-001"  # the model that answered


def test_request_shape_and_key_in_header_not_url() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, stream=FakeStream([event("ok")]))

    messages = [
        Message(role="system", content="be brief"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="hello"),
    ]
    provider = make(handler)

    async def go() -> None:
        async for _ in provider.stream(messages, asyncio.Event()):
            pass

    asyncio.run(go())
    request = seen["request"]
    body = json.loads(request.content)

    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    assert request.url.path.endswith("/models/test-model:streamGenerateContent")
    assert request.url.params["alt"] == "sse"
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert body["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal"


# --- Errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, RateLimitedError),
        (401, AuthenticationError),
        (403, AuthenticationError),
        (504, ProviderTimeoutError),
        (402, ProviderFailedError),
        (404, ProviderFailedError),
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
    ],
)
def test_status_codes_map_to_typed_errors(status, expected) -> None:
    body = {"error": {"code": status, "status": "X", "message": "nope"}}
    with pytest.raises(expected):
        run(make(error_response(status, body)))


def test_timeout_raises_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ProviderTimeoutError):
        run(make(handler))


def test_network_failure_raises_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderUnavailableError):
        run(make(handler))


def test_blocked_prompt_raises_failed_error() -> None:
    blocked = b'data: {"promptFeedback": {"blockReason": "SAFETY"}}\r\n\r\n'
    body = FakeStream([blocked])
    with pytest.raises(ProviderFailedError, match="blocked"):
        run(make(lambda request: httpx.Response(200, stream=body)))


def test_malformed_event_raises_failed_error() -> None:
    body = FakeStream([b"data: {not json\r\n\r\n"])
    with pytest.raises(ProviderFailedError):
        run(make(lambda request: httpx.Response(200, stream=body)))


def test_empty_key_is_refused_up_front() -> None:
    with pytest.raises(AuthenticationError):
        GeminiProvider(SETTINGS, SecretStr(""), RequestCap(1))


# --- The key never leaks ----------------------------------------------------


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def test_key_never_in_logs_or_exceptions(caplog) -> None:
    """Drive every path with DEBUG logging on for ALL loggers (ours and
    httpx's), then search the logs and each exception's full traceback text
    — including chained causes — for the key. One error body even echoes the
    key back, to prove we redact it."""
    echo = {"error": {"status": "INVALID_ARGUMENT", "message": f"bad key {KEY}"}}
    handlers = [
        lambda request: httpx.Response(200, stream=FakeStream([event("ok")])),
        error_response(429),
        error_response(401),
        error_response(400, echo),
        _timeout,
    ]
    texts = []
    with caplog.at_level(logging.DEBUG):
        for handler in handlers:
            try:
                run(make(handler))
            except ProviderError as exc:
                texts.append("".join(traceback.format_exception(exc)))
                texts.append(repr(exc))

    assert len(texts) == 8  # four failing paths, two texts each
    assert KEY not in caplog.text
    assert all(KEY not in text for text in texts)


# --- Cancellation and the request cap ---------------------------------------


def test_cancel_before_request_sends_nothing() -> None:
    calls = []
    cap = RequestCap(10)
    provider = make(lambda request: calls.append(request), cap)
    cancel = asyncio.Event()
    cancel.set()

    assert run(provider, cancel) == []
    assert calls == [] and cap.used == 0  # not sent, not counted


def test_cancel_between_chunks_stops_and_closes_stream() -> None:
    body = FakeStream([event("one"), event("two"), event("three")])
    provider = make(lambda request: httpx.Response(200, stream=body))
    cancel = asyncio.Event()

    async def go() -> list[str]:
        got = []
        async for chunk in provider.stream(ASK, cancel):
            got.append(chunk.text)
            cancel.set()  # the user interrupts after the first chunk
        return got

    assert asyncio.run(go()) == ["one"]
    assert body.closed  # the HTTP stream was closed, not left dangling


def test_request_cap_refuses_before_dispatch() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, stream=FakeStream([event("ok")]))

    provider = make(handler, RequestCap(1))
    run(provider)
    with pytest.raises(SpendCapExceededError):
        run(provider)

    assert len(calls) == 1  # the refused call never reached the network
