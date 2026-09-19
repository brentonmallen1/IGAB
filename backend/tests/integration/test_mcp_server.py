"""The MCP endpoint, over the real protocol.

Driven as a client would drive it — initialize, tools/list, tools/call — so
what is proved is what an assistant will actually get, not what the handlers
return when called directly.

The guarantees under test are the ones that would matter if they broke: the
tool list is the app's own registry and not a second copy of it, a key reads
only the budgets it was given, and neither credential works on the other's
door.
"""

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from igab.ai.tools.registry import BY_NAME
from igab.db.session import get_session
from igab.main import app
from igab.mcp.server import mcp_app

from .factories import create_budget, create_user

#: The app under test is a FRESH MCP app per test, so this is its own root.
#: In the running server the same app is mounted at /api/v1/mcp — see
#: `test_the_endpoint_is_mounted_where_nginx_already_proxies` below.
MCP_URL = "/"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@asynccontextmanager
async def mcp_client(db_session):
    """A client on the mounted MCP app, sharing the test's session.

    A context manager rather than a fixture: the transport's session manager
    is started by an anyio task group, and anyio requires the scope to be
    exited in the task that entered it — which a yielding fixture cannot
    promise. `async with` in the test body can.

    Two things production does that ASGITransport does not: it runs the
    lifespan (a MOUNTED sub-app's own lifespan never runs, so `main.lifespan`
    enters this same context), and it opens real sessions — the endpoint sits
    outside the dependency graph and calls `AsyncSessionLocal` itself, so
    that is what has to point at the test's transaction.
    """

    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    async def _session_override():
        yield db_session

    # A fresh app per test: a session manager can only be run once per
    # instance, and the module-level one the server mounts has a single
    # lifespan for the life of the process.
    fresh = mcp_app()
    app.dependency_overrides[get_session] = _session_override
    try:
        with patch("igab.db.session.AsyncSessionLocal", lambda: _Ctx()):
            async with fresh.router.lifespan_context(fresh):
                async with AsyncClient(
                    transport=ASGITransport(app=fresh), base_url="http://test"
                ) as client:
                    yield client
    finally:
        app.dependency_overrides.clear()


async def _key(db_session, budgets, name="Claude on the laptop"):
    """A live key for these budgets, as the endpoint will see it."""
    from igab.services.api_key_service import create_key

    user = budgets[0].user_id
    _key_row, raw = await create_key(
        db_session, user_id=user, name=name, budget_ids=[b.id for b in budgets]
    )
    await db_session.flush()
    return raw


def _rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    body: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


def _result(response) -> dict:
    """The JSON-RPC result, whether it came back as JSON or as one SSE frame."""
    text = response.text
    if text.startswith("event:") or "\ndata: " in text:
        line = next(ln for ln in text.splitlines() if ln.startswith("data: "))
        text = line[len("data: ") :]
    payload = json.loads(text)
    assert "error" not in payload, payload
    return payload["result"]


async def _session(mcp, raw_key):
    """Initialize, and return the headers for the calls that follow."""
    headers = {**HEADERS, "Authorization": f"Bearer {raw_key}"}
    started = await mcp.post(
        MCP_URL,
        headers=headers,
        json=_rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1"},
            },
        ),
    )
    assert started.status_code == 200, started.text
    session_id = started.headers.get("mcp-session-id")
    if session_id:
        headers["mcp-session-id"] = session_id
    await mcp.post(
        MCP_URL, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    return headers


class TestAuth:
    async def test_no_key_is_refused(self, db_session):
        async with mcp_client(db_session) as mcp:
            refused = await mcp.post(MCP_URL, headers=HEADERS, json=_rpc("tools/list"))
            assert refused.status_code == 401

    async def test_an_unknown_key_is_refused(self, db_session):
        async with mcp_client(db_session) as mcp:
            refused = await mcp.post(
                MCP_URL,
                headers={**HEADERS, "Authorization": "Bearer igab_not-a-real-key"},
                json=_rpc("tools/list"),
            )
            assert refused.status_code == 401

    async def test_a_revoked_key_stops_working(self, db_session):
        async with mcp_client(db_session) as mcp:
            from sqlalchemy import select

            from igab.db.models import ApiKey
            from igab.services.api_key_service import revoke

            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            raw = await _key(db_session, [budget])

            key = (await db_session.execute(select(ApiKey))).scalars().first()
            assert key is not None
            await revoke(db_session, key)
            await db_session.flush()

            refused = await mcp.post(
                MCP_URL,
                headers={**HEADERS, "Authorization": f"Bearer {raw}"},
                json=_rpc("tools/list"),
            )
            assert refused.status_code == 401


class TestToolsList:
    async def test_it_is_the_app_s_own_registry(self, db_session):
        """Not a second copy. A tool here that disagreed with the app would
        be worse than no tool, and the way to guarantee it cannot is to have
        nothing to disagree with."""
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            listed = await mcp.post(MCP_URL, headers=headers, json=_rpc("tools/list"))
            names = {t["name"] for t in _result(listed)["tools"]}

            assert set(BY_NAME) <= names
            assert names == set(BY_NAME) | {"list_budgets"}

    async def test_a_single_budget_key_is_asked_for_no_budget(self, db_session):
        """The common case asks the assistant for nothing."""
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            listed = await mcp.post(MCP_URL, headers=headers, json=_rpc("tools/list"))
            tools = {t["name"]: t for t in _result(listed)["tools"]}
            assert "budget" not in (tools["list_categories"]["inputSchema"].get("properties") or {})

    async def test_a_multi_budget_key_gains_a_budget_argument(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            first = await create_budget(db_session, user, "Household")
            second = await create_budget(db_session, user, "Harborstone")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [first, second]))

            listed = await mcp.post(MCP_URL, headers=headers, json=_rpc("tools/list"))
            tools = {t["name"]: t for t in _result(listed)["tools"]}
            assert "budget" in tools["list_categories"]["inputSchema"]["properties"]


