"""Gemini, called over its REST API with httpx, streaming via Server-Sent Events.

Request:  POST {base_url}/models/{model}:streamGenerateContent?alt=sse
          `alt=sse` asks Gemini to stream: instead of one JSON body at the end,
          the response body is a series of lines `data: {json}`, each sent as
          soon as the model has produced it.
Auth:     the API key goes in the `x-goog-api-key` HEADER, never in the URL.
          URLs are printed by httpx's own logging and appear in exception
          messages; headers are not.

Everything Gemini-specific (URL shape, JSON field names, role names, status
codes) stays in this file.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing

import httpx
from pydantic import SecretStr

from vaani.config import GeminiSettings
from vaani.providers.base import (
    AuthenticationError,
    LLMProvider,
    Message,
    ProviderError,
    ProviderFailedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
    TextChunk,
)
from vaani.providers.streaming import stream_lines
from vaani.spend import RequestCap

log = logging.getLogger("vaani.providers.gemini")

# Our role names -> Gemini's. "system" is not here: Gemini takes system text
# in a separate `systemInstruction` field, not as a message.
_ROLES = {"user": "user", "assistant": "model"}

# How much of Google's error message to keep in our exception text.
_MAX_DETAIL = 200


class GeminiProvider(LLMProvider):
    """Streams answers from one Gemini model.

    `client` is normally left as None and a long-lived httpx.AsyncClient is
    made here: reusing it keeps the connection (and its TLS handshake) open
    between calls, which saves latency. Tests pass a client whose transport is
    a fake, so no network is touched.
    """

    def __init__(
        self,
        settings: GeminiSettings,
        api_key: SecretStr,
        cap: RequestCap,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # A copied-but-unfilled .env gives "" rather than None. Refuse it here,
        # before any request is counted or sent.
        if not api_key.get_secret_value():
            raise AuthenticationError("gemini: API key is empty")
        self._settings = settings
        # Kept as SecretStr: printing or logging it shows '**********'.
        self._api_key = api_key
        self._cap = cap
        self._client = client or httpx.AsyncClient()
        self._url = f"{settings.base_url}/models/{settings.model}:streamGenerateContent"
        # One number for every step: connect, write, wait for a byte, pool.
        self._timeout = httpx.Timeout(settings.timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(
        self, messages: Sequence[Message], cancel: asyncio.Event
    ) -> AsyncIterator[TextChunk]:
        # Already cancelled: send nothing and count nothing.
        if cancel.is_set():
            return
        # Spend check BEFORE dispatch. Raises SpendCapExceededError if used up.
        self._cap.check_and_count()

        request = self._client.build_request(
            "POST",
            self._url,
            params={"alt": "sse"},
            headers={"x-goog-api-key": self._api_key.get_secret_value()},
            json=_request_body(messages, self._settings.thinking_level),
            timeout=self._timeout,
        )
        # aclosing: if OUR caller stops early, the inner line stream is closed
        # right away too (closing the connection), not whenever Python gets
        # round to garbage-collecting it.
        async with aclosing(
            stream_lines(
                self._client,
                request,
                cancel,
                self._error_for,
                "gemini",
                self._settings.timeout_s,
            )
        ) as lines:
            async for line in lines:
                for chunk in self._parse_line(line):
                    yield chunk

    def _parse_line(self, line: str) -> list[TextChunk]:
        """Turn one SSE line into zero or more text chunks.

        Gemini sends one `data: {json}` line per event, separated by blank
        lines. Blank lines and anything that is not `data:` carry no text.
        """
        if not line.startswith("data:"):
            return []
        try:
            payload = json.loads(line[len("data:") :])
        except json.JSONDecodeError as exc:
            raise ProviderFailedError("gemini: malformed stream event") from exc

        block = payload.get("promptFeedback", {}).get("blockReason")
        if block:
            # Nothing will be said. Surfacing it beats silently yielding nothing.
            raise ProviderFailedError(f"gemini: prompt blocked ({block})")

        model = payload.get("modelVersion")
        candidates = payload.get("candidates") or [{}]
        parts = candidates[0].get("content", {}).get("parts", [])
        # `thought` parts are the model's reasoning, not its answer: never speak
        # them. (With default settings Gemini does not send them at all.)
        return [
            TextChunk(text=part["text"], model=model)
            for part in parts
            if part.get("text") and not part.get("thought")
        ]

    def _error_for(self, response: httpx.Response) -> ProviderError:
        """Map an HTTP error response to one of our typed errors."""
        status = response.status_code
        detail = self._redact(_error_detail(response))
        message = f"gemini: HTTP {status} {detail}".rstrip()
        log.warning("%s", message)
        if status == 429:
            return RateLimitedError(message)
        if status in (401, 403):
            return AuthenticationError(message)
        if status == 504:
            return ProviderTimeoutError(message)
        if status in (500, 502, 503):
            return ProviderUnavailableError(message)  # their side is broken
        # 402 (credits depleted), 400, 404 (bad model ID): our side is wrong.
        return ProviderFailedError(message)

    def _redact(self, text: str) -> str:
        """Belt and braces: if Google ever echoes the key back, blank it out."""
        return text.replace(self._api_key.get_secret_value(), "[redacted]")


def _request_body(messages: Sequence[Message], thinking_level: str) -> dict:
    """Build Gemini's JSON body from our provider-neutral messages."""
    system = [m.content for m in messages if m.role == "system"]
    body: dict = {
        "contents": [
            {"role": _ROLES[m.role], "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": thinking_level}},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
    return body


def _error_detail(response: httpx.Response) -> str:
    """Google's `error.status` and a trimmed `error.message`, if present."""
    try:
        error = response.json().get("error", {})
    except (json.JSONDecodeError, AttributeError):
        return ""
    status = error.get("status", "")
    message = str(error.get("message", ""))[:_MAX_DETAIL]
    return f"{status}: {message}" if message else status
