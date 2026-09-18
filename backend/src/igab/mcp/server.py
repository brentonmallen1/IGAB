"""The read-only MCP endpoint.

An assistant asking "what did we spend on groceries in August" should not need
a screenshot. This exposes the answers the app already computes, over a
standard protocol, to whatever the person uses — Claude, a local model through
an MCP-speaking client, anything that can set a header.

**It is a transport, not a second implementation.** Every tool here is one the
AI chat already has: `ai/tools/registry.py` holds twelve read-only specs, each
a thin adapter over a service, and a unit test greps that package for SQL to
keep it that way. Nothing in this module computes a figure. A tool that
disagreed with the app would be worse than no tool, and the way to guarantee
it cannot is to have no second copy to disagree with.

**Read-only is a property of the tool set, not a promise in a docstring.**
There is no write tool to call, and a key's scope column says `read` so that
adding one later is a deliberate change rather than an omission.

**The budget is never a tool argument.** It comes from the key. That is the
registry's own invariant — a model that could name a budget could name one it
was not given.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import mcp.types as types
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings

from igab.ai.tools import executor
from igab.ai.tools.context import build_tool_context
from igab.ai.tools.registry import BY_NAME, TOOLS
from igab.services.api_key_service import ApiKeyPrincipal, authenticate

logger = logging.getLogger(__name__)

SERVER_NAME = "igab"

#: Where a multi-budget key says which budget it means. Added to each tool's
#: schema only when the key actually spans several, so the common case — one
#: key, one budget — asks the assistant for nothing.
BUDGET_ARG = "budget"

#: Required by AuthSettings, and inert here: no OAuth endpoints are served
#: because no `auth_server_provider` is passed. The SDK's bearer middleware
#: is the only part we want, and this is its price of admission.
_AUTH = AuthSettings(
    issuer_url="https://igab.local",
    resource_server_url="https://igab.local",
    # False because there is no audience to check: a key is not a JWT issued
    # for a named resource, it is a secret this server stored the hash of.
    # Leaving it unset would default to True in a later SDK and refuse every
    # key we issue.
    validate_token_resource=False,
)


class ApiKeyVerifier(TokenVerifier):
    """Turns a bearer header into a principal, or refuses it.

    Opens its own session: an MCP request arrives outside the FastAPI
    dependency graph, so there is no request-scoped session to borrow.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        from igab.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            principal = await authenticate(session, token)
            if principal is None:
                return None
            # The stamp `authenticate` set is worth keeping, and this is the
            # only place that can commit it.
            await session.commit()

        return AccessToken(
            token=token,
            client_id=str(principal.key_id),
            scopes=["read"],
            subject=str(principal.user_id),
            claims={
                "budget_ids": [str(b) for b in principal.budget_ids],
                "key_name": principal.name,
            },
        )


def _principal() -> ApiKeyPrincipal | None:
    """The key behind the call in flight, rebuilt from its verified claims.

    Read from the token rather than the database: it was checked moments ago
    on this same request, and a second lookup per tool call would be a query
    that can only ever agree with the first.
    """
    token = get_access_token()
    if token is None:
        return None
    claims: dict[str, Any] = token.claims or {}
    try:
        budget_ids = tuple(uuid.UUID(b) for b in claims.get("budget_ids", []))
        key_id = uuid.UUID(token.client_id or "")
        user_id = uuid.UUID(token.subject or "")
    except ValueError:
        return None
    return ApiKeyPrincipal(
        key_id=key_id,
        user_id=user_id,
        name=str(claims.get("key_name") or "API key"),
        budget_ids=budget_ids,
    )


def _tool_schema(spec, multi_budget: bool) -> dict:
    """The registry's own JSON Schema, plus a budget argument when needed."""
    schema = dict(spec.parameters)
    if not multi_budget:
        return schema
    properties = dict(schema.get("properties") or {})
    properties[BUDGET_ARG] = {
        "type": "string",
        "description": (
            "Which budget to read. Omit to use the only one this key can reach, "
            "or call list_budgets to see the names."
        ),
    }
    return {**schema, "properties": properties}