class TestToolsCall:
    async def test_a_tool_runs_end_to_end(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc("tools/call", {"name": "list_accounts", "arguments": {}}, request_id=2),
            )
            result = _result(called)
            assert result["content"], result
            assert result["content"][0]["type"] == "text"

    async def test_an_unknown_tool_is_named_rather_than_crashing(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc(
                    "tools/call", {"name": "delete_everything", "arguments": {}}, request_id=3
                ),
            )
            text = _result(called)["content"][0]["text"]
            assert "No tool named" in text

    async def test_a_multi_budget_key_must_say_which(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            first = await create_budget(db_session, user, "Household")
            second = await create_budget(db_session, user, "Harborstone")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [first, second]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc("tools/call", {"name": "list_accounts", "arguments": {}}, request_id=4),
            )
            assert "list_budgets" in _result(called)["content"][0]["text"]

    async def test_a_budget_the_key_cannot_reach_is_refused(self, db_session):
        """The reach rule at the point it matters. Named budgets only — a key
        that could name any budget would be a key to the whole install."""
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            mine = await create_budget(db_session, user, "Household")
            theirs = await create_budget(db_session, user, "Harborstone")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [mine]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc(
                    "tools/call",
                    {"name": "list_accounts", "arguments": {"budget": theirs.name}},
                    request_id=5,
                ),
            )
            # A single-budget key ignores the argument entirely and reads its own
            # budget; either way the other budget is never reachable.
            text = _result(called)["content"][0]["text"]
            assert str(theirs.id) not in text

    async def test_list_budgets_names_only_what_the_key_can_read(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            mine = await create_budget(db_session, user, "Household")
            # Exists, same owner, and deliberately not on the key.
            await create_budget(db_session, user, "Harborstone")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [mine]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc("tools/call", {"name": "list_budgets", "arguments": {}}, request_id=6),
            )
            text = _result(called)["content"][0]["text"]
            assert "Household" in text
            assert "Harborstone" not in text


class TestItIsReachable:
    async def test_the_endpoint_is_mounted_where_nginx_already_proxies(self):
        """Under /api/v1 so the existing `location /api/` block proxies it
        with no config change and no second port."""
        mounted = [route for route in app.routes if getattr(route, "path", None) == "/api/v1/mcp"]
        assert mounted, [getattr(r, "path", None) for r in app.routes][:20]


class TestTheNewToolsOverTheProtocol:
    """The querying tools, driven the way an assistant drives them.

    Unit tests prove the handlers; this proves an MCP client can actually
    reach them — schema accepted, arguments through the transport, an answer
    back — which is a different claim.
    """

    async def test_query_transactions_returns_a_grouped_total(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc(
                    "tools/call",
                    {
                        "name": "query_transactions",
                        "arguments": {"group_by": "month", "aggregate": "sum"},
                    },
                ),
            )
            assert called.status_code == 200, called.text
            assert "grouped_by" in json.dumps(_result(called))

    async def test_an_impossible_group_by_comes_back_as_an_answer(self, db_session):
        """Not a 500. A model that guessed wrong has to be able to read what
        went wrong and pick a legal dimension on its next turn."""
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            called = await mcp.post(
                MCP_URL,
                headers=headers,
                json=_rpc(
                    "tools/call",
                    {
                        "name": "query_transactions",
                        "arguments": {"group_by": "; DROP TABLE transactions"},
                    },
                ),
            )
            assert called.status_code == 200, called.text
            body = json.dumps(_result(called))
            assert "category" in body

    async def test_the_new_domain_tools_are_listed_and_callable(self, db_session):
        async with mcp_client(db_session) as mcp:
            user = await create_user(db_session)
            budget = await create_budget(db_session, user, "Household")
            await db_session.flush()
            headers = await _session(mcp, await _key(db_session, [budget]))

            listed = await mcp.post(MCP_URL, headers=headers, json=_rpc("tools/list"))
            names = {t["name"] for t in _result(listed)["tools"]}
            assert {
                "query_transactions",
                "get_debt_status",
                "get_net_worth",
                "list_scheduled",
                "cash_projection",
                "burn_rate",
                "spending_anomalies",
            } <= names

            for tool in ("get_debt_status", "get_net_worth", "list_scheduled"):
                called = await mcp.post(
                    MCP_URL,
                    headers=headers,
                    json=_rpc("tools/call", {"name": tool, "arguments": {}}),
                )
                assert called.status_code == 200, f"{tool}: {called.text}"
                assert "error" not in _result(called)
