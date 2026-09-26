"""What one subscription costs a year — the Subscriptions report's arithmetic.

Pure: a service's signed ledger rows in, one `ServiceCost` out, so every
branch is a one-line test. The cadence and the stopped rule are
`domain.schedule`'s, which the cash projection's subscription arm reads too:
the report and the projection must agree on which services are alive.

The rule (decided 2026-09-25):

- **Annual is what the last 12 complete months charged**, net of refunds.
  Monthly is Annual ÷ 12. The report used to divide each service's charges by
  the months since its first charge *inside the chosen range*, so a $60-a-year
  bill charged in June read $20/mo in September — $240 a year, four times the
  bill — and Annual swung threefold as the range picker moved.
- **Only a service younger than that year is extrapolated**: its latest
  charge times the cycles a year its observed cadence makes. A year of
  history is the bill; less than a year is a guess, and says so. A single
  charge has no cadence to observe, so it counts once, as charged: read as
  monthly, one $40 charge became $480 of a $520 headline.
- **A price change projects from the latest charge** once the new price has
  been charged twice. A year of $15 charges and then two of $18 is an $18
  service; blending them understated it until a year had passed at the new
  price. One different charge is not yet a price: it was an add-on billed
  beside the plan as often as a new one, and projecting it for a year read a
  $12 service as $5.
- **A service with no charge for 1.5 cycles is stopped** (`has_stopped`): it is
  still listed, and it counts in nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from igab.domain.money import quantize_cents
from igab.domain.schedule import (
    Cadence,
    cadence_of,
    cycles_per_year,
    has_stopped,
    observed_interval_days,
)


class Basis(StrEnum):
    """How a service's Annual was arrived at — served, so the page can say
    which figures are measured and which are projected."""

    #: The charges of the last 12 complete months, net of refunds.
    OBSERVED = "observed"
    #: First charged inside that year: latest charge × cycles a year — or,
    #: with one charge and so no cadence, that charge once.
    NEW = "new"
    #: Its price changed inside the year and the new price has been charged
    #: twice: every charge in the year at the latest price, net of refunds.
    PRICE_CHANGE = "price_change"
    #: No charge for 1.5 cycles. Annual is zero.
    STOPPED = "stopped"


#: Bases whose Annual can be a projection rather than a sum of charges —
#: always for a price change; for a new service only once it has a cadence
#: (`is_projected`).
PROJECTED = frozenset({Basis.NEW, Basis.PRICE_CHANGE})


@dataclass(frozen=True)
class ServiceCost:
    basis: Basis
    #: Net of refunds; zero for a stopped service.
    annual: Decimal
    #: `annual` ÷ 12.
    monthly: Decimal
    interval_days: int
    cadence: Cadence
    #: One charge (or several on one day) says nothing about cadence; monthly
    #: is assumed (`schedule.ASSUMED_INTERVAL_DAYS`) and the page says so.
    cadence_assumed: bool
    #: The most recent charge, as a positive cost.
    latest_charge: Decimal
    first_charge_date: date
    last_charge_date: date
    #: Charges inside the 12-month year.
    charges_in_year: int
    #: Refunds inside the year, positive — already taken off `annual`.
    refunded_in_year: Decimal
    #: First charged in the month still running.
    new_this_month: bool

    @property
    def is_projected(self) -> bool:
        """Whether Annual is a projection. A new service with one charge is
        not: it counts that charge once."""
        return self.basis in PROJECTED and not (self.basis is Basis.NEW and self.cadence_assumed)


#: How many charges at a new price make it the price.
NEW_PRICE_CHARGES = 2


def _price_change(amounts: Sequence[Decimal]) -> bool:
    """Whether a run of charges, oldest first, is one price and then another:
    X … X Y … Y with X ≠ Y and at least `NEW_PRICE_CHARGES` Ys.

    That shape and no other. A payee billing several different plans, or a
    usage-priced bill that varies every month, is not a price change — reading
    its latest charge as the price would project one month's bill for a year.
    """
    latest = amounts[-1] if amounts else None
    i = len(amounts)
    while i > 0 and amounts[i - 1] == latest:
        i -= 1
    before = amounts[:i]
    return (
        len(amounts) - i >= NEW_PRICE_CHARGES
        and bool(before)
        and all(a == before[0] for a in before)
    )


def service_cost(
    rows: Sequence[tuple[date, Decimal]],
    *,
    year_start: date,
    year_end: date,
    today: date,
) -> ServiceCost | None:
    """One service's cost from its signed ledger rows (charges negative,
    refunds positive), over every date the budget has seen it through `today`.

    `year_start`..`year_end` is the last 12 complete months
    (`dates.complete_month_window(today, 12)`). None when the rows hold no
    charge at all — a refund with nothing to refund is not a service.
    """
    charges = sorted((d, -a) for d, a in rows if a < 0 and d <= today)
    if not charges:
        return None

    first, last = charges[0][0], charges[-1][0]
    interval = observed_interval_days(first, last, len(charges))
    latest = charges[-1][1]

    in_year = [cost for d, cost in charges if year_start <= d <= year_end]
    refunded = sum((a for d, a in rows if a > 0 and year_start <= d <= year_end), Decimal(0))
    # The price-change test reads the year AND the running month: a new price
    # first charged this month is the price from now on.
    recent = [cost for d, cost in charges if d >= year_start]

    if has_stopped(last, interval, today):
        basis, annual = Basis.STOPPED, Decimal(0)
    elif first >= year_start:
        basis = Basis.NEW
        if last <= first:  # no cadence observed: what it charged, once
            annual = sum((cost for _, cost in charges), Decimal(0)) - refunded
        else:
            annual = latest * cycles_per_year(interval) - refunded
    elif _price_change(recent):
        basis = Basis.PRICE_CHANGE
        annual = latest * len(in_year) - refunded
    else:
        basis = Basis.OBSERVED
        annual = sum(in_year, Decimal(0)) - refunded

    annual = quantize_cents(annual)
    return ServiceCost(
        basis=basis,
        annual=annual,
        monthly=quantize_cents(annual / 12),
        interval_days=interval,
        cadence=cadence_of(interval),
        cadence_assumed=last <= first,
        latest_charge=quantize_cents(latest),
        first_charge_date=first,
        last_charge_date=last,
        charges_in_year=len(in_year),
        refunded_in_year=quantize_cents(refunded),
        new_this_month=(first.year, first.month) == (today.year, today.month),
    )
