"""Tests for ProviderChain.

Most tests use StubProvider: a fake LLMProvider scripted to yield some chunks
and/or raise a chosen error, which counts how often it was called. That tests
the chain's DECISIONS without any HTTP. The spend-cap test uses the real
Gemini and Groq classes (on mock transports), because the cap check lives
inside them.
"""

import asyncio
import logging
from time import perf_counter

import httpx
import pytest
from pydantic import SecretStr

from vaani.config import GeminiSettings, GroqSettings, Settings
from vaani.providers.base import (
    AuthenticationError,
    LLMProvider,
    Message,
    ProviderFailedError,
    ProvidersExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
    TextChunk,
)
from vaani.providers.chain import ProviderChain, build_chain
from vaani.providers.gemini import GeminiProvider
from vaani.providers.groq import GroqProvider
from vaani.spend import RequestCap, SpendCapExceededError

ASK = [Message(role="user", content="hi")]


class StubProvider(LLMProvider):
    """Yields `chunks`, raising `error` once `error_after` chunks are out.

    With `hang=True` it then waits for the token, like a real provider whose
    model has gone quiet, and ends quietly once cancelled.
    """

    def __init__(self, chunks=(), error=None, error_after=0, hang=False):
        self.chunks, self.error, self.error_after = list(chunks), error, error_after
        self.hang = hang
        self.calls = 0

    async def stream(self, messages, cancel):
        self.calls += 1
        for i, text in enumerate(self.chunks):
            if self.error and i == self.error_after:
                raise self.error
            yield TextChunk(text)
        if self.error and self.error_after >= len(self.chunks):
            raise self.error
        if self.hang:
            await cancel.wait()

    async def aclose(self) -> None:
        pass


def collect(chain: ProviderChain, cancel: asyncio.Event | None = None):
    async def go() -> list[str]:
        return [c.text async for c in chain.stream(ASK, cancel or asyncio.Event())]

    return asyncio.run(go())


@pytest.mark.parametrize(
    "error",
    [
        RateLimitedError("gemini: HTTP 429"),
        ProviderTimeoutError("gemini: no response"),
        ProviderUnavailableError("gemini: HTTP 503"),
    ],
)
def test_their_side_broken_fails_over_to_next(error, caplog) -> None:
    first = StubProvider(error=error)
    second = StubProvider(chunks=["from ", "groq"])
    chain = ProviderChain([("gemini", first), ("groq", second)])

    with caplog.at_level(logging.WARNING, logger="vaani.providers.chain"):
        assert collect(chain) == ["from ", "groq"]

    assert (first.calls, second.calls) == (1, 1)
    # The failover log names the provider, the reason and the elapsed time.
    assert f"failover: gemini {type(error).__name__} after" in caplog.text
    assert " ms -> groq" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError("gemini: HTTP 401"),
        ProviderFailedError("gemini: HTTP 400"),
    ],
)
def test_our_side_wrong_does_not_fail_over(error) -> None:
    second = StubProvider(chunks=["never"])
    chain = ProviderChain([("gemini", StubProvider(error=error)), ("groq", second)])

    with pytest.raises(type(error)):
        collect(chain)
    assert second.calls == 0  # the problem surfaced instead of being hidden


def test_all_failing_raises_exhausted_with_each_attempt() -> None:
    chain = ProviderChain(
        [
            ("gemini", StubProvider(error=RateLimitedError("gemini: HTTP 429"))),
            ("groq", StubProvider(error=ProviderTimeoutError("groq: 10s"))),
        ]
    )
    with pytest.raises(ProvidersExhaustedError) as info:
        collect(chain)

    attempts = info.value.attempts
    assert [(a.provider, a.error) for a in attempts] == [
        ("gemini", "RateLimitedError"),
        ("groq", "ProviderTimeoutError"),
    ]
    assert all(a.elapsed_ms >= 0 for a in attempts)
    assert "gemini: RateLimitedError" in str(info.value)
    assert "groq: ProviderTimeoutError" in str(info.value)


def test_mid_stream_failure_is_raised_not_restarted() -> None:
    first = StubProvider(
        chunks=["half an "], error=RateLimitedError("x"), error_after=1
    )
    second = StubProvider(chunks=["whole new answer"])
    chain = ProviderChain([("gemini", first), ("groq", second)])
    got: list[str] = []

    async def go() -> None:
        async for chunk in chain.stream(ASK, asyncio.Event()):
            got.append(chunk.text)

    with pytest.raises(RateLimitedError):
        asyncio.run(go())
    assert got == ["half an "]
    assert second.calls == 0


def test_cancel_stops_the_chain_immediately() -> None:
    first = StubProvider(hang=True)  # model has gone quiet
    second = StubProvider(chunks=["must not run"])
    chain = ProviderChain([("gemini", first), ("groq", second)])

    async def go() -> float:
        cancel = asyncio.Event()
        asyncio.get_running_loop().call_later(0.02, cancel.set)
        start = perf_counter()
        got = [c.text async for c in chain.stream(ASK, cancel)]
        assert got == []
        return (perf_counter() - start) * 1000

    assert asyncio.run(go()) < 200
    assert second.calls == 0  # a cancel is not a failure: no failover


def test_cancel_before_start_calls_no_provider() -> None:
    first = StubProvider(chunks=["x"])
    cancel = asyncio.Event()
    cancel.set()
    assert collect(ProviderChain([("gemini", first)]), cancel) == []
    assert first.calls == 0


def test_spend_cap_covers_the_whole_chain() -> None:
    """cap=1: Gemini's 429 uses the only request, so Groq is refused BEFORE
    any traffic. A failover is not a way around the cap."""
    cap = RequestCap(1)
    groq_requests = []
    gemini = GeminiProvider(
        GeminiSettings(
            model="m",
            base_url="https://g.example",
            timeout_s=5,
            thinking_level="minimal",
        ),
        SecretStr("k1"),
        cap,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(429, json={}))
        ),
    )
    groq = GroqProvider(
        GroqSettings(model="m", base_url="https://q.example", timeout_s=5),
        SecretStr("k2"),
        cap,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: groq_requests.append(request))
        ),
    )
    chain = ProviderChain([("gemini", gemini), ("groq", groq)])

    with pytest.raises(SpendCapExceededError):
        collect(chain)
    assert cap.used == 1
    assert groq_requests == []  # never reached the network


def test_build_chain_fails_fast_on_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("VAANI_GROQ_API_KEY", raising=False)
    settings = Settings(_env_file=None, gemini_api_key="k")

    with pytest.raises(AuthenticationError, match="VAANI_GROQ_API_KEY"):
        build_chain(settings, RequestCap(1))


def test_build_chain_follows_provider_order() -> None:
    settings = Settings(_env_file=None, gemini_api_key="k1", groq_api_key="k2")
    chain = build_chain(settings, RequestCap(1))
    names = [name for name, _ in chain._providers]
    assert names == settings.llm.provider_order
    asyncio.run(chain.aclose())
