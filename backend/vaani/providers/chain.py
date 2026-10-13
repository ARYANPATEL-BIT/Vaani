"""ProviderChain: try providers in the configured order, failing over between them.

The rule, in one line: fail over when THEIR side is broken; surface the error
when OUR side is wrong.

- Fail over on: RateLimitedError, ProviderTimeoutError, ProviderUnavailableError.
  The vendor is overloaded, slow or down; another vendor may be fine.
- Do NOT fail over on: AuthenticationError, ProviderFailedError,
  SpendCapExceededError. A bad key, a bad request or an exhausted budget is
  our problem; trying the next vendor would hide it (and spend money).
- Only fail over BEFORE the first chunk. Once text has been yielded, the user
  may already be hearing it, so a later failure is raised, not restarted.

The chain is itself an LLMProvider, so callers cannot tell it from a single
provider: same `stream(messages, cancel)`, same error types, plus
ProvidersExhaustedError when every provider failed over.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import aclosing
from dataclasses import replace
from time import perf_counter

import httpx
from pydantic import SecretStr

from vaani.config import Settings
from vaani.providers.base import (
    Attempt,
    AuthenticationError,
    LLMProvider,
    Message,
    ProvidersExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
    TextChunk,
)
from vaani.providers.gemini import GeminiProvider
from vaani.providers.groq import GroqProvider
from vaani.spend import RequestCap

log = logging.getLogger("vaani.providers.chain")

# The errors that mean "their side is broken, try the next one".
_FAIL_OVER_ON = (RateLimitedError, ProviderTimeoutError, ProviderUnavailableError)


class ProviderChain(LLMProvider):
    """Streams from the first provider that manages to start answering."""

    def __init__(self, providers: Sequence[tuple[str, LLMProvider]]) -> None:
        if not providers:
            raise ValueError("ProviderChain needs at least one provider")
        # (name, provider) pairs; the name is only for logs and Attempt records.
        self._providers = list(providers)

    async def aclose(self) -> None:
        for _, provider in self._providers:
            await provider.aclose()

    async def stream(
        self, messages: Sequence[Message], cancel: asyncio.Event
    ) -> AsyncIterator[TextChunk]:
        attempts: list[Attempt] = []
        for index, (name, provider) in enumerate(self._providers):
            # Cancelled between attempts: do not start the next provider.
            if cancel.is_set():
                return
            started_at = perf_counter()
            yielded = False
            try:
                # aclosing: if our caller stops early, the provider's stream
                # (and its HTTP connection) is closed immediately.
                async with aclosing(provider.stream(messages, cancel)) as chunks:
                    async for chunk in chunks:
                        yielded = True
                        # Tagged with which provider answered, for the turn's
                        # database row (turn_log.py).
                        yield replace(chunk, provider=name)
                # The provider finished normally OR was cancelled (a cancelled
                # provider ends quietly). Either way, we are done.
                return
            except _FAIL_OVER_ON as exc:
                elapsed_ms = (perf_counter() - started_at) * 1000
                if yielded:
                    # Mid-stream: part of the answer is already out. Report it.
                    log.warning(
                        "%s failed mid-stream after %.0f ms (%s); not failing over",
                        name,
                        elapsed_ms,
                        type(exc).__name__,
                    )
                    raise
                attempts.append(Attempt(name, type(exc).__name__, str(exc), elapsed_ms))
                is_last = index == len(self._providers) - 1
                log.warning(
                    "failover: %s %s after %.0f ms -> %s",
                    name,
                    type(exc).__name__,
                    elapsed_ms,
                    "none left" if is_last else self._providers[index + 1][0],
                )
            # Any other exception (auth, failed request, spend cap) is NOT
            # caught above, so it propagates straight to the caller.
        raise ProvidersExhaustedError(attempts)


def build_chain(
    settings: Settings,
    cap: RequestCap,
    clients: Mapping[str, httpx.AsyncClient] | None = None,
) -> ProviderChain:
    """Build the chain from config.toml's provider_order.

    Fails fast (AuthenticationError) if any listed provider has no key: a
    silently missing key is exactly the kind of our-side problem we refuse to
    hide. `cap` is shared by every provider, so the spend limit covers the
    whole chain. `clients` lets a caller swap in a test HTTP client for one
    provider by name (ask.py's --simulate-429 uses this).
    """
    clients = clients or {}
    providers: list[tuple[str, LLMProvider]] = []
    for name in settings.llm.provider_order:
        client = clients.get(name)
        if name == "gemini":
            key = _require_key(settings.gemini_api_key, name, "VAANI_GEMINI_API_KEY")
            provider = GeminiProvider(settings.llm.gemini, key, cap, client)
        elif name == "groq":
            key = _require_key(settings.groq_api_key, name, "VAANI_GROQ_API_KEY")
            provider = GroqProvider(settings.llm.groq, key, cap, client)
        else:
            raise ValueError(f"unknown provider in provider_order: {name!r}")
        providers.append((name, provider))
    return ProviderChain(providers)


def _require_key(key: SecretStr | None, name: str, env_var: str) -> SecretStr:
    if key is None or not key.get_secret_value():
        raise AuthenticationError(
            f"{name}: {env_var} is not set (env or backend/.env); set it, or "
            f"remove {name!r} from [llm] provider_order in config.toml"
        )
    return key
