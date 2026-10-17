"""What a target could be, read off a category's own last twelve months.

The target editor offers three figures as one-tap suggestions: the average
month's spending, the heaviest single month, and the most the envelope has
ever held at a month's end — the first two for a monthly amount, the last
for a "Stop at". Orchestration only, computing nothing new:

- Spending is the plan ledger's (`plan_ledger.spent_series`) — net of
  refunds, money moved in not counted as spending — over the same window and
  divided the same way as the Category History report the budget page's
  inspector draws, so "Avg $X/mo" here is the average printed there. It is
  NOT Auto-assign's "Average spent" (`BudgetService.get_category_history`),
  which answers a different question; see that method.
- The balance is the Budget page's own month-end Available
  (`BudgetService.envelope_series`).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.services.budget_service import BudgetService
from igab.services.plan_ledger import spent_series
from igab.services.report_basics import budget_window

ZERO = Decimal("0")

#: How far back a suggestion reads: a year of complete months, so a yearly
#: bill and a December are both in it.
SUGGESTION_MONTHS = 12


@dataclass(frozen=True)
class TargetSuggestions:
    #: The Category History report's average over the window: net spent per
    #: complete month, every complete month counted. Floored at zero — a year
    #: whose refunds beat its spending suggests no monthly amount.
    average_spent: Decimal
    #: The heaviest complete month's net spent, and which month it was. None
    #: when no month spent anything.
    peak_spent: Decimal | None
    peak_spent_month: date | None
    #: The most the envelope held at a complete month's end, and when. None
    #: when it never held anything.
    peak_available: Decimal | None
    peak_available_month: date | None
    #: Complete months the window holds — fewer than twelve on a budget whose
    #: history starts inside the year. Zero means there is nothing to suggest.
    months_counted: int


def _peak(values: list[tuple[date, Decimal | None]]) -> tuple[Decimal | None, date | None]:
    """The largest positive value and its month; the latest month wins a tie,
    as the more recent evidence. (None, None) when nothing is above zero."""
    best: tuple[Decimal | None, date | None] = (None, None)
    for month, value in values:
        if value is not None and value > ZERO and (best[0] is None or value >= best[0]):
            best = (value, month)
    return best


async def target_suggestions(
    session: AsyncSession,
    budget_service: BudgetService,
    budget_id: uuid.UUID,
    category_id: uuid.UUID,
    today: date,
) -> TargetSuggestions:
    window = await budget_window(session, budget_id, SUGGESTION_MONTHS, today)
    complete = list(window.complete)
    spent = await spent_series(session, budget_id, category_id, window, today)
    # `spent.spent` runs over `window.axis`: the complete months, then the
    # running one, which no suggestion reads.
    peak_spent, peak_spent_month = _peak(list(zip(complete, spent.spent, strict=False)))

    peak_available: Decimal | None = None
    peak_available_month: date | None = None
    if complete:
        series = (await budget_service.envelope_series(budget_id, [category_id], complete))[
            category_id
        ]
        # An income category's Available is a lifetime total, not a balance.
        if not series.in_system_group:
            peak_available, peak_available_month = _peak(
                list(zip(complete, series.available, strict=True))
            )

    return TargetSuggestions(
        average_spent=max(spent.average_spent, ZERO),
        peak_spent=peak_spent,
        peak_spent_month=peak_spent_month,
        peak_available=peak_available,
        peak_available_month=peak_available_month,
        months_counted=spent.months_averaged,
    )
