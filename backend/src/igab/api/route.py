"""The one place a request's transaction is made durable.

**Why this is not `get_session`'s exit code.** The session dependency commits
after its `yield`, and FastAPI registers a `yield` dependency's teardown on
`scope["fastapi_inner_astack"]`. Read `fastapi.routing.request_response` and
look at what that stack encloses:

    async with AsyncExitStack() as request_stack:   # yield deps live here
        scope["fastapi_inner_astack"] = request_stack
        async with AsyncExitStack() as function_stack:
            response = await f(request)
        await response(scope, receive, send)        # <- client has its answer
    # request_stack closes HERE -> session.commit() runs now

The response is on the wire *before* `COMMIT` is issued — on every mutating
request the app serves, not sometimes. The client then invalidates, refetches,
takes a different pooled connection, and Postgres answers it at once from a
snapshot that predates the commit: readers never block on writers, so an
uncommitted delete does not make the reader wait, it makes the reader wrong.
A blocking read would have been correct and slow. This is instant and stale.

The window is exactly the duration of the commit — WAL write plus `fsync`,
scaling with how much the transaction touched. On a developer SSD with a small
dataset it closes before the browser can blink and the bug is invisible; on
self-hosted storage with a real imported history it does not, and the symptom
is "changes don't show up until I reload". Deleting a budget is the largest
single transaction this application issues, which is why it is the case users
report. **Any attempt to reproduce this with a bigger click on fast local
storage will succeed at reproducing nothing** — the reproduction is an
artificial delay on the commit (see `tests/unit/test_commit_route.py`).

`CommitRoute` runs its commit inside `f(request)`, so it lands before
`await response(...)`. The endpoint has already returned a fully serialized
`Response` by then, so committing afterwards cannot disturb serialization.

The dependency keeps its exit code for **rollback**, which is the right place
to guarantee a failed request leaves nothing open. It is the wrong place to
make a change durable, because by then the client has been told it already is.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute


class CommitRoute(APIRoute):
    """An `APIRoute` that commits its session before the response is sent.

    Every router under `api/v1` is built with `route_class=CommitRoute`, and
    `test_every_v1_route_commits_before_it_answers` fails if one is not — a
    comment asking the next router to remember would not be a mechanism.
    `include_router` passes `route_class_override=type(route)`, so a parent
    router's class does NOT reach an included one; it has to be set on each.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await original(request)
            # An endpoint that raised never gets here: the exception unwinds
            # past us to `wrap_app_handling_exceptions`, which sits outside
            # the exit stack, so the dependency's `except` rolls back first.
            # A handler that *returns* an error status is the case this guard
            # covers — it has decided nothing should persist.
            session = getattr(request.state, "session", None)
            if session is not None and response.status_code < 400:
                await session.commit()
            return response

        return handler
