"""How fast money is going: the last thirty days against the sixty before them.

The Overview's "30-Day Burn Rate" card and every point of the Burn Rate tab's
chart read `burn` here. They used to spell the windows out once each — and the
Guide's essentials window a third time — with floats, the server's clock, and
a comparison that could not show a change:

- **The comparison shared its money.** The old second figure was the last
  ninety days ÷ 3, and those ninety days contain the thirty it was held
  against. A $900 spike in the last month moved the thirty-day figure by $900
  and the "average" by $300, so the two read nearly equal exactly when they
  should have parted. The prior sixty days end the day before the thirty
  begin: the two figures share no day and no dollar.
- **A refund lowered nothing.** Both copies summed `amount < 0` only, while
  Spent This Period and Essentials net a refund against the spending it
  reverses. Burn is net here, by the same sign rule: outflows are stored
  negative, and the burn is the negated signed sum, so a $120 return on a
  $300 purchase burns $180. A window where refunds outweigh spending reads
  negative — honestly — rather than being floored.

**Per thirty days.** The prior figure is the sixty days' total ÷
`PRIOR_MONTHS`, so both figures are in the same unit and their ratio is the
change a reader expects. `MONTH_DAYS` is what "a month" means for a trailing
window counted in days; `LOOKBACK_DAYS` is the whole span both windows cover.

**The Guide reads the same ninety days.** `guide.concepts` takes its
essentials window from `LOOKBACK_DAYS`/`LOOKBACK_MONTHS`, so on the Overview the
Essentials card and this one read one span, and a register tagged all
Essential can never quote an essentials month the burn's ninety days do not
contain. Changing the comparison here moves the Guide's window with it — on
purpose, and pinned by `test_report_windows.py`.

**Which rows.** The caller hands in signed per-day, per-class totals over
`txn_filters.CLASS_TOTAL_ROW` — the rows Spent This Period and Essentials sum
— and this decides which classes count (`counted_classes()`, spending) and
which days fall in which window. Pure: no session, no clock; `as_of` is the
day the reader is living in (`client_today` when the browser sent one).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple

from igab.domain.activity_class import counted_classes
from igab.domain.dates import trailing_start
from igab.domain.money import quantize_cents

#: A month, when a trailing window is counted in days. Days rather than
#: calendar months so the windows slide daily instead of jumping on the 1st.
MONTH_DAYS = 30
#: The burn itself: the trailing thirty days.
RECENT_MONTHS = 1
#: What it is compared with: the sixty days before those thirty.
PRIOR_MONTHS = 2
LOOKBACK_MONTHS = RECENT_MONTHS + PRIOR_MONTHS
RECENT_DAYS = RECENT_MONTHS * MONTH_DAYS
LOOKBACK_DAYS = LOOKBACK_MONTHS * MONTH_DAYS


class DayClassTotal(NamedTuple):
    """One day's signed total for one activity class (outflows negative)."""

    day: date
    cls: str
    amount: Decimal


@dataclass(frozen=True)
class BurnWindows:
    """Both windows ending on `as_of`, every bound inclusive. `prior_end` is
    the day before `recent_start`, so no day is in both."""

    recent_start: date
    recent_end: date
    prior_start: date
    prior_end: date


def burn_windows(as_of: date) -> BurnWindows:
    """The trailing `RECENT_DAYS` ending on `as_of`, and the days before them
    back to the start of `LOOKBACK_DAYS` — `as_of` counts as day 1."""
    recent_start = trailing_start(as_of, RECENT_DAYS)
    return BurnWindows(
        recent_start=recent_start,
        recent_end=as_of,
        prior_start=trailing_start(as_of, LOOKBACK_DAYS),
        prior_end=recent_start - timedelta(days=1),
    )


@dataclass(frozen=True)
class Burn:
    """Net spending, as positive outflow, in whole cents."""

    #: Over the trailing thirty days.
    recent: Decimal
    #: Over the sixty days before them, per thirty days.
    prior: Decimal

    @property
    def per_day(self) -> Decimal:
        """The recent burn spread over its days — what a runway divides by."""
        return self.recent / RECENT_DAYS


def burn(days: Iterable[DayClassTotal], as_of: date) -> Burn:
    """The burn as of `as_of`. Rows outside both windows, and rows of a class
    spending does not count, are ignored — so a caller may hand in a wider
    span than one point needs, and a row dated after `as_of` never counts."""
    windows = burn_windows(as_of)
    counted = counted_classes()
    recent = prior = Decimal("0")
    for day, cls, amount in days:
        if cls not in counted:
            continue
        if windows.recent_start <= day <= windows.recent_end:
            recent += amount
        elif windows.prior_start <= day <= windows.prior_end:
            prior += amount
    # `0 - total`, not `-total`: negating Decimal("0") is Decimal("-0"), which
    # serializes as -0.0 and prints as a negative zero on a quiet budget.
    return Burn(
        recent=quantize_cents(Decimal("0") - recent),
        prior=quantize_cents((Decimal("0") - prior) / PRIOR_MONTHS),
    )
