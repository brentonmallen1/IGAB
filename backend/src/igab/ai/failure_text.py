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
from igab.integrations.ollama.client import STALL_TIMEOUT_S, STOP_DEADLINE, STOP_REPETITION

AI_SETTINGS = "System → AI"
THINKING_SETTING = "System → AI → Advanced → Thinking"
TIMEOUT_SETTING = "System → AI → Advanced → Receipt scan timeout"


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


def _cut_short(exc: ReplyCutShort, kind: str, call: dict | None) -> Failure:
    entry = _entry(kind)
    if exc.reason == STOP_REPETITION:
        return Failure(
            "The model got stuck repeating one line and was stopped.",
            f"{entry}, or try a closer photo of just the bottom of the receipt."
            if kind == "receipt"
            else f"{entry}.",
            _technical(f"Stopped: one item repeated {LOOPING_RUN} times in a row", call),
        )
    if exc.reason == STOP_DEADLINE:
        return Failure(
            "Reading took longer than the time limit.",
            f"The model hadn't reached the total yet. {entry}, or allow more time and scan again.",
            _technical("Stopped at the time limit", call),
            TIMEOUT_SETTING,
        )
    return Failure(
        "The model ran out of room before reaching the total.",
        f"Usually a long receipt with thinking on. {entry}, or turn thinking off and scan again.",
        _technical("Cut off: output limit or context window reached", call),
        THINKING_SETTING,
    )


def _ollama_status(exc: httpx.HTTPStatusError, kind: str) -> Failure:
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
        "It tries again by itself; if it keeps happening, check Ollama's own log.",
        technical,
    )


def explain_failure(exc: BaseException, kind: str, call: dict | None = None) -> Failure:
    """What went wrong, what to do, and the evidence. `kind` is the job's
    ("receipt" or "nl_parse"); `call` is the model call's debug view, when
    the failure came from one."""
    from igab.tasks.ai_worker import NonRetryableJobError  # the worker imports this

    entry = _entry(kind)
    if isinstance(exc, NonRetryableJobError):
        return Failure(str(exc), exc.next_step or f"{entry}.", _call_facts(call), exc.settings)
    if isinstance(exc, ReplyCutShort):
        return _cut_short(exc, kind, call)
    if isinstance(exc, ReplyNotJSON):
        return Failure(
            "The model's answer couldn't be read.",
            f"Scanning again sometimes works; otherwise {entry[0].lower()}{entry[1:]}."
            if kind == "receipt"
            else f"Trying again sometimes works; otherwise {entry[0].lower()}{entry[1:]}.",
            _technical(str(exc), call),
        )
    if isinstance(exc, InvariantViolation):
        return Failure(
            "The model didn't read an amount.",
            "Enter it from the image." if kind == "receipt" else "Enter it yourself.",
            _technical(str(exc), call),
        )
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return Failure(
            "Couldn't reach Ollama.",
            "Check that it's running and that its address is right.",
            error_text(exc),
            AI_SETTINGS,
        )
    if isinstance(exc, httpx.ReadTimeout):
        return Failure(
            "Ollama stopped responding.",
            f"Nothing arrived for {int(STALL_TIMEOUT_S // 60)} minutes — it may be busy with"
            " another model or out of memory. It tries again by itself.",
            _technical(f"No data for {int(STALL_TIMEOUT_S)} s", call),
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return _ollama_status(exc, kind)
    if isinstance(exc, httpx.TransportError):
        return Failure(
            "The connection to Ollama broke off.",
            "It tries again by itself; check that Ollama is running.",
            error_text(exc),
        )
    return Failure(
        "Something unexpected went wrong.",
        f"{entry}. The details below are worth sending along.",
        _technical(error_text(exc, limit=300), call),
    )
