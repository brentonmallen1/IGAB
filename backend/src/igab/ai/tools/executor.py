"""Running what the model asked for, without ever letting it break the stream.

**Nothing here raises.** A bad tool name, an argument of the wrong type, a
handler that blows up — each becomes a tool *result* the model can read and
react to. The alternative is an exception escaping into a half-written SSE
stream, which reaches the user as an answer that stops mid-sentence: the worst
failure mode this feature has.

Small local models are the design constraint throughout. They call tools that
do not exist, pass `"three"` where an integer belongs, and ask the same
question twice in a loop. Each of those is handled here rather than treated as
impossible.
"""

import logging
import time
from typing import Any

from igab.ai.context import ToolInvocation
from igab.ai.tools.context import ToolContext
from igab.ai.tools.registry import BY_NAME

logger = logging.getLogger(__name__)

#: How many times the model may go round the "call a tool, look at the result"
#: loop before it must answer in prose. Four turns is three rounds of tools.
MAX_TURNS = 4

#: Total tool calls across one user message, whatever the turn count.
MAX_TOOL_CALLS = 8


def _coerce(value: Any, spec: dict) -> Any:
    """Bend an argument into the declared type, or leave it alone.

    Returns the value unchanged when it cannot be bent — the caller reports
    that as an argument error rather than guessing.
    """
    kind = spec.get("type")
    if kind == "integer" and not isinstance(value, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if kind == "number" and not isinstance(value, bool):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if kind == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    if kind == "string" and not isinstance(value, str) and value is not None:
        return str(value)
    return value


def validate(name: str, arguments: dict) -> tuple[dict, str | None]:
    """Coerce arguments against the tool's schema.

    Returns `(resolved, error)`. Unknown keys are dropped rather than rejected:
    a model that adds a plausible extra field should still get its answer.
    """
    spec = BY_NAME[name]
    properties: dict = spec.parameters.get("properties", {})
    resolved: dict = {}
    for key, value in (arguments or {}).items():
        if key not in properties:
            continue
        resolved[key] = _coerce(value, properties[key])

    missing = [k for k in spec.required if k not in resolved]
    if missing:
        return resolved, f"missing required argument(s): {', '.join(missing)}"
    return resolved, None


async def run(ctx: ToolContext, name: str, arguments: dict) -> ToolInvocation:
    """Run one tool call and return the record of it.

    The record carries both what the model asked for and what actually ran,
    because the difference between them is where a small model's mistake is
    visible.
    """
    invocation = ToolInvocation(name=name, arguments=dict(arguments or {}))
    started = time.monotonic()

    spec = BY_NAME.get(name)
    if spec is None:
        invocation.error = f"No tool named {name!r}."
        invocation.result = {
            "error": invocation.error,
            "available_tools": sorted(BY_NAME),
        }
        invocation.duration_ms = 0
        return invocation

    invocation.delegates_to = spec.delegates_to
    resolved, error = validate(name, arguments or {})
    invocation.resolved_arguments = resolved
    if error:
        invocation.error = error
        invocation.result = {"error": error, "expected": spec.parameters}
        invocation.duration_ms = int((time.monotonic() - started) * 1000)
        return invocation

    try:
        result = await spec.handler(ctx, resolved)
        invocation.result = result
        if isinstance(result, dict):
            invocation.row_count = result.get("total_rows")
            invocation.truncated = bool(result.get("truncated"))
    except Exception as exc:
        # The traceback goes to the log; the model gets one sentence, because
        # a stack trace in the context window is tokens spent on nothing.
        logger.exception("ai tool %s failed", name)
        invocation.error = f"{type(exc).__name__}: {exc}"[:500]
        invocation.result = {"error": f"{name} could not be run: {type(exc).__name__}."}

    invocation.duration_ms = int((time.monotonic() - started) * 1000)
    return invocation


def dedupe_key(name: str, arguments: dict) -> str:
    """Identity of a tool call, for spotting a model asking twice.

    Repeating a call inside one turn is the cheapest loop a small model falls
    into, and returning the cached answer with a note breaks it without
    pretending the call did not happen.
    """
    import json

    return f"{name}:{json.dumps(arguments or {}, sort_keys=True, default=str)}"
