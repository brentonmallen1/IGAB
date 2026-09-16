"""What "saved" means: money moved into savings, plus what kept-here Savings
envelopes came to hold.

A Savings category counts in one of two ways (`category_filters.SAVINGS_ROLE`):

- **sent out** — its outflows are savings the moment they leave. The
  classifier's rule 1 classes them SAVINGS, so they are already in the
  SAVINGS-class flows and nothing here adds to them.
- **kept here** — the envelope's balance *is* the savings. Assigning to it is
  saving; spending from it is dissaving; moving it on to a tracked savings
  account is neither, because the money is still saved, just somewhere else.

So the savings figure has two parts, and every consumer adds the same two:

    saved = moved + held

**moved** is the SAVINGS-class flows: `class_magnitude(buckets, SAVINGS)` over
`CLASS_TOTAL_ROW`, exactly what the savings rate always divided.

**held** is how much the kept-here envelopes' balances grew over the window,
read off the Budget page's own Available:

    held = next_carryover(balance at the end) − next_carryover(balance before the start)

Why this nets correctly, case by case (the integration suite names each):

- *Assign 500*: held +500, moved 0 → saved +500.
- *Spend 120 from it*: held −120 (and SPENDING +120) → saved −120.
- *Move 300 on to a tracked HYSA, filed to the envelope*: the row classes
  SAVINGS (moved +300) and leaves the envelope (held −300) → saved 0.
- *Withdraw X from the HYSA into checking, then assign X back*: the
  uncategorized inflow is a SAVINGS-class inflow (moved −X) that lands in
  Ready to Assign; the assignment is held +X → saved 0.

**Why the floor.** `next_carryover` is the page's own write-off: a month that
ends overspent is absorbed by Ready to Assign and the next month starts at
zero. The money that covered it was never the envelope's. A pass-through
kept-here envelope that was never assigned and sends $800 to a tracked HYSA
ends at −800: moved +800, held max(0, −800) − 0 = 0, saved 800 — once, not
twice, and not zero. Spending from an empty kept-here envelope holds 0 for
the same reason: Ready to Assign paid for it.

**Unknown balances.** On an imported budget a month before the import whose
balance the history cannot reproduce has no Available (`EnvelopeSeries.
unrecovered_through`). A step with an unknown end holds 0, so that step's
saved is its moved alone — the plan's "falls back to flows". The bound: held
is understated by at most the unknown balances' change, and only for steps
that touch a month before the envelope's recovered history.

Pure: the balances come in, the figures go out. `services/savings_held.py`
reads them from the budget.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from igab.domain.activity_class import SAVINGS_CLASSES, ActivityClass, class_magnitude
from igab.domain.carryover import next_carryover
from igab.domain.dates import add_months, clamped_month_end, month_end

ZERO = Decimal("0")

#: The contributor reason for a kept-here envelope's held change. Not an
#: `ActivityReason` member: no SQL rule emits it, and every member of that enum
#: must fire on a leaf row — the precedent is `activity_class.SPLIT_REASON_TEXT`.
HELD_REASON = "held_in_savings_envelope"
HELD_REASON_LABEL = "held in a Savings envelope"


def balance_at(available: Decimal | None, activity_after: Decimal) -> Decimal | None:
    """An envelope's balance at the end of a day, from its month's Available.

    `available` is the page's figure for the day's month, which already holds
    the month's assignment (assignments count from the first of their month)
    and every register row dated in the month — including rows later than the
    day. `activity_after` is those later rows' signed total, so a future-dated
    row in the current month is not held until its date. For a month-end day
    it is zero and the page's figure stands.

    None stays None: an unrecovered month has no balance to cut.
    """
    if available is None:
        return None
    return available - activity_after


def held_change(before: Decimal | None, after: Decimal | None) -> Decimal:
    """What one step between two balances held, through the page's floor.

    Zero when either end is unknown — see the module docstring for the bound.
    """
    if before is None or after is None:
        return ZERO
    return next_carryover(after) - next_carryover(before)


def held_over(balances: Sequence[Decimal | None]) -> Decimal:
    """The held change along a chain of balances, one step at a time.

    With every balance known the steps telescope to `held_change(first,
    last)` exactly, so a window cut at month ends holds what its months hold,
    added up. Stepping rather than reading only the two ends is what keeps
    that true across an unknown balance: a month whose start is unrecovered
    holds 0, and the whole window is still the sum of its months.
    """
    return sum(
        (held_change(a, b) for a, b in zip(balances, balances[1:], strict=False)),
        ZERO,
    )


def window_cuts(start: date, end: date) -> list[date]:
    """The days a window [start, end] is read at: the day before it starts,
    every month end inside it, and its last day.

    Month ends because the page states Available per month, so each step
    between two cuts is a step between two page figures — which is what lets
    an unknown month hold 0 without zeroing the months around it (`held_over`).
    A window that ends before it starts is the one cut, and holds nothing.
    """
    cuts = [start - timedelta(days=1)]
    month = start.replace(day=1)
    while end >= start and (last := month_end(month)) < end:
        if last >= start:
            cuts.append(last)
        month = add_months(month, 1)
    if end >= start:
        cuts.append(end)
    return cuts


def month_cuts(months: Sequence[date], today: date) -> list[date]:
    """Cuts for a monthly series: the day before the first month, then each
    month's end — the running month's clamped to today, so a future-dated row
    is not held before its date (`clamped_month_end`). Never earlier than the
    cut before it, so a month wholly after today holds nothing.

    `held_over` of these steps, month by month, is the monthly held series,
    and its sum is the held change over `window_cuts(first month, today)`.
    """
    if not months:
        return []
    cuts = [months[0] - timedelta(days=1)]
    for m in months:
        cuts.append(max(cuts[-1], clamped_month_end(m, today)))
    return cuts


@dataclass(frozen=True)
class SavingsFigure:
    """One window's savings figure in its two parts."""

    #: SAVINGS-class flows, as a magnitude: positive for money that left.
    moved: Decimal
    #: The kept-here envelopes' floored balance change.
    held: Decimal

    @property
    def total(self) -> Decimal:
        return self.moved + self.held


