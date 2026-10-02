"""One session's speech recognition scheduler.

The gateway's frame loop must never wait for recognition, so it only calls
the synchronous request_*/abandon_turn methods here, which record what is
wanted and return at once. A single background task per session (the
"drain" task) does the actual work, one job at a time:

  * finals run first, in turn order, and are never dropped;
  * at most ONE partial waits; a newer partial replaces it (latest wins), so
    partials never pile up behind a slow decode;
  * a final for a turn discards that turn's partials, waiting or running.

One job at a time per session also means one worker thread at a time per
session. An abandoned or timed-out decode keeps its thread until the engine
stops (local inference cannot be interrupted), and this session's next job
waits for that. So no session can hold more than one pool thread, and
rapid turns from one user cannot starve everyone else.

A job that was abandoned (barge-in, disconnect) is never emitted: the check
sits directly in front of the send.
"""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from time import perf_counter

from vaani.asr.base import AsrError, Recognizer, Transcript
from vaani.config import AsrSettings
from vaani.protocol import ErrorCode, error, transcript_final, transcript_partial
from vaani.telemetry import ASR_FINAL, ASR_PARTIAL, ASR_START, Telemetry

log = logging.getLogger("vaani.asr")

SendJson = Callable[[dict], Awaitable[None]]


@dataclass
class _Job:
    """One transcription to run: a partial or a turn's final."""

    turn_id: str
    pcm: bytes
    final: bool
    duration_ms: int = 0  # finals only: speech length of the turn
    ended_at: float | None = None  # finals only: perf_counter of turn_ended
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    abandoned: bool = False


class AsrRunner:
    """Schedules one session's transcriptions and sends their results."""

    def __init__(
        self,
        recognizer: Recognizer,
        cfg: AsrSettings,
        send_json: SendJson,
        telemetry: Telemetry,
    ) -> None:
        self._recognizer = recognizer
        self._timeout_s = cfg.timeout_s
        self._send = send_json
        self._telemetry = telemetry
        self._session_id = telemetry.session_id
        self._finals: deque[_Job] = deque()
        self._partial: _Job | None = None  # the next partial, if any
        self._running: _Job | None = None
        self._task: asyncio.Task | None = None
        self._closed = False

    # --- Called from the frame loop: synchronous, never wait -------------

    def request_partial(self, turn_id: str, pcm: bytes) -> None:
        """Transcribe the utterance so far. Replaces a partial still waiting."""
        if self._closed:
            return
        self._partial = _Job(turn_id, pcm, final=False)
        self._kick()

    def request_final(
        self, turn_id: str, pcm: bytes, duration_ms: int, ended_at: float
    ) -> None:
        """Transcribe a finished turn. Supersedes that turn's partials."""
        if self._closed:
            return
        if self._partial is not None and self._partial.turn_id == turn_id:
            self._partial = None
        running = self._running
        if running is not None and not running.final and running.turn_id == turn_id:
            self._abandon(running)
        self._finals.append(_Job(turn_id, pcm, True, duration_ms, ended_at))
        self._kick()

    def abandon_turn(self, turn_id: str) -> None:
        """Drop everything for `turn_id`: nothing more is sent for it."""
        if self._partial is not None and self._partial.turn_id == turn_id:
            self._partial = None
        self._finals = deque(j for j in self._finals if j.turn_id != turn_id)
        if self._running is not None and self._running.turn_id == turn_id:
            self._abandon(self._running)

    async def close(self) -> None:
        """Session over: abandon everything and stop the drain task."""
        self._closed = True
        self._finals.clear()
        self._partial = None
        if self._running is not None:
            self._abandon(self._running)
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    # --- Internals ---------------------------------------------------------

    def _abandon(self, job: _Job) -> None:
        job.abandoned = True  # read in front of the send: never emit it
        job.cancel.set()  # ask the recogniser to stop early

    def _kick(self) -> None:
        """Start the drain task unless it is already running."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._drain())

    def _next_job(self) -> _Job | None:
        if self._finals:
            return self._finals.popleft()
        job, self._partial = self._partial, None
        return job

    async def _drain(self) -> None:
        """Run jobs one after another until none are left."""
        while not self._closed and (job := self._next_job()) is not None:
            self._running = job
            try:
                await self._run(job)
            except Exception:
                # Most likely the socket closed under a send. Log it and carry
                # on; the gateway's cleanup will close() this runner.
                log.exception("session %s: transcript send failed", self._session_id)
            finally:
                self._running = None

    async def _run(self, job: _Job) -> None:
        started = self._telemetry.record(ASR_START, job.turn_id).at
        inner = asyncio.create_task(self._recognizer.transcribe(job.pcm, job.cancel))
        try:
            # asyncio.wait with a timeout does NOT cancel `inner` when time is
            # up, unlike asyncio.timeout. That is the point: we report the
            # failure now, but keep this session's slot until the thread is
            # really free (the second wait below).
            await asyncio.wait({inner}, timeout=self._timeout_s)
            if not inner.done():
                await self._fail(job, f"timed out after {self._timeout_s:.1f} s")
                self._abandon(job)
                await asyncio.wait({inner})
                return
            result = inner.result()
        except AsrError as exc:
            await self._fail(job, str(exc))
            return
        except asyncio.CancelledError:
            inner.cancel()  # teardown: stop waiting for the recogniser too
            raise
        await self._emit(job, result, started)

    async def _emit(self, job: _Job, result: Transcript | None, started: float) -> None:
        # The abandon check is IMMEDIATELY before the send, with no await in
        # between: a barge-in handled before this line wins; after it, the
        # message is already on its way.
        if job.abandoned or self._closed or result is None:
            log.info(
                "session %s: discarded abandoned %s for turn %s",
                self._session_id,
                "final" if job.final else "partial",
                job.turn_id,
            )
            return
        decode_ms = (perf_counter() - started) * 1000
        if not job.final:
            await self._send(transcript_partial(job.turn_id, result.text))
            self._telemetry.record(ASR_PARTIAL, job.turn_id)
            log.info(
                "session %s: transcript.partial turn %s (decode %.0f ms): %r",
                self._session_id,
                job.turn_id,
                decode_ms,
                result.text,
            )
            return
        await self._send(
            transcript_final(job.turn_id, result.text, job.duration_ms, result.language)
        )
        span = self._telemetry.record(ASR_FINAL, job.turn_id)
        assert job.ended_at is not None  # always set for finals
        log.info(
            "session %s: transcript.final turn %s (turn_ended->final %.0f ms, "
            "decode %.0f ms): %r",
            self._session_id,
            job.turn_id,
            (span.at - job.ended_at) * 1000,
            decode_ms,
            result.text,
        )

    async def _fail(self, job: _Job, reason: str) -> None:
        """A partial failing is only logged; a final failing tells the browser."""
        log.warning(
            "session %s: %s for turn %s failed: %s",
            self._session_id,
            "final" if job.final else "partial",
            job.turn_id,
            reason,
        )
        # Nobody is waiting for an abandoned turn's transcript, so its failure
        # is not news to the browser.
        if job.final and not job.abandoned and not self._closed:
            await self._send(
                error(ErrorCode.ASR_FAILED, f"transcription failed: {reason}")
            )
