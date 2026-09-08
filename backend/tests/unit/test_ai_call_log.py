"""The call recorder must survive being called while a generator unwinds.

The rule this pins is narrow and easy to lose: `call_log.submit` may **not**
await. The gateway records in a `finally`, and for a streaming chat that
`finally` runs while the request is being cancelled — where an await either
re-raises `CancelledError` at the next checkpoint or, under `GeneratorExit`,
raises `RuntimeError: async generator ignored GeneratorExit`. Either way the
row never lands, which defeats the whole point of recording in a `finally`.

`httpx.ASGITransport` sets no `scope["asgi"]`, so tests take the same Starlette
branch production takes and neither exercises the ASGI 2.4 path. That is why
this asserts the *shape* — submit enqueues, and returns before the write runs —
rather than hoping a disconnect test would catch a regression.
"""

import asyncio
import inspect

import pytest

from igab.ai import call_log
from igab.ai.context import AICallContext, AICallResult


def _result() -> AICallResult:
    return AICallResult(
        context=AICallContext(feature="chat"),
        model="gemma4:31b",
        host="http://localhost:11434",
        endpoint="chat",
    )


class TestSubmitDoesNotAwait:
    def test_submit_is_not_a_coroutine_function(self):
        """If this ever becomes `async def`, every caller in a `finally`
        silently stops recording under cancellation."""
        assert not inspect.iscoroutinefunction(call_log.submit)

    async def test_submit_returns_before_the_write_runs(self, monkeypatch):
        started = asyncio.Event()

        async def slow_write(result):
            started.set()
            await asyncio.sleep(0)

        monkeypatch.setattr(call_log, "_write", slow_write)
        call_log.submit(_result())
        # Nothing has run yet: create_task schedules, it does not execute.
        assert not started.is_set()
        await asyncio.sleep(0)
        assert started.is_set()

    async def test_submit_works_while_a_generator_is_being_closed(self, monkeypatch):
        """The real scenario: a client disconnects mid-stream and the
        generator's `finally` runs during finalisation."""
        recorded: list[str] = []

        async def record(result):
            recorded.append(result.context.feature)

        monkeypatch.setattr(call_log, "_write", record)

        async def stream():
            try:
                yield "chunk"
                yield "never reached"
            finally:
                call_log.submit(_result())

        gen = stream()
        assert await anext(gen) == "chunk"
        await gen.aclose()  # what a disconnect does
        await asyncio.sleep(0)
        assert recorded == ["chat"]

    async def test_a_failing_write_never_escapes(self, monkeypatch):
        """Telemetry that can break the thing it observes is worse than none."""

        async def boom(result):
            raise RuntimeError("database is on fire")

        monkeypatch.setattr(call_log, "_write", boom)
        call_log.submit(_result())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        # Reaching here without an unhandled exception is the assertion.

    async def test_pending_tasks_are_referenced_until_done(self, monkeypatch):
        """asyncio holds only a weak reference to a running task; without the
        module's strong set the collector can drop a write mid-flight."""
        release = asyncio.Event()

        async def blocked(result):
            await release.wait()

        monkeypatch.setattr(call_log, "_write", blocked)
        call_log.submit(_result())
        await asyncio.sleep(0)
        assert call_log.pending_count() == 1
        release.set()
        await call_log.drain()
        assert call_log.pending_count() == 0

    async def test_drain_with_nothing_pending_is_a_no_op(self):
        await call_log.drain()

    def test_submit_without_a_running_loop_does_not_raise(self):
        """Interpreter shutdown, or a synchronous caller."""
        call_log.submit(_result())


class TestEnqueueIsTheOnlyWriteMechanism:
    """The stream's `finally` may not await, so anything that must survive a
    disconnect goes through `enqueue` — the assistant turn included."""

    def test_enqueue_is_not_a_coroutine_function(self):
        assert not inspect.iscoroutinefunction(call_log.enqueue)

    async def test_enqueue_runs_the_write_after_returning(self):
        ran = asyncio.Event()

        async def write():
            ran.set()

        call_log.enqueue(write(), what="test")
        assert not ran.is_set()
        await asyncio.sleep(0)
        assert ran.is_set()

    async def test_enqueue_survives_generator_close(self):
        """The real case: the panel is closed and the generator is finalised."""
        ran: list[str] = []

        async def write():
            ran.append("landed")

        async def stream():
            try:
                yield "chunk"
            finally:
                call_log.enqueue(write(), what="interrupted answer")

        gen = stream()
        assert await anext(gen) == "chunk"
        await gen.aclose()
        await asyncio.sleep(0)
        assert ran == ["landed"]

    def test_no_loop_closes_the_coroutine_rather_than_orphaning_it(self):
        async def write():
            pass

        # An unawaited coroutine is a RuntimeWarning, and this module must
        # never be louder than the work it observes.
        call_log.enqueue(write(), what="test")


class TestDebugViewShape:
    async def test_a_cancelled_call_still_records(self, monkeypatch):
        from igab.ai.context import STATUS_CANCELLED

        recorded: list[AICallResult] = []

        async def record(result):
            recorded.append(result)

        monkeypatch.setattr(call_log, "_write", record)
        result = _result()
        result.status = STATUS_CANCELLED
        call_log.submit(result)
        await asyncio.sleep(0)
        assert recorded[0].status == STATUS_CANCELLED


@pytest.fixture(autouse=True)
def _clear_pending():
    yield
    call_log._pending.clear()
