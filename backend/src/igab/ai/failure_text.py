"""What a failed scan or description says to the person reviewing it — pure.

The job's error is read in the review banner and on the Scans tab, by someone
holding a receipt, not a stack trace. It used to be the exception's own text
("ReplyCutShort: The model's reply was cut off before its JSON was complete",
"ReadTimeout: "), which named the failure in the app's vocabulary and said
nothing about what to do next.

Each sentence here says what happened in plain words and, when there is one,
the next step — naming the setting as the screen labels it. A sentence that
mentions System → AI gets the banner's "Open System → AI" link
(`isConfigFailure` in the frontend's scanFailure.ts). The technical text stays
where it is useful: on the model call's record in AI Activity → Model calls.
"""

import httpx

from igab.ai.context import error_text
from igab.ai.reply_json import ReplyCutShort, ReplyNotJSON
from igab.domain.exceptions import InvariantViolation
from igab.integrations.ollama.client import STALL_TIMEOUT_S, STOP_DEADLINE, STOP_REPETITION

#: Where the two settings that matter for a slow or long read live, as the
#: screen labels them.
_THINKING = "System → AI → Advanced → Thinking"
_TIMEOUT = "System → AI → Advanced → Receipt scan timeout"


def _subject(kind: str) -> str:
    return "this receipt" if kind == "receipt" else "this description"


def _cut_short(exc: ReplyCutShort, kind: str) -> str:
    thing = _subject(kind)
    if exc.reason == STOP_REPETITION:
        return (
            f"The model got stuck repeating one line while reading {thing}, before it"
            " reached the total, so it was stopped. Enter the details yourself, or try a"
            " closer photo of just the bottom of the receipt."
        )
    if exc.reason == STOP_DEADLINE:
        return (
            f"Reading {thing} took longer than the time limit, and the model hadn't reached"
            f" the total yet. Enter the details yourself, or allow more time in {_TIMEOUT}."
        )
    return (
        f"The model ran out of room before it finished reading {thing}"
        " — usually a long receipt with thinking on. Enter the details yourself, or turn"
        f" thinking off in {_THINKING} and scan it again."
    )


def _ollama_status(exc: httpx.HTTPStatusError) -> str:
    detail = str(exc).split(": ", 1)[-1]
    if exc.response.status_code == 404:
        return (
            f"Ollama doesn't have the model this uses ({detail}). Download it in Ollama, or"
            " choose another model in System → AI."
        )
    return f"Ollama ran into a problem and stopped: {detail}."


def failure_text(exc: BaseException, kind: str) -> str:
    """One or two sentences for the person: what went wrong, and what to do.
    `kind` is the job's ("receipt" or "nl_parse")."""
    from igab.tasks.ai_worker import NonRetryableJobError  # the worker imports this

    thing = _subject(kind)
    if isinstance(exc, NonRetryableJobError):
        return str(exc)  # written for people where it is raised
    if isinstance(exc, ReplyCutShort):
        return _cut_short(exc, kind)
    if isinstance(exc, ReplyNotJSON):
        return (
            f"The model's answer for {thing} couldn't be read. Scanning again sometimes"
            " works; otherwise enter the details yourself."
        )
    if isinstance(exc, InvariantViolation):
        return f"The model didn't read an amount from {thing}. Enter it yourself" + (
            " from the image." if kind == "receipt" else "."
        )
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return (
            "Couldn't reach Ollama. Check that it's running and that the address in"
            " System → AI is right."
        )
    if isinstance(exc, httpx.ReadTimeout):
        return (
            f"Ollama stopped responding for {int(STALL_TIMEOUT_S // 60)} minutes while"
            f" reading {thing}. It may be busy with another model or out of memory."
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return _ollama_status(exc)
    if isinstance(exc, httpx.TransportError):
        return "The connection to Ollama broke off. Check that it's running."
    return (
        f"Something unexpected went wrong ({error_text(exc, limit=300)}). Enter the"
        " details yourself; AI Activity → Model calls has more."
    )
