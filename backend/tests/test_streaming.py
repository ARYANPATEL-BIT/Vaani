"""Cancellation that really closes the connection, proven over a real socket.

A tiny HTTP server runs on 127.0.0.1 (asyncio.start_server, no extra library).
It reads the request, optionally sends the headers plus ONE event, and then
never finishes the response, like a model still generating. It then waits for
the client to hang up: reading b"" (end of file) from a TCP socket means the
other side closed it. So `client_closed` being set while `finished_sending` is
False is direct evidence that we closed the connection mid-response instead
of reading it to the end.

Before this branch these tests hung: the provider only checked the token when
a chunk arrived, and this server never sends another one. `wait_for` turns
such a hang into a failure.
"""

import asyncio
import json
from time import perf_counter

import httpx
import pytest
from pydantic import SecretStr

from vaani.config import GeminiSettings
from vaani.providers.base import Message
from vaani.providers.gemini import GeminiProvider
from vaani.providers.streaming import Cancelled, until_cancelled
from vaani.spend import RequestCap

ASK = [Message(role="user", content="hi")]


def _event(text: str) -> bytes:
    payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return f"data: {json.dumps(payload)}\r\n\r\n".encode()


class HangingServer:
    """Sends part of a response, never the rest, and notices the hang-up."""

    def __init__(self, send_first_event: bool) -> None:
        self.send_first_event = send_first_event
        self.request_received = asyncio.Event()
        self.client_closed = asyncio.Event()
        self.finished_sending = False  # never becomes True: that is the point

    async def handle(self, reader, writer) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":")[1])
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        await reader.readexactly(length)
        self.request_received.set()
        if self.send_first_event:
            # Chunked encoding: the body length is not known up front, which
            # is how a real streaming response is sent.
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
            )
            data = _event("one")
            writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
            await writer.drain()
        # "Still generating": block until the client goes away.
        try:
            rest = await reader.read(1)
        except ConnectionError:  # Windows may report a reset instead of EOF
            rest = b""
        if rest == b"":
            self.client_closed.set()
        writer.close()


async def _cancel_mid_response(send_first_event: bool):
    server = HangingServer(send_first_event)
    listener = await asyncio.start_server(server.handle, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    settings = GeminiSettings(
        model="m",
        base_url=f"http://127.0.0.1:{port}/v1beta",
        timeout_s=30.0,  # far longer than the test: a stop can't be a timeout
        thinking_level="minimal",
    )
    # trust_env=False: ignore any HTTP proxy set on the machine running tests.
    client = httpx.AsyncClient(trust_env=False)
    provider = GeminiProvider(settings, SecretStr("k"), RequestCap(5), client)
    cancel = asyncio.Event()
    got: list[str] = []
    first_chunk = asyncio.Event()

    async def consume() -> None:
        async for chunk in provider.stream(ASK, cancel):
            got.append(chunk.text)
            first_chunk.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(server.request_received.wait(), 5)
    if send_first_event:
        await asyncio.wait_for(first_chunk.wait(), 5)
    await asyncio.sleep(0.05)  # the provider is now blocked on a read

    cancelled_at = perf_counter()
    cancel.set()
    await asyncio.wait_for(task, 2)  # a hang fails the test instead
    stop_ms = (perf_counter() - cancelled_at) * 1000
    await asyncio.wait_for(server.client_closed.wait(), 2)

    await provider.aclose()
    listener.close()
    await listener.wait_closed()
    return got, stop_ms, server


@pytest.mark.parametrize("send_first_event", [True, False])
def test_cancel_closes_the_connection_while_server_is_still_sending(
    send_first_event,
) -> None:
    """True: cancel while waiting for the NEXT chunk.
    False: cancel while waiting for the response HEADERS (model thinking)."""
    got, stop_ms, server = asyncio.run(_cancel_mid_response(send_first_event))

    assert got == (["one"] if send_first_event else [])
    assert stop_ms < 500  # stopped at once, not at the 30 s timeout
    assert server.client_closed.is_set()  # the server saw the socket close...
    assert not server.finished_sending  # ...while its response was unfinished


def test_until_cancelled_returns_result_when_work_wins() -> None:
    async def go():
        return await until_cancelled(asyncio.sleep(0, result="done"), asyncio.Event())

    assert asyncio.run(go()) == "done"


def test_until_cancelled_aborts_the_pending_work() -> None:
    async def go() -> bool:
        work_was_cancelled = False

        async def slow() -> None:
            nonlocal work_was_cancelled
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                work_was_cancelled = True
                raise

        cancel = asyncio.Event()
        asyncio.get_running_loop().call_later(0.02, cancel.set)
        with pytest.raises(Cancelled):
            await until_cancelled(slow(), cancel)
        return work_was_cancelled

    assert asyncio.run(go())  # the wait was torn down, not left running
