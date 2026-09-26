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
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from igab.services.report_day import reader_today


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


def _reader_today(client_today: Annotated[date | None, Query()] = None) -> date:
    return reader_today(client_today)


#: The reader's day, for a report that ends "today" or leaves the running month
#: out — which is every report with a window it did not get from the caller.
#: A GET has no body to carry `ClientDated`, so the browser's local date rides
#: as `client_today` (`frontend/src/api/reports.ts` sends it on every report
#: request). A caller that omits it gets the server's day — see
#: `services/report_day.py` for why that is a different day every evening.
#: Resolved here, once, so an endpoint receives a date rather than a choice.
ReaderToday = Annotated[date, Depends(_reader_today)]
