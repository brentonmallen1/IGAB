"""The Guide's worked examples, computed by the functions the reports run.

"Setting money aside" teaches with invented figures, but every figure it
shows is an answer from the real arithmetic — never a number typed into the
page. This module owns only the invented inputs; the rules stay in
`guide/concepts.py`.

Pure: fixed inputs in, figures out.
"""

from dataclasses import dataclass
from decimal import Decimal

from igab.guide.concepts import EssentialsWindows, emergency_fund_target, essentials_monthly

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


def spread_example() -> SpreadExample:
    """$2,000 a month of essentials and a $2,400 yearly bill, both ways.

    The windows are what `TransactionRepository.essential_windows` would read
    (outflows negative): three months of everyday essentials over 90 days,
    with the bill inside those 90 days or not, and the bill once in the year.
    """
    everyday = -EXAMPLE_MONTHLY_ESSENTIALS * 3
    bill = -EXAMPLE_YEARLY_BILL
    after_bill = essentials_monthly(
        EssentialsWindows(recent=everyday + bill, recent_sinking=bill, year_sinking=bill),
        spread_on=True,
    )
    otherwise = essentials_monthly(
        EssentialsWindows(recent=everyday, recent_sinking=Decimal("0"), year_sinking=bill),
        spread_on=True,
    )
    if after_bill.spread != otherwise.spread:
        # Spread is the point of the example: it reads the same either way.
        raise AssertionError("the spread figure moved with the bill's date")
    share = essentials_monthly(
        EssentialsWindows(recent=Decimal("0"), recent_sinking=Decimal("0"), year_sinking=bill),
        spread_on=True,
    ).spread
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
