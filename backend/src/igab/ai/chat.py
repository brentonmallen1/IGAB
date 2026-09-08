"""The chat turn: ask the model, run what it asks for, ask again, answer.

Emits typed events rather than a token stream of prose. LoreStudio, which this
borrows from, marks a model's reasoning with `<|channel>thought` sentinels
inside the text and has the browser regex them back out; that cannot carry tool
state, breaks if a model ever emits the literal text, and duplicates the parse
between streaming and final render. Typed events cost nothing and carry
everything.

The loop is bounded three ways — turns, total tool calls, and a wall clock —
because a small local model will happily call the same tool forever. At the
bound it gets one more turn with the tools removed, so it must answer in prose:
a stream that simply stops reads to the user as a crash.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from igab.ai.context import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    AICallContext,
    AICallResult,
    ToolInvocation,
)
from igab.ai.gateway import AIGateway
from igab.ai.tools import executor
from igab.ai.tools.context import ToolContext
from igab.ai.tools.registry import ollama_schema
from igab.integrations.ollama.client import OllamaClient


@dataclass
class ChatEvent:
    """One thing worth telling the browser about."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatOutcome:
    """What the turn produced, for persisting once it is over."""

    content: str = ""
    thinking: str | None = None
    tool_invocations: list[ToolInvocation] = field(default_factory=list)
    call_results: list[AICallResult] = field(default_factory=list)
    error: str | None = None


async def run_turn(
    *,
    gateway: AIGateway,
    client: OllamaClient,
    tool_ctx: ToolContext,
    messages: list[dict],
    context: AICallContext,
    use_tools: bool,
    think: bool | None = None,
    options: dict | None = None,
    timeout: float = 120.0,
    outcome: ChatOutcome,
) -> AsyncIterator[ChatEvent]:
    """Drive one user message to an answer, yielding events as it goes.

    `outcome` is filled in as the turn runs so the caller can persist the
    result even when the stream is cut short.
    """
    working = list(messages)
    seen: dict[str, Any] = {}
    started = time.monotonic()
    tools = ollama_schema() if use_tools else None

    for turn in range(executor.MAX_TURNS):
        last_turn = turn == executor.MAX_TURNS - 1
        over_budget = (
            len(outcome.tool_invocations) >= executor.MAX_TOOL_CALLS
            or (time.monotonic() - started) > timeout
        )
        # The final turn drops the tools, so the model has no choice but to
        # answer. Stopping instead would end the stream with no assistant text.
        turn_tools = None if (last_turn or over_budget) else tools

        call = AICallContext(
            feature=context.feature,
            budget_id=context.budget_id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            round=turn,
        )
        result = AICallResult(
            context=call,
            model=client.model,
            host=client.host,
            endpoint="chat",
            # Lifted out of the message list as well as left in it: the
            # transparency view has a section for the system prompt, and it
            # reads this field rather than digging through the transcript.
            system=next(
                (m.get("content") for m in working if m.get("role") == "system"),
                None,
            ),
            messages=list(working),
            options=dict(options or {}),
            tools=turn_tools or [],
            thinking_enabled=bool(think),
        )
        gateway.last_result = result
        call_started = time.monotonic()
        try:
            body = await client.chat(
                working,
                tools=turn_tools,
                think=think,
                options=options,
                timeout=timeout,
            )
        except asyncio.CancelledError:
            # The user closed the panel. Record it as what it is and let the
            # cancellation continue — swallowing it would both fabricate an
            # error and stop the request unwinding.
            result.status = STATUS_CANCELLED
            result.error = "cancelled"
            result.duration_ms = int((time.monotonic() - call_started) * 1000)
            outcome.call_results.append(result)
            raise
        except Exception as exc:
            result.status = STATUS_ERROR
            result.error = f"{type(exc).__name__}: {exc}"[:2000]
            result.duration_ms = int((time.monotonic() - call_started) * 1000)
            outcome.call_results.append(result)
            outcome.error = result.error
            yield ChatEvent("error", {"message": _friendly(exc)})
            return

        result.duration_ms = int((time.monotonic() - call_started) * 1000)
        message = body.get("message") or {}
        text = _absorb(result, message, client)

        if result.thinking:
            outcome.thinking = result.thinking
            yield ChatEvent("thinking", {"delta": result.thinking})

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            outcome.content = text
            outcome.call_results.append(result)
            if text:
                yield ChatEvent("token", {"delta": text})
            yield ChatEvent(
                "usage",
                {
                    "prompt_tokens": result.prompt_tokens,
                    "eval_tokens": result.completion_tokens,
                },
            )
            return

        # The model asked for something. Keep its turn in the history exactly
        # as it came back, or the next round loses what it was doing.
        working.append({"role": "assistant", "content": text, "tool_calls": tool_calls})

        for raw in tool_calls:
            if _out_of_budget(outcome, started, timeout, working):
                break
            async for event in _dispatch(raw, tool_ctx, seen, working, outcome, result):
                yield event

        outcome.call_results.append(result)

    # Every turn used and the model never stopped asking for tools.
    outcome.content = outcome.content or (
        "I looked several things up but could not settle on an answer. "
        "Try asking about one month or one envelope at a time."
    )
    yield ChatEvent("token", {"delta": outcome.content})


