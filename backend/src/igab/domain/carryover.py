"""How a category's available balance carries from one month to the next.

The rule is a month-by-month simulation, not a running total, and the
difference is the zero floor between months: when a category ends a month
negative, that overspending is covered from To Be Assigned and the next month
starts at zero rather than inheriting the debt. Only the month being viewed
may show a negative available.

This lived only inside `BudgetService.get_category_balance`, and a second
caller that needed the same number — the Guide, deciding whether to tell
someone they have no emergency fund — summed assignments and activity over all
time instead. That answer is lower than the budget page's for any category
that has ever overspent and been covered, and it is permanently lower. Stating
it once here is what keeps a roadmap from arguing with the budget it reads.

Pure: takes the two series and the month, returns the number.
"""

from datetime import date
from decimal import Decimal


def monthly_end_balances(
    assignments_by_month: dict[date, Decimal],
    activity_by_month: dict[date, Decimal],
) -> dict[date, Decimal]:
    """Each data month's raw end-of-month available, in one pass.

    The one loop of the simulation — `available_through` reads its answer out
    of this, and the card set-aside arithmetic (domain/cards.py) reads the
    negatives out of it to split a month's overspending by funding source.
    Values may be negative; the floor is applied *between* entries, so each
    value is what that month ended at before the next month floored it.
    """
    out: dict[date, Decimal] = {}
    carryover = Decimal("0")
    for m in sorted(set(assignments_by_month) | set(activity_by_month)):
        end_of_month = (
            carryover
            + assignments_by_month.get(m, Decimal("0"))
            + activity_by_month.get(m, Decimal("0"))
        )
        out[m] = end_of_month
        # Floor into the next month; the month itself keeps its raw value.
        carryover = max(Decimal("0"), end_of_month)
    return out


def available_through(
    assignments_by_month: dict[date, Decimal],
    activity_by_month: dict[date, Decimal],
    month_start: date,
) -> Decimal:
    """Available in `month_start`, simulating every month up to it.

    Both dicts are keyed by the first of the month. Months absent from both
    contribute nothing and are skipped — a gap in the calendar is not a month
    that zeroed the carryover.
    """
    balances = monthly_end_balances(
        {m: v for m, v in assignments_by_month.items() if m <= month_start},
        {m: v for m, v in activity_by_month.items() if m <= month_start},
    )
    # Only the month with its own data may show negative. A later month starts
    # from the floored carryover, because the overspend was absorbed by TBA.
    if month_start in balances:
        return balances[month_start]
    if not balances:
        return Decimal("0")
    return max(Decimal("0"), balances[max(balances)])
