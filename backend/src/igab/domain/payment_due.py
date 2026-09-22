"""When a card's bill is due — the two shapes that statement date can take.

A day of the month is the obvious one and the only one stored until now: "the
17th", every month, clamped in February. It is also not how every issuer
bills. A card on a fixed-length cycle — 28 days, 31 days — walks its due date
through the calendar, so a household reading "the 17th" off a statement in
March is reading a date that will be the 14th by July. Storing that as a day
of the month is storing a figure a statement happened to show, which is the
same trap `minimum_payment` documents two screens up: it freezes the rule at
one observation and is wrong from the next cycle on.

So the rule is stored, not the figure:

- ``day_of_month`` — ``payment_due_day`` (1-31), clamped to the month's
  length. 31 in February is the 28th.
- ``cycle_days`` — ``payment_due_cycle_days`` days after
  ``payment_due_anchor``, the last due date the user actually saw, repeating.

**What lives here is the WRITE rule** — whether a stored pair is complete
enough to mean anything — and nothing else. The arithmetic that turns the
rule into the next date is on the client (``frontend/src/utils/paymentDue.ts``),
deliberately and by the boundary rule in CLAUDE.md: no backend path reads a
due date (amortization is monthly and dateless by design, and `payment_due_day`
has always been metadata), and the one input the arithmetic needs beyond these
columns is *today* — which the client owns. A GET has no `client_today` to
read, so a server-side answer would be computed against UTC and read a day
early for every evening west of Greenwich.

The two sides are not two copies of one rule: this one refuses a rule that
cannot be evaluated; the client's returns null for a card that has no rule on
file at all, which is most cards and is not an error.
"""

from datetime import date
from typing import Literal

from igab.domain.exceptions import InvariantViolation

PaymentDueKind = Literal["day_of_month", "cycle_days"]

#: The default, and what every row written before this module carries.
DAY_OF_MONTH: PaymentDueKind = "day_of_month"
CYCLE_DAYS: PaymentDueKind = "cycle_days"

PAYMENT_DUE_KINDS: tuple[PaymentDueKind, ...] = (DAY_OF_MONTH, CYCLE_DAYS)

#: Bounds on a cycle, wide enough for anything an issuer actually bills on
#: (weekly store cards at the bottom, quarterly at the top) and narrow enough
#: that a mistyped year of days refuses instead of projecting a due date in
#: 2031. Zero and negatives are the ones that matter: stepping a cycle of zero
#: days never reaches today, so the walk that finds the next due date would not
#: terminate.
MIN_CYCLE_DAYS = 7
MAX_CYCLE_DAYS = 120


def validate_payment_due(
    *,
    kind: str,
    day: int | None,
    cycle_days: int | None,
    anchor: date | None,
) -> None:
    """Refuse a due-date rule that cannot be evaluated. Raises InvariantViolation.

    Applied to the MERGED state on create and update — the same duty
    `validate_schedule` carries for a scheduled transaction — so a PATCH that
    sets a kind without its fields, or clears a field out from under its kind,
    cannot leave a row the client would have to render as "not set" while the
    dialog showed a cycle.

    A ``day_of_month`` rule with no day is the ordinary "no due date on file"
    state and is accepted: that is what every card starts as.
    """
    if kind not in PAYMENT_DUE_KINDS:
        allowed = ", ".join(PAYMENT_DUE_KINDS)
        raise InvariantViolation(f"A bill due date is stated one of two ways: {allowed}")

    if kind == DAY_OF_MONTH:
        if day is not None and not 1 <= day <= 31:
            raise InvariantViolation("The bill due day is a day of the month — 1 to 31")
        return

    # A cycle needs both halves. Either alone is unevaluable, and the halves
    # arrive from two different inputs in the dialog.
    if cycle_days is None or anchor is None:
        raise InvariantViolation(
            "A billing cycle needs both its length in days and the last due date you saw"
        )
    if not MIN_CYCLE_DAYS <= cycle_days <= MAX_CYCLE_DAYS:
        raise InvariantViolation(
            f"A billing cycle is between {MIN_CYCLE_DAYS} and {MAX_CYCLE_DAYS} days"
        )
