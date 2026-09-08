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

#: A whole serialized result larger than this is replaced by a summary. Guards
#: the case a row cap cannot: one report with no row list and 200 categories.
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


def fits(payload: Any) -> bool:
    """Whether a serialized result is small enough to hand to a model."""
    import json

    try:
        return len(json.dumps(payload, default=str)) <= TOOL_RESULT_MAX_CHARS
    except (TypeError, ValueError):
        return False


def summarize_if_large(payload: dict, *, keep: tuple[str, ...] = ()) -> dict:
    """Fall back to a summary when a result is too big to send whole.

    `keep` names the fields worth preserving verbatim — usually the totals.
    Everything else is replaced by a count, and the result says so, because a
    quietly emptied field reads to the model as "there is nothing there".
    """
    if fits(payload):
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
