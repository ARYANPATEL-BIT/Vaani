"""Groq's hosted Whisper behind the Recognizer interface.

For a machine with no GPU: instead of running Whisper here, each turn's audio
is uploaded to Groq, which runs it on their hardware and sends the text back.
THE USER'S AUDIO LEAVES THIS MACHINE on every turn.

Request:  POST {base_url}/audio/transcriptions, OpenAI's API shape, sent as
          multipart/form-data: the form encoding a browser uses to upload a
          file, where one body carries several named fields, here the WAV
          file plus model, language, prompt, temperature, response_format.
Auth:     the same VAANI_GROQ_API_KEY as the LLM provider, in the
          `Authorization: Bearer <key>` header, never in the URL.
Response: {"text": "...", "x_groq": {...}} for response_format=json.

No thread pool, unlike whisper.py: the work happens on Groq's side, and
waiting on a socket does not block the event loop. So cancelling is
immediate: the request is aborted and transcribe() returns at once, which is
exactly what the runner's "wait until the work has really stopped" needs.
"""

import asyncio
import io
import logging
import wave

import httpx
from pydantic import SecretStr

from vaani.asr.base import AsrError, Recognizer, Transcript
from vaani.config import AsrSettings
from vaani.providers.streaming import Cancelled, until_cancelled
from vaani.spend import RequestCap, SpendCapExceededError

log = logging.getLogger("vaani.asr")

# How much of Groq's error message to keep in the server log.
_MAX_DETAIL = 200


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV header, in memory.

    Raw PCM is just numbers; it does not say its own rate or format, so Groq
    could not decode it. A WAV file is the same numbers behind a 44-byte
    header that does say so. Groq recommends WAV for the lowest latency (no
    decompression on their side). io.BytesIO is a file that lives in RAM, so
    nothing touches the disk.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # bytes per sample: 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


class GroqRecognizer(Recognizer):
    """One HTTP client to Groq, shared by every session in the process.

    The long-lived AsyncClient keeps the connection (and its TLS handshake)
    open between turns, as the LLM providers do. `client` is for tests only.
    """

    def __init__(
        self,
        cfg: AsrSettings,
        sample_rate: int,
        api_key: SecretStr,
        cap: RequestCap,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cfg = cfg.groq
        self._language = cfg.language
        self._prompt = cfg.initial_prompt
        self._sample_rate = sample_rate
        self._api_key = api_key  # SecretStr: prints as '**********'
        self._cap = cap
        self._client = client or httpx.AsyncClient()
        self._url = f"{cfg.groq.base_url}/audio/transcriptions"
        # The runner's own timeout (asyncio.wait, then cancel) is the one that
        # normally fires first; this is httpx's limit on each step (connect,
        # send, wait for the answer), so a stuck socket cannot outlive it.
        self._timeout_s = cfg.timeout_s
        self._timeout = httpx.Timeout(cfg.timeout_s)

    async def transcribe(self, pcm: bytes, cancel: asyncio.Event) -> Transcript | None:
        if cancel.is_set():
            return None  # abandoned before we began: send nothing, pay nothing
        try:
            # Checked and counted BEFORE anything is sent: a refused request
            # costs nothing. Converted to AsrError because the runner turns
            # only AsrError into ASR_FAILED; any other exception would leave
            # the turn waiting for a transcript that never comes.
            self._cap.check_and_count()
        except SpendCapExceededError as exc:
            raise AsrError(f"groq stt: {exc}") from exc

        request = self._client.post(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
            # (filename, bytes, content type): the filename's extension is how
            # Groq knows the format.
            files={
                "file": ("turn.wav", pcm_to_wav(pcm, self._sample_rate), "audio/wav")
            },
            data={
                "model": self._cfg.model,
                "language": self._language,
                "prompt": self._prompt,
                "temperature": str(self._cfg.temperature),
                "response_format": "json",
            },
            timeout=self._timeout,
        )
        try:
            # Races the request against the cancel token (providers/
            # streaming.py). If the token wins, the request task is cancelled,
            # which closes the socket, and Cancelled is raised here.
            response = await until_cancelled(request, cancel)
        except Cancelled:
            return None  # a barge-in or timeout: not an error
        except httpx.TimeoutException as exc:
            raise AsrError(f"groq stt: no response within {self._timeout_s} s") from exc
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, connection reset.
            raise AsrError(f"groq stt: unreachable ({type(exc).__name__})") from exc

        if response.status_code != 200:
            raise self._error_for(response)
        try:
            text = response.json()["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AsrError("groq stt: malformed response") from exc
        # Groq's json answer has no language field. We forced the language, so
        # report that, as faster-whisper does when the language is forced.
        return Transcript(str(text).strip(), self._language)

    def _error_for(self, response: httpx.Response) -> AsrError:
        """A short AsrError for the browser; Groq's own detail goes to the log.

        The runner sends the AsrError text to the browser ("transcription
        failed: ..."), so it holds only the status and what to do. Groq's
        message can carry account details (organisation IDs), so it is
        logged on the server only, with the key redacted.
        """
        status = response.status_code
        log.warning("groq stt: HTTP %d %s", status, self._redact(_detail(response)))
        if status == 429:
            retry = response.headers.get("retry-after")
            after = f", retry after {retry} s" if retry else ""
            return AsrError(f"groq stt: rate limited (HTTP 429){after}")
        if status in (401, 403):
            return AsrError(
                f"groq stt: API key rejected (HTTP {status}); check VAANI_GROQ_API_KEY"
            )
        if status == 404:
            # Groq retires model IDs; a retired one answers 404.
            return AsrError(f"groq stt: model {self._cfg.model!r} not found (HTTP 404)")
        return AsrError(f"groq stt: HTTP {status}")

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key.get_secret_value(), "[redacted]")


def _detail(response: httpx.Response) -> str:
    """Groq's `error.message`, trimmed, or "" if the body has none."""
    try:
        error = response.json().get("error") or {}
        return str(error.get("message", ""))[:_MAX_DETAIL]
    except (ValueError, AttributeError):
        return ""
