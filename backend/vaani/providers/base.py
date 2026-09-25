"""The provider-neutral interface every language model provider implements.

Callers depend on `LLMProvider`, `Message`, `TextChunk` and the error types
here — never on a vendor module. Swapping or adding a vendor then means writing
one new class, not editing every caller.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Message:
    """One message in a conversation, in OUR role names, not a vendor's.

    Each provider translates these (Gemini calls the assistant "model" and
    takes system text in a separate field).
    """

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class TextChunk:
    """One piece of streamed text.

    `model` is the model the provider says actually produced it (it can differ
    from the one we asked for), or None if the provider did not say.
    """

    text: str
    model: str | None = None


# --- Errors -----------------------------------------------------------------
# A small, fixed set. Callers branch on the TYPE (retry later? fix the key?
# try another provider?) instead of parsing vendor messages or HTTP codes.
# Messages must never contain a secret.


class ProviderError(Exception):
    """Base class for every provider failure. Never raised directly."""


class RateLimitedError(ProviderError):
    """The provider refused because we are sending too much (HTTP 429)."""


class AuthenticationError(ProviderError):
    """The API key is missing, invalid, expired, or lacks permission."""


class ProviderTimeoutError(ProviderError):
    """No response (or no next chunk) arrived within the configured time."""


class ProviderFailedError(ProviderError):
    """Anything else: server errors, network failures, malformed or blocked
    responses."""


class LLMProvider(ABC):
    """A language model that streams its answer as it is generated."""

    @abstractmethod
    def stream(
        self, messages: Sequence[Message], cancel: asyncio.Event
    ) -> AsyncIterator[TextChunk]:
        """Send `messages` and yield text chunks in the order they arrive.

        `cancel` is the cancellation token. Implementations check it before
        sending and between chunks; once it is set they stop yielding and
        close the underlying HTTP stream. It cannot interrupt a wait for the
        next chunk — that needs task cancellation as well (week 3).

        Implementations are async generators (`async def ... yield`), which
        is why this is declared with plain `def` returning an AsyncIterator.

        Raises a ProviderError subclass on failure, and SpendCapExceededError
        (vaani.spend) if the request cap is used up.
        """

    @abstractmethod
    async def aclose(self) -> None:
        """Release network resources (open connections)."""
