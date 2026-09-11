"""Cutting a tool result down to something a model can hold — honestly.

**Never truncate silently.** A model handed 25 of 912 rows will say "you had 25
Dining transactions", and a budgeting app that states a wrong count is the
failure this repo's own history opens with — the badge saying 3 while the
register drew 930. So every clipped result carries the true count and says it
was clipped, in a field the prompt renders.

Pure: no session, no I/O, no clock. Every branch is a one-line test.
"""

from decimal import Decimal
from typing import Any

#: Rows in a listing tool result. Small on purpose — a local model's context is
#: the scarce resource, and the aggregate below is exact regardless.
DEFAULT_ROW_LIMIT = 25

#: The floor for a whole serialized result before it is replaced by a summary.
#: The real budget is sized from the model's context window — see
#: ``igab.ai.context_window`` — and this is what a caller gets when it has
#: not said. It once stood alone at this value and silently turned a month
#: grid of 188 envelopes into "too many categories to list".
TOOL_RESULT_MAX_CHARS = 6000


def money(value: Any) -> Any:
    """Money as a JSON number, matching what the API serves.

    `ApiModel` turns Decimal into float when serializing to JSON, so a tool
    that hands the model a Decimal string would quote figures the UI shows
    unquoted — and the two would read as different numbers.
    """
    if isinstance(value, Decimal):
        return float(value)
    return value


def clip(
    rows: list[dict],
    *,
    limit: int = DEFAULT_ROW_LIMIT,
    total_rows: int | None = None,
    total_amount: Any = None,
) -> dict:
    """A bounded row list that still states the whole truth.

    `total_rows` and `total_amount` are the figures computed over the *full*
    predicate, not over `rows` — that is the point. `list_for_budget` already
    returns both beside its page, so the honest total costs nothing.
    """
    true_count = len(rows) if total_rows is None else total_rows
    shown = rows[:limit]
    result: dict[str, Any] = {
        "rows": shown,
        "shown": len(shown),
        "total_rows": true_count,
        "truncated": true_count > len(shown),
    }
    if total_amount is not None:
        result["total_amount"] = money(total_amount)
    if result["truncated"]:
        result["note"] = (
            f"Showing {len(shown)} of {true_count} rows. Any totals above cover "
            f"all {true_count}, not just the ones shown."
        )
    return result


def ranked(
    rows: list[dict],
    *,
    measure: str,
    total_amount: Any = None,
    total_rows: int | None = None,
) -> dict:
    """A "top N by spend" result, said as what it is.

    Distinct from `clip`, and the distinction is the point. `clip` describes a
    *page* of a list whose true length is known. These reports are ranked: the
    service returns the biggest N and a total computed over **everything**.

    Passing one through `clip` told the model "25 rows, not truncated", so it
    would answer "you paid 25 payees" for a budget with three hundred — the
    badge-says-3-register-draws-930 failure, one table over.

    `total_rows` is for a ranking whose service DOES count the whole set —
    `payee_analysis` now does, because both the Pareto card and the payee
    table needed the denominator to stop stating the cap as a period-wide
    fact. Omit it and the note still forbids guessing, which is the honest
    answer for a ranking that never counted.
    """
    counted = total_rows is not None
    note = (
        f"These are only the {len(rows)} largest by {measure}, not every row. "
        "Any total above covers them all, not just the ones shown. "
    )
    note += (
        f"There were {total_rows} in total."
        if counted
        else "Do not state how many there were in total — this result does not say."
    )
    return {
        "rows": rows,
        "shown": len(rows),
        "ranking": f"the {len(rows)} largest by {measure}",
        # None unless the caller counted: inventing a number here is exactly
        # what went wrong.
        "total_rows": total_rows,
        "truncated": not counted or total_rows > len(rows),
        **({"total_amount": money(total_amount)} if total_amount is not None else {}),
        "note": note,
    }


def fits(payload: Any, max_chars: int = TOOL_RESULT_MAX_CHARS) -> bool:
    """Whether a serialized result is small enough to hand to a model."""
    import json

    try:
        return len(json.dumps(payload, default=str)) <= max_chars
    except (TypeError, ValueError):
        return False


def summarize_if_large(
    payload: dict, *, keep: tuple[str, ...] = (), max_chars: int = TOOL_RESULT_MAX_CHARS
) -> dict:
    """Fall back to a summary when a result is too big to send whole.

    `keep` names the fields worth preserving verbatim — usually the totals.
    Everything else is replaced by a count, and the result says so, because a
    quietly emptied field reads to the model as "there is nothing there".

    `max_chars` comes from the context window the call was given
    (``context_window.result_char_budget``); the default is only the floor.
    """
    if fits(payload, max_chars):
        return payload
    summary: dict[str, Any] = {k: payload[k] for k in keep if k in payload}
    dropped: list[str] = []
    for key, value in payload.items():
        if key in summary:
            continue
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
            dropped.append(key)
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = len(value)
            dropped.append(key)
        else:
            summary[key] = value
    if dropped:
        summary["note"] = (
            "This result was too large to send in full, so "
            f"{', '.join(sorted(dropped))} were replaced by counts. Ask a "
            "narrower question — a shorter date range, or one category."
        )
    return summary
