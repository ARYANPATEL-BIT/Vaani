"""One attempt at a reply: the model's answer streamed out, chunked and spoken.

reply.py's step 3, in its own file since fix/language-and-login added the
first-chunk check (reply.py was already past 300 lines). reply.py calls
`stream_reply` once, or twice when the check fails, and handles every error
it raises (ProviderError, SpendCapExceededError, TtsError): this file only
streams.

What it does with each piece of text the model sends (a "delta"):
  * keeps it on the turn's record (record.parts, for the database row);
  * sends it to the browser as agent.text;
  * feeds it to the chunker (chunker.py), and speaks each chunk the chunker
    cuts AT ONCE (speaker.py), while the model is still generating.

The first-chunk check (`check_script`, forced sessions only): a session that
forces "en" or "hi" must never show or say a reply in the other script. The
first chunk is the earliest point the reply's script is known, so until it
is cut, deltas are HELD instead of sent. If that chunk is in the forced
language's script, the held text goes out and the reply carries on as
normal. If not, the stream is closed (aclosing, below) and False is
returned: nothing of this attempt reached the browser, and reply.py retries.
Holding costs nothing audible: the voice waits for the first chunk anyway.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from time import perf_counter

from vaani.chunker import ClauseChunker
from vaani.config import ChunkerSettings
from vaani.language import reply_language
from vaani.protocol import agent_text
from vaani.providers.base import LLMProvider, Message
from vaani.speaker import Speaker
from vaani.telemetry import LLM_FIRST_TOKEN, LLM_REQUEST, Telemetry
from vaani.turn_log import ReplyRecord

log = logging.getLogger("vaani.reply")

SendJson = Callable[[dict], Awaitable[None]]


async def stream_reply(
    chain: LLMProvider,
    messages: list[Message],
    record: ReplyRecord,  # this reply's turn; every delta is appended to parts
    cancel: asyncio.Event,
    speaker: Speaker | None,  # None: [tts] disabled, the reply is text only
    chunker_cfg: ChunkerSettings,
    send: SendJson,
    telemetry: Telemetry,
    ended_at: float,  # turn_ended's perf_counter, for the timing logs
    check_script: str | None,  # "en"/"hi": the first chunk must be in it
) -> bool:
    """Stream one answer. False only when `check_script` caught a first
    chunk in the other script; True otherwise, cancelled or not."""
    turn_id = record.turn_id
    parts = record.parts
    chunker = ClauseChunker(chunker_cfg)
    requested_at = telemetry.record(LLM_REQUEST, turn_id).at
    # Each delta until the first chunk is cut: (ms after turn_ended, text).
    # Tells "waiting for tokens" from "waiting on synthesis" in debug logs.
    arrivals: list[tuple[float, str]] = []
    first_cut = False
    # Deltas not yet sent, while the first chunk's script is unknown. Only a
    # checked reply holds any (and only a spoken one has chunks to check).
    holding = check_script is not None and speaker is not None
    held: list[str] = []

    async def first_chunk(chunk: str) -> bool:
        """The first chunk is cut: log it, check it, release the held text."""
        nonlocal holding
        _log_first_cut(
            telemetry, turn_id, ended_at, arrivals, chunk, chunker.first_rule
        )
        if holding and reply_language(chunk) != check_script:
            log.warning(
                "session %s: turn %s forced %s reply began in %s script; "
                "nothing shown or said",
                telemetry.session_id,
                turn_id,
                check_script,
                reply_language(chunk),
            )
            return False
        if holding:
            holding = False
            if cancel.is_set():
                return True
            await send(agent_text(turn_id, "".join(held)))
        return True

    # aclosing: if we leave the loop early (a return, an exception), the
    # chain's stream and its HTTP connection are closed at once, not at
    # garbage collection.
    async with aclosing(chain.stream(messages, cancel)) as chunks:
        async for chunk in chunks:
            if cancel.is_set():
                return True
            if not parts:
                _first_token(telemetry, turn_id, requested_at, ended_at)
                record.provider, record.model = chunk.provider, chunk.model
            parts.append(chunk.text)
            if not first_cut:
                arrivals.append(((perf_counter() - ended_at) * 1000, chunk.text))
            if holding:
                held.append(chunk.text)
            else:
                await send(agent_text(turn_id, chunk.text))
            if speaker is None:
                continue
            pieces = chunker.push(chunk.text)
            if pieces and not first_cut:
                first_cut = True
                if not await first_chunk(pieces[0]):
                    return False  # leaving the `async with` closes the stream
            # Synthesis runs inside this loop: while it does, the next tokens
            # wait unread in the HTTP stream. Nothing is lost, and the speech
            # is never waiting on text.
            for piece in pieces:
                await speaker.say(piece)
    if speaker is not None and (last := chunker.flush()):
        if not first_cut and not await first_chunk(last):
            return False  # the whole reply arrived without a cut, and failed
        await speaker.say(last)
    return True


def _first_token(
    telemetry: Telemetry, turn_id: str, requested_at: float, ended_at: float
) -> None:
    span = telemetry.record(LLM_FIRST_TOKEN, turn_id)
    log.info(
        "session %s: turn %s first token: %.0f ms after request, "
        "turn_ended->first agent.text %.0f ms",
        telemetry.session_id,
        turn_id,
        (span.at - requested_at) * 1000,
        (span.at - ended_at) * 1000,
    )


def _log_first_cut(
    telemetry: Telemetry,
    turn_id: str,
    ended_at: float,
    arrivals: list[tuple[float, str]],
    chunk: str,
    rule: str | None,
) -> None:
    # Debug: off in normal runs, switched on for latency tuning. %a escapes
    # non-ASCII, so Devanagari never reaches the console raw.
    log.debug(
        "session %s: turn %s first chunk %a cut %.0f ms after turn_ended "
        "by rule %r; deltas (ms, chars, text): %a",
        telemetry.session_id,
        turn_id,
        chunk,
        (perf_counter() - ended_at) * 1000,
        rule,
        [(round(at), len(text), text) for at, text in arrivals],
    )
