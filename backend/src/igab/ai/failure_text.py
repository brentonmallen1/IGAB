"""What a failed scan or description says to the person reviewing it — pure.

The job's error used to be the exception's own text ("ReplyCutShort: The
model's reply was cut off before its JSON was complete", "ReadTimeout: "),
read in the review banner by someone holding a receipt. Now each failure is
three parts, shown in layers:

- **headline** — what happened, in one short sentence. Always visible: on
  the Scans row and in bold in the review banner.
- **next step** — what to do about it. In the banner, and under Details on
  the Scans row.
- **technical** — the evidence (why the call stopped, the model, thinking,
  tokens, time). Only under Details, for whoever is diagnosing it.

`settings` names the setting that helps, as the screen labels it; the page
links to System → AI under that label.
"""

from dataclasses import dataclass

import httpx

from igab.ai.context import error_text
from igab.ai.reply_json import ReplyCutShort, ReplyNotJSON
from igab.domain.exceptions import InvariantViolation
from igab.domain.receipt_checks import LOOPING_RUN
from igab.integrations.ollama.client import STOP_DEADLINE, STOP_REPETITION

AI_SETTINGS = "System → AI"
THINKING_SETTING = "System → AI → Advanced → Thinking"
TIMEOUT_SETTING = "System → AI → Advanced → Receipt scan timeout"


#: The next step of a failure the worker is about to try again.
RETRYING = "It will try again in a moment."


class NonRetryableJobError(Exception):
    """A failure no retry can fix (missing file, deleted account, no vision
    support): the job goes straight to 'error'. Raised by the worker, and
    written for people where it is raised — `message` is the headline."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        next_step: str | None = None,
        settings: str | None = None,
    ) -> None:
        super().__init__(message)
        # The model that produced the failure, when known. Assignments made to
        # the job before the raise are lost with the session rollback, so
        # record_job_failure re-persists this from the exception.
        self.model = model
        self.next_step = next_step
        self.settings = settings


@dataclass(frozen=True)
class Failure:
    headline: str
    next_step: str
    technical: str | None = None
    settings: str | None = None

    def sentence(self) -> str:
        """The headline and next step as one line — `job.error`, for anything
        that reads the error as text (older clients, the activity log)."""
        return f"{self.headline} {self.next_step}"

    def as_json(self) -> dict:
        return {
            "headline": self.headline,
            "next_step": self.next_step,
            "technical": self.technical,
            "settings": self.settings,
        }


def _entry(kind: str) -> str:
    """Where the details go: a scan has its image to read them from."""
    return "Enter the details from the image" if kind == "receipt" else "Enter the details yourself"


def _call_facts(call: dict | None) -> str | None:
    """The model call's facts, as one line: model · thinking · tokens · time."""
    if not call:
        return None
    facts: list[str] = []
    model = (call.get("request") or {}).get("model")
    if model:
        facts.append(str(model))
    if "thinking_enabled" in call:
        facts.append("thinking on" if call["thinking_enabled"] else "thinking off")
    tokens = call.get("completion_tokens")
    if isinstance(tokens, int):
        facts.append(f"{tokens:,} tokens")
    duration = call.get("duration_ms")
    if isinstance(duration, int):
        facts.append(f"{round(duration / 1000)} s")
    return " · ".join(facts) or None


def _technical(cause: str | None, call: dict | None) -> str | None:
    lines = [line for line in (cause, _call_facts(call)) if line]
    return "\n".join(lines) or None


