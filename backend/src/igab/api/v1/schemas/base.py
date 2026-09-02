"""The base every response schema inherits, and the one rule it carries.

**Money crosses the wire as a JSON number, not a string.**

Pydantic's default is a string, and every TypeScript interface in
`frontend/src/types/index.ts` declares these fields `number`. `tsc` cannot see
the difference between the two, so the mismatch never failed loudly — it
failed quietly, in the ways a string differs from a number:

    "0.00" !== 0            a settled card drew "$0.00" where the code said "—"
    "9.00" + "10.00"        concatenates, then reads NaN
    "9.00" >= "10.00"       true, lexicographically

The workaround grew to 444 `Number(...)` wrappings across 86 files, which is
not a mechanism: it is invisible exactly where somebody forgot it, and the
forgetting is silent. Serializing correctly once removes the need for all of
them, and `jsonable_encoder` — what FastAPI already uses for any endpoint
returning a plain dict — has always encoded `Decimal` as a number, so this
also ends a disagreement between two paths out of the same API.

Exact arithmetic is unaffected: the server stays `Decimal` end to end, and
this is only the wire. On the way back in, pydantic parses a JSON float to an
exact `Decimal` (`1234.56` → `Decimal('1234.56')`), so write paths are
unchanged.
"""

import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, SerializerFunctionWrapHandler, field_serializer


class ApiModel(BaseModel):
    """Every schema in this package. Inherit rather than annotating each field:
    there are 323 `Decimal` fields across 128 models, and a per-field spelling
    is 323 chances to leave one out."""

    @field_serializer("*", mode="wrap", when_used="json")
    def _money_as_number(self, value: Any, handler: SerializerFunctionWrapHandler) -> Any:
        # Containers of Decimal too — `dict[str, Decimal]` is how the register
        # ships its running balances. Anything else, including nested models,
        # goes to the default handler and gets this same treatment on its way
        # through, because every model in this package inherits it.
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, list) and value and all(isinstance(v, Decimal) for v in value):
            return [float(v) for v in value]
        if (
            isinstance(value, dict)
            and value
            and all(isinstance(v, Decimal) for v in value.values())
        ):
            return {k: float(v) for k, v in value.items()}
        return handler(value)


class ClientDated(ApiModel):
    """A request body that stamps a date on something the person just recorded.

    The browser sends its own local date. The server cannot work it out: it
    does not know the caller's timezone, so `today_utc()` is already tomorrow
    every evening west of UTC — which is how an asset valued on Tuesday night
    got dated Wednesday. Resolve with `clock.recorded_on`, which ranks the
    explicit date above this and this above the server's clock; never read a
    clock at the call site.
    """

    #: The browser's local "today", ISO. Optional: a non-browser caller that
    #: omits it still gets a date, just the server's own.
    client_today: datetime.date | None = None