def _absorb(result: AICallResult, message: dict, client: OllamaClient) -> str:
    """Copy what came back onto the record, and return the prose.

    Thinking and token counts arrive on the client's `last_meta` rather than in
    the message body, so both are read here in one place.
    """
    text = (message.get("content") or "").strip()
    meta = client.last_meta or {}
    thinking = meta.get("thinking")
    result.response = text
    result.thinking = thinking if isinstance(thinking, str) else None
    if isinstance(meta.get("prompt_eval_count"), int):
        result.prompt_tokens = meta["prompt_eval_count"]
    if isinstance(meta.get("eval_count"), int):
        result.completion_tokens = meta["eval_count"]
    result.status = STATUS_OK
    return text


def _out_of_budget(
    outcome: ChatOutcome,
    started: float,
    timeout: float,
    working: list[dict],
) -> bool:
    """Whether this turn has spent its allowance of lookups or its clock.

    Checked before every call rather than between turns: a model can ask for a
    dozen tools in one message, and reading the cap only between turns let all
    of them run — `guide_checkup`, which fans out across the whole budget,
    included.

    Says so in the transcript rather than going quiet, so the model answers
    with what it has instead of waiting for a result that is not coming.
    """
    if len(outcome.tool_invocations) >= executor.MAX_TOOL_CALLS:
        working.append(
            {
                "role": "tool",
                "content": (
                    '{"error": "No more lookups are allowed for this question. '
                    'Answer with what you already have."}'
                ),
                "tool_name": "budget",
            }
        )
        return True
    return (time.monotonic() - started) > timeout


async def _dispatch(
    raw: dict,
    tool_ctx: ToolContext,
    seen: dict[str, Any],
    working: list[dict],
    outcome: ChatOutcome,
    result: AICallResult,
) -> AsyncIterator[ChatEvent]:
    """Run one tool call the model asked for, and say so twice.

    Once before, so the panel can show what it reached for while it runs, and
    once after with what came back — including the arguments as the model wrote
    them beside the ones that actually ran. The difference between those two is
    where a small model's mistake is visible.
    """
    function = raw.get("function") or {}
    name = str(function.get("name") or "")
    arguments = function.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    yield ChatEvent("tool_call", {"name": name, "arguments": arguments})

    key = executor.dedupe_key(name, arguments)
    if key in seen:
        # The cheapest loop a small model falls into. Answer from cache and say
        # so, rather than pretending it did not ask.
        invocation = ToolInvocation(
            name=name,
            arguments=arguments,
            resolved_arguments=arguments,
            result={**seen[key], "note": "You already asked this. Here is the same answer."},
        )
    else:
        invocation = await executor.run(tool_ctx, name, arguments)
        if invocation.error is None and isinstance(invocation.result, dict):
            seen[key] = invocation.result

    outcome.tool_invocations.append(invocation)
    result.tool_invocations.append(invocation)
    working.append({"role": "tool", "content": _as_text(invocation.result), "tool_name": name})
    yield ChatEvent(
        "tool_result",
        {
            "name": name,
            "arguments": invocation.arguments,
            "resolved_arguments": invocation.resolved_arguments,
            "delegates_to": invocation.delegates_to,
            "rows": invocation.row_count,
            "truncated": invocation.truncated,
            "duration_ms": invocation.duration_ms,
            "error": invocation.error,
        },
    )


def _as_text(result: Any) -> str:
    import json

    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _friendly(exc: BaseException) -> str:
    """What the user reads when a call fails.

    The class name, not the repr: a connection error's repr carries the host
    and port, which belongs in the log rather than in a chat bubble.
    """
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return "The model took too long to answer. It may be loading — try again."
    if isinstance(exc, httpx.ConnectError):
        return "Could not reach Ollama. Check the AI settings."
    return "Something went wrong talking to the model."
