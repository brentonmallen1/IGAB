"""What a model call is, and what came back — as data, with no I/O.

Split out from the gateway so the shape of a recorded call can be built and
asserted without a database or an Ollama server. `AICallResult` is what the
gateway hands the recorder; every field it carries is a field the activity log
can show.

`ToolInvocation` is deliberately fat. A small local model picks the wrong tool
and the wrong arguments, and a wrong argument produces a confident wrong
number, so the record keeps **both** what the model asked for and what actually
ran. The difference between `arguments` and `resolved_arguments` is where a bad
model is visible; collapsing them would hide the only evidence.
"""

from dataclasses import dataclass, field
from typing import Any

#: Thinking transcripts and tool payloads can be enormous. This is the same cap
#: `AIService` applied to its own debug capture — one number, not two.
RESPONSE_KEEP_CHARS = 100_000

#: Call outcomes. `cancelled` exists because the user closing the chat panel
#: mid-answer is a normal event that must still be recorded, not an error.
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


def clip(value: str | None, limit: int = RESPONSE_KEEP_CHARS) -> str | None:
    """Truncate for storage. None stays None so "absent" and "empty" differ."""
    if value is None:
        return None
    return value[:limit]


@dataclass(frozen=True)
class AICallContext:
    """Why this call is happening, and what it belongs to.

    `feature` is required and validated against the registry — a call nobody
    can name is a call nobody can explain in the activity log.
    """

    feature: str
    budget_id: Any | None = None
    conversation_id: Any | None = None
    message_id: Any | None = None
    job_id: Any | None = None
    #: Which model round trip this is within one user turn, 0-based. A tool
    #: loop produces several rows sharing a message_id; the round is what
    #: makes the sequence readable.
    round: int = 0


@dataclass
class ToolInvocation:
    """One tool call the model asked for, and what running it did."""

    name: str
    #: Exactly what the model emitted, before validation or coercion.
    arguments: dict[str, Any] = field(default_factory=dict)
    #: What actually ran, after defaults, coercion and clamping.
    resolved_arguments: dict[str, Any] | None = None
    #: The service method the handler delegated to — proof it went through the
    #: shared implementation rather than inventing its own query.
    delegates_to: str | None = None
    result: Any = None
    row_count: int | None = None
    truncated: bool = False
    duration_ms: int | None = None
    error: str | None = None
    #: Compiled SQL the handler issued, when SQL capture is switched on.
    sql: list[str] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        """The stored shape. Kept explicit so the log format does not drift
        with the dataclass."""
        return {
            "name": self.name,
            "arguments": self.arguments,
            "resolved_arguments": self.resolved_arguments,
            "delegates_to": self.delegates_to,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "sql": self.sql,
        }


@dataclass
class AICallResult:
    """Everything worth knowing about one model round trip."""

    context: AICallContext
    model: str
    host: str
    endpoint: str  # "generate" | "chat"
    status: str = STATUS_OK
    error: str | None = None
    duration_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    thinking_enabled: bool = False
    system: str | None = None
    #: The messages exactly as sent — a list even for /api/generate, so the
    #: activity log renders one shape.
    messages: list[dict[str, Any]] = field(default_factory=list)
    response: str | None = None
    thinking: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_invocations: list[ToolInvocation] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        """The heavy half of the record, clipped for storage."""
        return {
            "system": clip(self.system),
            "messages": self.messages,
            "response": clip(self.response),
            "thinking": clip(self.thinking),
            "options": self.options,
            "tools": self.tools,
            "tool_trace": [t.as_record() for t in self.tool_invocations],
        }


def debug_view(result: "AICallResult | None") -> dict:
    """What a job row shows about the model call that produced it.

    The activity page has always shown the prompt, the raw response and the
    thinking beside a receipt job, and a failed extraction is unanswerable
    without them. This builds that view from the recorded call, so the page and
    the call log cannot describe the same call differently.
    """
    if result is None:
        return {}
    view: dict = {
        "request": {
            "prompt": result.messages[0]["content"] if result.messages else None,
            "system": result.system,
            "model": result.model,
        }
    }
    if result.response is not None:
        view["raw_response"] = clip(result.response)
    if result.thinking:
        view["thinking"] = clip(result.thinking)
    return view