#: What each savings rate divides by income: saving alone, or saving plus the
#: principal paid down. Paying down a mortgage and funding a brokerage both
#: build net worth, but people think about them differently, so both are shown.
#: Held money is saving, so it joins every numerator that holds SAVINGS.
SAVINGS_RATE_NUMERATORS: dict[str, tuple[ActivityClass, ...]] = {
    "savings_rate": (ActivityClass.SAVINGS,),
    "savings_rate_with_debt": SAVINGS_CLASSES,
}


def savings_rates(buckets: Mapping[str, Decimal], held: Decimal) -> dict[str, float | None]:
    """Both savings rates from class buckets (class value -> signed sum) and
    the window's held change:

        savings_rate           = (moved + held) / income
        savings_rate_with_debt = (moved + held + debt_principal) / income

    One division for the Savings Rate report, the Overview card and the
    Guide's worked month, so the example cannot teach a rate the report would
    not compute. `held` has no default: a path that forgets it must fail, not
    quietly report a kept-here household's savings as zero.

    With no income the rate is None rather than 0: "no income recorded" and
    "saved nothing" are different facts, and a chart should show a gap rather
    than a floor.
    """
    income = buckets.get(ActivityClass.INCOME.value, ZERO)
    rates: dict[str, float | None] = {}
    for key, classes in SAVINGS_RATE_NUMERATORS.items():
        numerator = sum((class_magnitude(buckets, c) for c in classes), ZERO)
        if ActivityClass.SAVINGS in classes:
            numerator += held
        rates[key] = None if income <= 0 else float(numerator / income)
    return rates
