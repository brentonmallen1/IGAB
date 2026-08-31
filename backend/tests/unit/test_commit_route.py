"""The commit lands before the response does.

These tests exist because hardware hides this defect. On a developer SSD the
commit finishes before the browser can blink; on self-hosted storage with a
real imported history it does not, and the same code reports "changes don't
show up until I reload". So the property is asserted on *ordering*, with a
fake session and a spy on the ASGI send channel — no database, no sleep, no
dependence on how fast anything is.
"""

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from httpx import ASGITransport, AsyncClient

from igab.api.route import CommitRoute
from igab.db.session import get_session


class RecordingSession:
    """Records commit/rollback against a shared timeline."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def commit(self) -> None:
        self.log.append("commit")

    async def rollback(self) -> None:
        self.log.append("rollback")


def build_app(log: list[str]) -> FastAPI:
    router = APIRouter(route_class=CommitRoute)

    async def session_override(request: Request):
        session = RecordingSession(log)
        request.state.session = session
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # Every route takes the session the way the real ones do — indirectly,
    # through the same dependency, so the override under test is the override
    # the app uses.
    @router.post("/write")
    async def write(session=Depends(get_session)) -> dict[str, str]:
        return {"ok": "yes"}

    @router.post("/refuse")
    async def refuse(session=Depends(get_session)) -> Response:
        return Response(status_code=409)

    @router.post("/boom")
    async def boom(session=Depends(get_session)) -> dict[str, str]:
        raise HTTPException(status_code=400, detail="no")

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = session_override

    # The spy: wrap the app so every ASGI message the route sends is stamped
    # onto the same timeline the session writes to.
    inner = app.router

    async def spy(scope, receive, send):
        async def traced(message):
            log.append(message["type"])
            await send(message)

        await inner(scope, receive, traced)

    app.router = spy  # type: ignore[assignment]
    return app


async def call(app: FastAPI, path: str) -> int:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return (await c.post(path)).status_code


async def test_the_commit_lands_before_the_response_starts():
    """The whole finding, in one assertion.

    Before the fix this fails on every machine: `get_session`'s teardown runs
    on FastAPI's request exit stack, which closes *after*
    `await response(scope, receive, send)`, so "commit" lands after
    "http.response.start" and a refetch on another pooled connection reads a
    snapshot that predates it.
    """
    log: list[str] = []
    assert await call(build_app(log), "/write") == 200

    assert "commit" in log, log
    assert "http.response.start" in log, log
    assert log.index("commit") < log.index("http.response.start"), log


async def test_a_failed_request_rolls_back_and_never_commits():
    log: list[str] = []
    assert await call(build_app(log), "/boom") == 400

    assert "rollback" in log, log
    assert "commit" not in log, log


async def test_a_handler_returning_an_error_status_does_not_commit():
    """A handler that answers 4xx has decided nothing should persist.

    The teardown commit still runs (nothing is dirty, so it is a no-op), but
    `CommitRoute` must not be the thing that makes a refusal durable — so no
    commit precedes the response.
    """
    log: list[str] = []
    assert await call(build_app(log), "/refuse") == 409

    start = log.index("http.response.start")
    assert "commit" not in log[:start], log


def test_every_v1_route_commits_before_it_answers():
    """The mechanism, not a comment asking router #29 to remember.

    `include_router` passes `route_class_override=type(route)`, so setting a
    route class on the aggregating router does NOT reach the routers it
    includes. Each one has to declare it, and this is what notices when one
    does not.
    """
    from fastapi.routing import APIRoute

    from igab.main import app

    v1 = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1")]
    assert v1, "no v1 routes found — this test would pass vacuously"

    missing = sorted(r.path for r in v1 if not isinstance(r, CommitRoute))
    assert not missing, f"routes that answer before they commit: {missing}"


@pytest.mark.parametrize("path,expected", [("/write", 200), ("/refuse", 409)])
async def test_the_route_still_returns_what_the_handler_returned(path, expected):
    assert await call(build_app([]), path) == expected
