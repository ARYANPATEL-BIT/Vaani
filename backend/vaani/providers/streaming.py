"""The HTTP streaming plumbing every provider shares, with real cancellation.

Two things live here:

- `until_cancelled`: wait for something (response headers, the next line)
  OR for the cancellation token, whichever happens first. If the token wins,
  the wait is aborted there and then.
- `stream_lines`: send one streaming request and yield the response body line
  by line, closing the connection the moment the token is set.

Why a race and not just `if cancel.is_set()` between lines: a check between
lines only runs when a line ARRIVES. If the model pauses for three seconds,
the check does not run for three seconds, and the user who interrupted hears
nothing change. Racing the wait against `cancel.wait()` reacts immediately.

Nothing here is vendor-specific: the vendor supplies the request and a
function that maps an error response to one of our typed errors.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

import httpx

from vaani.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

T = TypeVar("T")


class Cancelled(Exception):
    """Internal signal: the token was set while we were waiting.

    Raised by `until_cancelled`, caught inside `stream_lines`. It never leaves
    this module: to every caller, a cancelled stream simply ends.
    """


async def until_cancelled(awaitable: Awaitable[T], cancel: asyncio.Event) -> T:
    """Return `awaitable`'s result, or raise Cancelled if `cancel` is set first.

    On cancel, the wait is aborted with task cancellation, so whatever it was
    blocked on (a socket read, a connect) is torn down, not left running.
    """
    if cancel.is_set():
        raise Cancelled
    # Two tasks run side by side: the real work, and one that finishes the
    # moment the token is set. asyncio.wait returns as soon as EITHER is done.
    work = asyncio.ensure_future(awaitable)
    stop = asyncio.ensure_future(cancel.wait())
    try:
        await asyncio.wait({work, stop}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        # WE were cancelled from outside (e.g. the whole turn's task). Take the
        # work down with us rather than leaving it running unowned.
        work.cancel()
        raise
    finally:
        stop.cancel()  # never leave the watcher task behind

    if work.done():
        # Work finished (possibly at the same instant as cancel): use it.
        # .result() re-raises the work's own exception, if it had one.
        return work.result()

    # The token won. Cancelling the task throws CancelledError into the
    # pending read; httpcore reacts by closing the socket. We then wait for
    # that cleanup to finish, so the connection is really gone when we return.
    work.cancel()
    await asyncio.wait({work})
    if not work.cancelled():
        work.exception()  # mark any cleanup error as seen (avoids a warning)
    raise Cancelled


async def stream_lines(
    client: httpx.AsyncClient,
    request: httpx.Request,
    cancel: asyncio.Event,
    error_for: Callable[[httpx.Response], ProviderError],
    vendor: str,
    timeout_s: float,
) -> AsyncIterator[str]:
    """Send `request`, yield the body line by line, stop at once on cancel.

    Ends quietly (no exception) when cancelled. Raises ProviderError subclasses
    on failure: `error_for(response)` for a non-200 status, our own mapping
    for timeouts and connection failures.
    """
    try:
        # stream=True: return as soon as the HEADERS arrive; the body is read
        # afterwards, piece by piece. Waiting for headers is often the longest
        # wait of all (the model is thinking), so it is raced too.
        response = await until_cancelled(client.send(request, stream=True), cancel)
        try:
            if response.status_code != 200:
                await until_cancelled(response.aread(), cancel)  # small error body
                raise error_for(response)
            lines = response.aiter_lines()
            # anext(lines, None) gives None at end of body instead of raising.
            while (
                line := await until_cancelled(anext(lines, None), cancel)
            ) is not None:
                yield line
        finally:
            # CLOSE, not drain. If the server is still sending, httpcore closes
            # the socket rather than reading the rest (and paying for it). This
            # runs on every exit: normal end, cancel, error, or the caller
            # closing this generator early.
            await response.aclose()
    except Cancelled:
        return
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(
            f"{vendor}: no response within {timeout_s}s"
        ) from exc
    except httpx.HTTPError as exc:
        # Connection refused, DNS failure, connection reset mid-stream: their
        # side (or the path to it) is broken, which is a failover case.
        raise ProviderUnavailableError(f"{vendor}: {type(exc).__name__}") from exc
