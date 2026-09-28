"""Did a category's spending fit its plan? One answer for every plan-vs-actual
report.

**The plan floors at zero.** A NEGATIVE assignment is money moved back OUT of
the envelope — a plan being reduced, not a household overspending — and
`spent > assigned` read it as the latter: drain 300 from an envelope that spent
nothing and `0 > -300` flagged it, so an envelope with no spending at all could
be reported as a chronic overspender. Do it in three months and Plan vs Reality
named it the household's worst habit.

Plan vs Reality learned that first and Budget vs Actual did not. Budget vs
Actual served `assigned - spent` unfloored and its chart decided "overspent"
for itself from `spent > assigned`, so over one drained envelope the two
reports gave opposite verdicts: neutral on one screen, a red 300 overrun on
the other, first under "Sort by overspent" and reported to the AI as -300. The
verdict lives here now and both reports serve it; the chart reads it.

**Money moved INTO an envelope raises its plan** — the mirror of the floor.
A transfer from savings into a Medical envelope, a bonus deposit filed to a
Savings envelope: the household funded that envelope as surely as by
assigning to it, and the budget page's Available says so. Read as nothing,
the 2,000 of savings that paid a 2,000 bill made the bill a 2,000 overrun,
every large red Plan vs Reality cell was one, and a Budget vs Actual row
read twenty times over its plan where the budget page showed the envelope a
few dollars short. A
REFUND is different: it is spending coming back, so it lowers spent. Which is
which is the row's activity class (`plan_effect`).

**Money moved OUT of an envelope lowers its plan** — the mirror of money
moved in (owner's call, 2026-09-26). A transfer to a brokerage, a principal
payment to a tracked loan, filed to an envelope nobody tagged as savings or
debt: the household took that money back out of the plan as surely as by
un-assigning it, and the budget page's Available says so. Read as nothing, a
Mortgage envelope assigned 1,500 and paid by a 1,500 principal transfer read
1,500 underspent every month, a plan the household had kept to the dollar.

**One floor, over the whole plan**: `max(assigned + moved_in - moved_out, 0)`.
Not a floor per term: money moved out past what the period planned is the
envelope drawing down a balance it carried in, which a period's plan cannot
see, exactly as a negative assignment is. Unfloored, that leaves a negative
plan every dollar of spending overruns, so an envelope drained into a
brokerage with nothing spent read "over" — the drained-envelope bug above,
arriving by a transfer instead of an assignment.

Pure: takes the figures at whatever grain the report plans in — a month for
a Plan vs Spent cell, the whole window for its Total column — and returns the
verdict.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from igab.domain.activity_class import ActivityClass, counted_classes

ZERO = Decimal("0")

#: How far past its plan a category must go before it is OVER. Both, not
#: either: a dollar, and a hundredth of the plan. Without it a mortgage paid
#: from an envelope assigned a few cents short read "over" three months
#: running and was named a chronic overspender — on a real budget, more than
#: one chronic flag in five was rounding. The dollar floor is what
#: keeps a small plan's cents quiet; the percentage is what keeps a large
#: plan's rounding quiet. A category with no plan is over as soon as it has
#: spent a dollar (1% of nothing is nothing).
OVER_BY_AT_LEAST = Decimal("1.00")
OVER_SHARE_AT_LEAST = Decimal("0.01")

#: "Chronic" is over plan in at least `CHRONIC_MONTHS` of the last
#: `CHRONIC_WINDOW` months the report reads — a plan habitually wrong rather
#: than a month unlucky. Plan vs Spent serves the flag and the Guide's
#: checkup reads it (`guide.service.checkup`); neither decides it again.
CHRONIC_MONTHS = 3
CHRONIC_WINDOW = 6


@dataclass(frozen=True)
class PlanOutcome:
    #: What the category planned to spend: the assignment plus money moved
    #: in, less money moved out, floored at zero.
    plan: Decimal
    #: `plan - spent`, unrounded and untolerated — the arithmetic. Whether it
    #: is bad news is `over`, never the sign: a few cents past a plan is
    #: negative here and on plan there.
    variance: Decimal
    #: Spending exceeded the plan by at least `OVER_BY_AT_LEAST` and
    #: `OVER_SHARE_AT_LEAST` of it — the one meaning of "over" the matrix
    #: tint, the chronic count and the Total column's verdict all read.
    over: bool

    @property
    def variance_pct(self) -> float | None:
        """Variance as a share of the plan; None where there was no plan to
        measure against, rather than a division by zero or a sign flip from
        a negative denominator.

        None, not 0.0: Budget vs Actual printed "0.0%" for spending nobody
        planned, which is what a category that spent its plan to the cent
        also prints."""
        return float(self.variance / self.plan * 100) if self.plan > ZERO else None


def total_variance(outcomes: Iterable[PlanOutcome]) -> Decimal:
    """What a set of categories came to against their plans: the sum of each
    one's floored verdict.

    Not `sum(assigned) - sum(spent)`. That headline read beside rows floored
    per category disagreed with them whenever an envelope was drained: 300
    moved out of one envelope and 300 overspent in another nets to 0 raw,
    while the rows say one is on plan and the other 300 over.
    """
    return sum((o.variance for o in outcomes), ZERO)


def plan_outcome(
    assigned: Decimal, spent: Decimal, *, moved_in: Decimal, moved_out: Decimal
) -> PlanOutcome:
    """The verdict for one category over one planning period.

    `assigned` is the budget assignments, `moved_in` and `moved_out` what
    `plan_effect` counts as money moved into and out of the envelope (both
    non-negative), and `spent` the net spent — negative only when refunds
    beat spending, which leaves the plan with room to spare, as the budget
    page's Available does.

    Both movements are required: a caller that forgot `moved_out` would
    report a debt-paying envelope as underspent by its whole payment.
    """
    plan = max(assigned + moved_in - moved_out, ZERO)
    overrun = spent - plan
    over = overrun >= OVER_BY_AT_LEAST and overrun >= plan * OVER_SHARE_AT_LEAST
    return PlanOutcome(plan=plan, variance=plan - spent, over=over)


def is_chronic(months_over_recently: int, *, sinking_fund: bool) -> bool:
    """Whether a category is a chronic overspender, given how many of the last
    `CHRONIC_WINDOW` months it was over.

    **A sinking fund never is.** Its whole design is months of saving and one
    month of paying the bill: the envelope is "over" its monthly assignment
    every time the premium lands, which is the plan working. Four of those in
    six months — quarterly tax, say — named the household's most disciplined
    envelope its worst habit.
    """
    return not sinking_fund and months_over_recently >= CHRONIC_MONTHS


class PlanEffect(NamedTuple):
    """What one row (or one bucket of like rows) does to a plan report."""

    #: Added to spent: an outflow positive, a refund negative.
    spent: Decimal
    #: Added to the plan: money moved into the envelope.
    moved_in: Decimal
    #: Taken off the plan: money moved out of the envelope that is not spent.
    #: Non-negative, like `moved_in`.
    moved_out: Decimal


NO_EFFECT = PlanEffect(ZERO, ZERO, ZERO)


def plan_effect(amount: Decimal, cls: str, *, savings_envelope: bool) -> PlanEffect:
    """What a row filed to a planned envelope (`txn_filters.PLAN_LEDGER_ROW`)
    does to that envelope's plan report — the one statement of it. Every
    Plan vs Spent figure, Category History's Spent, Volatility and
    Anomalies read it.

    `amount` is signed (outflow negative); `cls` the row's `ACTIVITY_CLASS`;
    `savings_envelope` whether its category is a savings category
    (`category_filters.IS_SAVINGS_CATEGORY`). Linear in `amount`, so a bucket
    of rows sharing all three facts may be passed as its sum.

    - **Spending, either sign, is spent.** A refund is spending coming back,
      so it lowers spent — the budget page nets it, and so does every other
      spending figure. It used to be dropped, which drew a returned purchase
      as the whole purchase.
    - **Money leaving a savings envelope is spent, whatever its class.** The
      household planned that money to leave; see
      `activity_class.PLANNED_SPEND_TAG_KEYS` and #182 for the phantom
      underspend counting it as nothing made. This is the only statement of
      that exception — `money_moves.counts_as_planned_spend_by_tag` asks it
      here rather than restating it.
    - **A starting balance does nothing.** It is where an account's counting
      begins, not money that moved, in either direction.
    - **Anything else arriving raises the plan**: a transfer from savings, a
      deposit filed to the envelope, a loan draw spent through it. It funds
      the envelope exactly as an assignment does — the mirror of a negative
      assignment lowering it (`plan_outcome`).
    - **Anything else leaving lowers the plan**: a transfer to a brokerage
      out of an untagged envelope, a principal payment from an envelope not
      tagged Debt principal. It is not spent — it is saving, or paying down
      a debt, which no spending figure counts — but it was not left unspent
      either. It used to do nothing, so the envelope read underspent by the
      whole transfer.
    """
    if cls in counted_classes():
        return PlanEffect(spent=-amount, moved_in=ZERO, moved_out=ZERO)
    if cls == ActivityClass.OPENING_BALANCE.value:
        return NO_EFFECT
    if amount < ZERO:
        if savings_envelope:
            return PlanEffect(spent=-amount, moved_in=ZERO, moved_out=ZERO)
        return PlanEffect(spent=ZERO, moved_in=ZERO, moved_out=-amount)
    if amount > ZERO:
        return PlanEffect(spent=ZERO, moved_in=amount, moved_out=ZERO)
    return NO_EFFECT
