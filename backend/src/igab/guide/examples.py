"""The Guide's worked examples, computed by the functions the reports run.

"Setting money aside" teaches with invented figures, but every figure it
shows is an answer from the real arithmetic — never a number typed into the
page. This module owns only the invented inputs; the rules stay in
`guide/concepts.py`.

Pure: fixed inputs in, figures out.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.guide.concepts import emergency_fund_target, essentials_at

#: Essential spending in a month without the bill, and the yearly bill filed to
#: a Long-term expense category. Round, so the page can be checked on paper.
EXAMPLE_MONTHLY_ESSENTIALS = Decimal("2000")
EXAMPLE_YEARLY_BILL = Decimal("2400")
#: The emergency-fund goal the example sizes, in months of essentials.
EXAMPLE_GOAL_MONTHS = 3


@dataclass(frozen=True)
class SpreadExample:
    #: As paid, in a quarter the bill landed in / a quarter it did not.
    as_paid_after_bill: Decimal
    as_paid_otherwise: Decimal
    #: Spread: the same in either quarter.
    spread: Decimal
    #: The bill's twelfth.
    bill_monthly_share: Decimal
    goal_months: int
    goal_as_paid_after_bill: Decimal
    goal_as_paid_otherwise: Decimal
    goal_spread: Decimal


def _year(bill_month: int | None) -> tuple[list[date], list[Decimal], list[Decimal]]:
    """Twelve invented complete months of everyday essentials, with the
    yearly bill landing in month `bill_month` (0 = oldest), or nowhere —
    the shape `services.essentials.essential_months` reads (magnitudes)."""
    months = [date(2025, m, 1) for m in range(1, 13)]
    totals = [EXAMPLE_MONTHLY_ESSENTIALS] * 12
    sinking = [Decimal("0")] * 12
    if bill_month is not None:
        totals[bill_month] += EXAMPLE_YEARLY_BILL
        sinking[bill_month] = EXAMPLE_YEARLY_BILL
    return months, totals, sinking


def spread_example() -> SpreadExample:
    """$2,000 a month of essentials and a $2,400 yearly bill, both ways.

    Twelve complete months, read at the newest (`essentials_at`): the bill
    inside the last three months, or earlier in the year.
    """
    after_bill = essentials_at(*_year(11), 11, spread_on=True)
    otherwise = essentials_at(*_year(2), 11, spread_on=True)
    if after_bill.spread != otherwise.spread:
        # Spread is the point of the example: it reads the same either way.
        raise AssertionError("the spread figure moved with the bill's date")
    months, _, sinking = _year(2)
    share = essentials_at(months, [Decimal("0")] * 12, sinking, 11, spread_on=True).spread
    return SpreadExample(
        as_paid_after_bill=after_bill.as_paid,
        as_paid_otherwise=otherwise.as_paid,
        spread=after_bill.spread,
        bill_monthly_share=share,
        goal_months=EXAMPLE_GOAL_MONTHS,
        goal_as_paid_after_bill=emergency_fund_target(after_bill.as_paid, EXAMPLE_GOAL_MONTHS),
        goal_as_paid_otherwise=emergency_fund_target(otherwise.as_paid, EXAMPLE_GOAL_MONTHS),
        goal_spread=emergency_fund_target(after_bill.spread, EXAMPLE_GOAL_MONTHS),
    )
