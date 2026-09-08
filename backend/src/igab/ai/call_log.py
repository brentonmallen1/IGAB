"""Recording a model call, from places where you cannot await.

**Why this is not just `await session.commit()`.** The gateway records in a
`finally`, so that a call which errored or was cancelled is recorded too — a
user closing the chat panel mid-answer is a normal event, and "what did it do
before I stopped it" is exactly the question the log exists to answer.

But a streaming response's generator is finalized during cancellation. On a
client disconnect Starlette either collapses the cancel scope around it or
finalizes it under `GeneratorExit`, and in both cases **an `await` in that
`finally` does not complete**: the first re-raises `CancelledError` at the next
checkpoint, the second raises `RuntimeError: async generator ignored
GeneratorExit`. So the one shape that works is to *enqueue* — `create_task`
schedules on the loop and returns synchronously, outside the cancel scope that
is unwinding.

`BackgroundTask` is not a substitute: Starlette skips `self.background()` when
a disconnect raises out of `stream_response`, which is the branch it takes once
uvicorn advertises ASGI 2.4 (its websocket protocols already do).

The write takes its own session for the same reason the AI worker does. The
request's session belongs to a response that has already been sent, and
`CommitRoute` has already committed it.
"""

import asyncio
import logging
from collections.abc import Coroutine

from igab.ai.context import AICallResult
from igab.db.models import AICall, AICallPayload

logger = logging.getLogger(__name__)

#: Strong references to in-flight writes. asyncio only holds a weak reference
#: to a running task, so without this the garbage collector may drop one
#: mid-write and the row silently never lands.
_pending: set[asyncio.Task] = set()


def enqueue(coro: Coroutine, *, what: str) -> None:
    """Run a write without awaiting it. Never blocks, never raises.

    The primitive this module exists for. Safe to call from a `finally` that is
    unwinding under cancellation — `create_task` schedules on the loop and
    returns synchronously, outside the cancel scope that is collapsing.

    Anything that must survive a client disconnect goes through here: the call
    log, and the assistant turn the stream was in the middle of writing.
    """
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        # No running loop (a synchronous caller, or interpreter shutdown).
        # Close the coroutine rather than leaving it unawaited: an orphaned
        # coroutine is a RuntimeWarning, and this module must never make noise
        # louder than the work it observes.
        coro.close()
        logger.warning("ai: no event loop to write %s", what)
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def submit(result: AICallResult) -> None:
    """Queue a call record to be written."""
    enqueue(_write(result), what=f"{result.context.feature} call")


async def drain(timeout: float = 5.0) -> None:
    """Wait for queued writes, for shutdown. Never raises."""
    if not _pending:
        return
    try:
        await asyncio.wait(set(_pending), timeout=timeout)
    except Exception:
        logger.exception("ai: could not drain pending call records")


def pending_count() -> int:
    """Test-only: how many writes are in flight."""
    return len(_pending)


async def _write(result: AICallResult) -> None:
    """Persist one call. Swallows its own failures on purpose — telemetry that
    can break the thing it observes is worse than no telemetry."""
    from igab.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            call = AICall(
                budget_id=result.context.budget_id,
                feature=result.context.feature,
                model=result.model,
                host=result.host,
                endpoint=result.endpoint,
                status=result.status,
                error=result.error,
                round=result.context.round,
                duration_ms=result.duration_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                tool_call_count=len(result.tool_invocations),
                thinking_enabled=result.thinking_enabled,
                conversation_id=result.context.conversation_id,
                job_id=result.context.job_id,
            )
            session.add(call)
            await session.flush()
            payload = result.payload()
            session.add(
                AICallPayload(
                    ai_call_id=call.id,
                    request={
                        "system": payload["system"],
                        "messages": payload["messages"],
                        "options": payload["options"],
                        "tools": payload["tools"],
                    },
                    response=payload["response"],
                    thinking=payload["thinking"],
                    tool_trace=payload["tool_trace"],
                )
            )
            await session.commit()
    except Exception:
        logger.exception("ai: could not record %s call", result.context.feature)