def _cut_short(exc: ReplyCutShort, kind: str, call: dict | None, read: dict | None) -> Failure:
    """A reply cut short: never retried (the same call stops the same way)."""
    receipt = kind == "receipt"
    entry = _entry(kind)
    reached = "reaching the total" if receipt else "finishing"
    if exc.reason == STOP_REPETITION:
        return Failure(
            "The model got stuck repeating one line and was stopped.",
            f"{entry}, or try a closer photo of just the bottom of the receipt."
            if receipt
            else f"{entry}.",
            _technical(f"Stopped: one item repeated {LOOPING_RUN} times in a row", call),
        )
    if exc.reason == STOP_DEADLINE:
        return Failure(
            "Reading took longer than the time limit.",
            f"The model hadn't finished yet. {entry}, or allow more time and try again.",
            _technical("Stopped at the time limit", call),
            TIMEOUT_SETTING,
        )
    cause = "Cut off: output limit or context window reached"
    headline = f"The model ran out of room before {reached}."
    if read and read.get("thinking_fallback"):
        # Thinking ran out of room, and so did the re-read without it:
        # turning thinking off is not the advice.
        return Failure(
            headline,
            f"It ran out with thinking on and again with it off — it may be too long to"
            f" read in one go. {entry}.",
            _technical(f"Thinking ran out of room; re-read with thinking off\n{cause}", call),
        )
    if call is not None and not call.get("thinking_enabled"):
        return Failure(
            headline, f"It may be too long to read in one go. {entry}.", _technical(cause, call)
        )
    return Failure(
        headline,
        f"Thinking used the room the answer needed. {entry}, or turn thinking off and try again.",
        _technical(cause, call),
        THINKING_SETTING,
    )


def _ollama_status(exc: httpx.HTTPStatusError, will_retry: bool) -> Failure:
    detail = str(exc).split(": ", 1)[-1]
    technical = f"{exc.response.status_code}: {detail}"
    if exc.response.status_code == 404:
        return Failure(
            "Ollama doesn't have this model.",
            "Download it in Ollama, or choose another model.",
            technical,
            AI_SETTINGS,
        )
    return Failure(
        "Ollama ran into a problem.",
        RETRYING if will_retry else "If it keeps happening, check Ollama's own log.",
        technical,
    )


def explain_failure(
    exc: BaseException,
    kind: str,
    call: dict | None = None,
    read: dict | None = None,
    *,
    will_retry: bool = False,
) -> Failure:
    """What went wrong, what to do, and the evidence. `kind` is the job's
    ("receipt" or "nl_parse"); `call` the model call's debug view, when the
    failure came from one; `read` how the read was made; `will_retry` whether
    the worker is about to try again — the next step says so only then."""
    entry = _entry(kind)
    if isinstance(exc, NonRetryableJobError):
        return Failure(str(exc), exc.next_step or f"{entry}.", _call_facts(call), exc.settings)
    if isinstance(exc, ReplyCutShort):
        return _cut_short(exc, kind, call, read)
    if isinstance(exc, ReplyNotJSON):
        return Failure(
            "The model's answer couldn't be read.",
            RETRYING if will_retry else f"It couldn't be read on any try. {entry}.",
            _technical(str(exc), call),
        )
    if isinstance(exc, InvariantViolation):
        return Failure(
            "The model didn't read an amount.",
            RETRYING
            if will_retry
            else ("Enter it from the image." if kind == "receipt" else "Enter it yourself."),
            _technical(str(exc), call),
        )
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        check = "Check that it's running and that its address is right."
        return Failure(
            "Couldn't reach Ollama.",
            f"{RETRYING} {check}" if will_retry else check,
            error_text(exc),
            AI_SETTINGS,
        )
    if isinstance(exc, httpx.ReadTimeout):
        return Failure(
            "Ollama stopped sending anything.",
            "It may be busy with another model or out of memory. "
            + (RETRYING if will_retry else "Try again once it's free."),
            _technical(error_text(exc), call),
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return _ollama_status(exc, will_retry)
    if isinstance(exc, httpx.TransportError):
        return Failure(
            "The connection to Ollama broke off.",
            RETRYING if will_retry else "Check that Ollama is running, then try again.",
            error_text(exc),
        )
    return Failure(
        "Something unexpected went wrong.",
        f"{entry}. The details below are worth sending along.",
        _technical(error_text(exc, limit=300), call),
    )
