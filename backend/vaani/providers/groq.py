"""Groq, called over its OpenAI-compatible REST API with httpx, streaming via SSE.

Request:  POST {base_url}/chat/completions   with "stream": true in the body.
          Groq copies OpenAI's API shape, so this file would work, with a
          different base_url, for other OpenAI-compatible vendors.
Auth:     the API key goes in the `Authorization: Bearer <key>` HEADER, never
          in the URL, for the same reason as Gemini (URLs get logged).
Stream:   lines `data: {json}`, each carrying `choices[0].delta.content`; the
          stream ends with the literal line `data: [DONE]`.

How this differs from Gemini (see the learning doc, §5):
- system text is an ordinary message with role "system" (Gemini: a separate
  `systemInstruction` field);
- the assistant role is called "assistant" (Gemini: "model");
- text is in `choices[0].delta.content` (Gemini: `candidates[0].content.parts`);
- the model is chosen in the BODY (Gemini: in the URL path).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing

import httpx
from pydantic import SecretStr

from vaani.config import GroqSettings
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

log = logging.getLogger("vaani.providers.groq")

# How much of Groq's error message to keep in our exception text.
_MAX_DETAIL = 200

# 498 is Groq's own "flex tier capacity exceeded": they are full right now.
_UNAVAILABLE = (498, 500, 502, 503)


class GroqProvider(LLMProvider):
    """Streams answers from one Groq-hosted model.

    Same construction as GeminiProvider: one long-lived AsyncClient unless a
    test passes its own.
    """

    def __init__(
        self,
        settings: GroqSettings,
        api_key: SecretStr,
        cap: RequestCap,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value():
            raise AuthenticationError("groq: API key is empty")
        self._settings = settings
        self._api_key = api_key  # SecretStr: prints as '**********'
        self._cap = cap
        self._client = client or httpx.AsyncClient()
        self._url = f"{settings.base_url}/chat/completions"
        self._timeout = httpx.Timeout(settings.timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(
        self, messages: Sequence[Message], cancel: asyncio.Event
    ) -> AsyncIterator[TextChunk]:
        if cancel.is_set():
            return
        # Same shared cap as every other provider: checked before dispatch.
        self._cap.check_and_count()

        request = self._client.build_request(
            "POST",
            self._url,
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
            json=_request_body(messages, self._settings),
            timeout=self._timeout,
        )
        async with aclosing(
            stream_lines(
                self._client,
                request,
                cancel,
                self._error_for,
                "groq",
                self._settings.timeout_s,
            )
        ) as lines:
            async for line in lines:
                for chunk in self._parse_line(line):
                    yield chunk

    def _parse_line(self, line: str) -> list[TextChunk]:
        """Turn one SSE line into zero or one text chunk."""
        if not line.startswith("data:"):
            return []
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return []  # end-of-stream marker; the body closes right after
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProviderFailedError("groq: malformed stream event") from exc

        if "error" in payload:
            # An error reported INSIDE a 200 stream (e.g. the model failed midway).
            detail = self._redact(_describe(payload))
            raise ProviderFailedError(f"groq: stream error ({detail})")

        # The last event often has "choices": [] and only usage figures.
        choices = payload.get("choices") or [{}]
        # `delta.reasoning` (gpt-oss thinking) is deliberately ignored: never speak it.
        text = choices[0].get("delta", {}).get("content")
        return [TextChunk(text=text, model=payload.get("model"))] if text else []

    def _error_for(self, response: httpx.Response) -> ProviderError:
        """Map an HTTP error response to one of our typed errors."""
        status = response.status_code
        detail = self._redact(_error_detail(response))
        message = f"groq: HTTP {status} {detail}".rstrip()
        log.warning("%s", message)
        if status == 429:
            return RateLimitedError(message)
        if status in (401, 403):
            return AuthenticationError(message)
        if status == 504:
            return ProviderTimeoutError(message)
        if status in _UNAVAILABLE:
            return ProviderUnavailableError(message)
        if status == 404:
            # Groq retires models (llama-3.1-8b-instant went this way), and a
            # retired model ID answers 404. Say so, naming the ID from config.
            return ProviderFailedError(
                f"groq: configured model {self._settings.model!r} not found "
                f"(HTTP 404); it may have been retired. List the models the key "
                f"can use with GET {self._settings.base_url}/models and update "
                f"[llm.groq] model in config.toml. {detail}".rstrip()
            )
        # 400, 413, 422...: our request is wrong.
        return ProviderFailedError(message)

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key.get_secret_value(), "[redacted]")


def _request_body(messages: Sequence[Message], settings: GroqSettings) -> dict:
    """Build the OpenAI-style body. Our role names ARE OpenAI's, so no mapping."""
    body: dict = {
        "model": settings.model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "stream": True,
    }
    # Only sent when configured: non-reasoning models reject these fields.
    if settings.reasoning_effort is not None:
        body["reasoning_effort"] = settings.reasoning_effort
    if settings.include_reasoning is not None:
        body["include_reasoning"] = settings.include_reasoning
    return body


def _describe(payload: dict) -> str:
    """Groq's `error.type` and a trimmed `error.message`, if present."""
    error = payload.get("error") or {}
    if not isinstance(error, dict):
        return ""
    kind = str(error.get("type", ""))
    message = str(error.get("message", ""))[:_MAX_DETAIL]
    return f"{kind}: {message}" if message else kind


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (json.JSONDecodeError, AttributeError):
        return ""
    return _describe(payload) if isinstance(payload, dict) else ""