def _list_budgets_tool() -> types.Tool:
    return types.Tool(
        name="list_budgets",
        description=(
            "The budgets this key can read, by name and id. Call this first when a "
            "question could be about more than one."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


async def _resolve_budget(
    session, principal: ApiKeyPrincipal, arguments: dict
) -> tuple[uuid.UUID | None, str | None]:
    """Which budget this call is for, and why not.

    A single-budget key never has to say. A key that spans several must, and
    a name it does not cover is 'not found' rather than 'not allowed': a
    refusal that distinguishes them tells the caller which budgets exist.
    """
    named = (arguments or {}).pop(BUDGET_ARG, None)
    if not principal.budget_ids:
        return None, "This key is not scoped to any budget."
    if not named:
        if len(principal.budget_ids) == 1:
            return principal.budget_ids[0], None
        return None, (
            "This key can read several budgets — pass `budget` with the name, or call list_budgets."
        )

    from sqlalchemy import select

    from igab.db.models import Budget

    rows = (
        (await session.execute(select(Budget).where(Budget.id.in_(principal.budget_ids))))
        .scalars()
        .all()
    )
    wanted = str(named).strip().lower()
    for budget in rows:
        if budget.name.strip().lower() == wanted or str(budget.id) == str(named):
            return budget.id, None
    return None, f"No budget named {named!r} is readable with this key."


def build_server() -> Server:
    """The MCP server, wired to the tools the app already has.

    Handlers are constructor arguments rather than decorators: that is the
    shape the 2.x low-level server takes, and the low level is what lets a
    tool carry the registry's own JSON Schema. The high-level server derives
    schemas from Python signatures, which would mean restating every tool's
    arguments here — a second definition of the thing this module exists not
    to duplicate.
    """
    return Server(
        SERVER_NAME,
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


async def _on_list_tools(_ctx, _params) -> types.ListToolsResult:
    principal = _principal()
    multi = bool(principal and len(principal.budget_ids) > 1)
    tools = [
        types.Tool(
            name=spec.name,
            description=spec.description,
            input_schema=_tool_schema(spec, multi),
        )
        for spec in TOOLS
    ]
    # Last: it is about the connection rather than about money, and an
    # assistant reads the list in order.
    tools.append(_list_budgets_tool())
    return types.ListToolsResult(tools=tools)


def _text(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)])


async def _on_call_tool(_ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    from igab.db.session import AsyncSessionLocal

    principal = _principal()
    if principal is None:
        return _text("This key is no longer valid.")

    name = params.name
    async with AsyncSessionLocal() as session:
        if name == "list_budgets":
            return _text(await _budgets_text(session, principal))

        if name not in BY_NAME:
            return _text(f"No tool named {name!r}. Available: {', '.join(sorted(BY_NAME))}.")

        args = dict(params.arguments or {})
        budget_id, refusal = await _resolve_budget(session, principal, args)
        if budget_id is None:
            return _text(refusal or "Unavailable.")

        ctx = await build_tool_context(session, budget_id, datetime.now(tz=UTC).date())
        invocation = await executor.run(ctx, name, args)

    # The executor never raises — a failed tool reports itself as a result,
    # which is what lets an assistant say what went wrong instead of the
    # connection dropping.
    if invocation.error:
        logger.info("mcp: tool %s reported: %s", name, invocation.error)
    return _text(json.dumps(invocation.result, default=str))


async def _budgets_text(session, principal: ApiKeyPrincipal) -> str:
    from sqlalchemy import select

    from igab.db.models import Budget

    rows = (
        (await session.execute(select(Budget).where(Budget.id.in_(principal.budget_ids))))
        .scalars()
        .all()
    )
    if not rows:
        return "This key is not scoped to any budget."
    return "\n".join(f"{b.name} ({b.id})" for b in rows)


#: The transport's own DNS-rebinding guard is a Host/Origin allowlist, and it
#: is aimed at a local MCP server a browser could be tricked into POSTing to.
#: That threat does not reach this one: every request must carry a secret
#: bearer key, which a rebinding attacker cannot read or replay, and no CORS
#: headers are served so a browser could not read a response anyway.
#:
#: An allowlist here would instead be a list of every hostname any
#: self-hosted install might answer on — a Tailscale name, a LAN address, a
#: domain behind someone's own proxy — which is not knowable from here and
#: would fail closed on a working setup. The key is the gate.
_TRANSPORT_SECURITY = TransportSecuritySettings(enable_dns_rebinding_protection=False)


def mcp_app():
    """The ASGI app to mount. Stateless: every request carries its own key,
    and nothing about a budget question needs a session to persist."""
    return build_server().streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        auth=_AUTH,
        token_verifier=ApiKeyVerifier(),
        transport_security=_TRANSPORT_SECURITY,
    )
