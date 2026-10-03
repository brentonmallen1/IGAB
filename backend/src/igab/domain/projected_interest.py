"""What a loan's projected interest row for one month should be.

A loan payment posts as a transfer of the whole amount into the loan
account. The lender splits it: the interest it charged on last month's close
is a separate, payee-less outflow on the loan, and nothing in the app writes
that row — so the register and the loan's balance ran one month of interest
low until someone typed it in or the bank sent it. The app now writes it
from the terms on file, and replaces it the moment the lender's own row
arrives.

This module is the rule; `services/projected_interest.py` is the wiring that
gathers each month's facts and writes the plan. Pure: facts in, a plan out.

**One month, one question.** A projection is wanted for a month when:

- the month has a payment (`LOAN_PAYMENT_ROW`) — interest is charged when a
  statement closes, and a month with no payment is not a month the app
  knows a statement for;
- the lender's own interest row has not arrived (`LENDER_INTEREST_ROW`);
- something was owed as the month opened, at a rate above zero — the same
  `interest_for_month` the liability page's estimate reads, so the row and
  the estimate are one figure;
- the person has not declined the month (deleted its projection).

The amount is that month's interest as an outflow; the date is the month's
first payment, which is where a lender's statement puts it.

**Known limit.** A lender that posts the interest on the 1st of the
FOLLOWING month (some servicers do) is outside this month model — the same
model `liability_service._charged_interest` reads. Its row for March lands
in April, so March keeps its projection and April, which now holds a lender
row, gets none. The balance then carries March's interest twice — the
projection and the lender's row — until the person deletes the projection,
which declines March for good. Those lenders' months are each "charged" by
the previous month's row, so this happens once per loan, at the month the
terms were first filled in.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from igab.domain.dates import add_months, month_start
from igab.domain.field_changes import changed_fields
from igab.domain.interest import interest_for_month

ZERO = Decimal("0")

#: `Transaction.created_via` for a projection. `change_log.source_for` maps
#: it to `system`: the app wrote it, not the person.
PROJECTION_ORIGIN = "projection"

#: The memo a projection carries, so a register row says what it is even
#: where the badge is not drawn (exports, the MCP tools).
PROJECTION_MEMO = (
    "Projected interest from the loan's terms — replaced when the lender posts its own"
)

#: Change-log bookkeeping on a retire's `before`: this delete was the app
#: replacing its own projection, not the person declining the month. Written
#: by `services/projected_interest.py`, read by undo's redo path
#: (`UndoService._reapply_delete`) so a replayed retire clears the month.
RETIRED_KEY = "_retired"

#: The fields whose edit makes a projection the person's own row. Money and
#: bank state: a new amount is the person saying "this is what was charged",
#: a new date or account moves it somewhere this month's plan no longer
#: describes, and clearing it is the person vouching for it against the
#: statement. A memo, payee or category edit is bookkeeping and adopts
#: nothing.
ADOPTING_FIELDS = ("amount", "date", "cleared", "account_id")


def adopts_projection(current: Mapping[str, Any], changes: Mapping[str, Any]) -> bool:
    """Would this edit make a projection the person's own row?

    Compared, not tested for presence — the editor sends every field it
    shows, so an unchanged amount riding along with a memo edit adopts
    nothing (`domain.field_changes`).
    """
    return bool(changed_fields(current, changes, ADOPTING_FIELDS))


def may_create_for(month: date, today: date) -> bool:
    """A NEW projection is written only for this month and last.

    Last month too, because a payment typed a few days after the month turned
    still belongs to the month it was made in. Nothing older: a register
    brought in with years of history would otherwise sprout a row in every
    month, for interest the lender long since charged and the person never
    recorded. An existing projection is updated or retired whatever its age —
    that is correcting the app's own row, not inventing one.
    """
    this_month = month_start(today)
    return month_start(month) in (this_month, add_months(this_month, -1))


@dataclass(frozen=True)
class StandingProjection:
    """The live projection already written for a month."""

    id: UUID
    date: date
    #: Signed, as stored: an outflow, so negative.
    amount: Decimal


@dataclass(frozen=True)
class MonthFacts:
    """Everything the plan needs to know about one loan account's month."""

    month: date
    #: Owed as the month opened, positive (`owed_at_month_open`). Includes
    #: last month's projection when it stands: a lender charges interest on
    #: interest it has already charged.
    owed_at_open: Decimal
    #: The month's first payment, or None when no payment arrived.
    first_payment: date | None
    #: The lender's own interest rows this month, signed (zero or negative).
    lender_interest: Decimal
    standing: StandingProjection | None
    #: The person deleted this month's projection — a tombstone.
    declined: bool


@dataclass(frozen=True)
class Create:
    month: date
    date: date
    amount: Decimal


@dataclass(frozen=True)
class Update:
    id: UUID
    date: date
    amount: Decimal


@dataclass(frozen=True)
class Retire:
    id: UUID


Plan = Create | Update | Retire | None


def projected_amount(facts: MonthFacts, rate: Decimal | None) -> Decimal | None:
    """The row the month should carry, signed — or None when it should carry
    none. `rate` is the month's CHARGEABLE rate (`chargeable_rate`): None
    when no terms are on file, zero inside a promo."""
    if rate is None or facts.declined or facts.first_payment is None:
        return None
    if facts.lender_interest != ZERO:
        return None
    interest = interest_for_month(facts.owed_at_open, rate)
    if interest <= ZERO:
        return None
    return -interest


def plan_projection(facts: MonthFacts, rate: Decimal | None, may_create: bool) -> Plan:
    """Create, Update, Retire or None for one month.

    `may_create` gates only a NEW row (see `may_create_for`); a standing one is
    kept in step — re-dated, re-sized or retired — however old it is.
    """
    amount = projected_amount(facts, rate)
    standing = facts.standing
    if amount is None:
        return Retire(standing.id) if standing is not None else None
    assert facts.first_payment is not None  # projected_amount checked it
    if standing is None:
        return Create(month_start(facts.month), facts.first_payment, amount) if may_create else None
    if standing.amount != amount or standing.date != facts.first_payment:
        return Update(standing.id, facts.first_payment, amount)
    return None
