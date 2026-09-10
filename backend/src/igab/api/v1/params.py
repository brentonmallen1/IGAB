"""Query-parameter parsing shared by the report and transaction routes.

One home, because the two had drifted into opposite behaviours on the same
input. `transactions.py` rejected a malformed id with a 400 naming the value;
`reports.py` returned None — and None is the "no scope was asked for" sentinel,
so one bad character in a category, tag, account or payee id silently WIDENED
the report to the whole budget.

`report_scope.py`'s own docstring calls that out as the worse surprise: "a
stale id resolving to nothing would silently WIDEN the report to the whole
budget, which looks like data appearing rather than a filter going missing."
It guarded `filter_id` against exactly this and the id lists went unguarded
beside it.
"""

import uuid

from fastapi import HTTPException, status


def parse_uuid_list(value: str | None) -> list[uuid.UUID] | None:
    """Parse a comma-separated id list, rejecting malformed entries with a 400.

    Unguarded `uuid.UUID()` turns a client-side id-construction slip into a
    500 from the catch-all handler, which reads as a server fault and tells
    nobody which value was wrong. Returning None instead is worse still: it is
    indistinguishable from "no filter", so the report answers a question nobody
    asked and looks like it is working.
    """
    if not value:
        return None
    try:
        return [uuid.UUID(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed id: {e}"
        ) from e


def parse_csv(value: str | None) -> list[str] | None:
    """A comma-separated list of plain strings, or None when nothing was asked."""
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()] or None
