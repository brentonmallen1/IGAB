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

Pure: takes the two figures at whatever grain the report plans in — a month
for Plan vs Reality, the whole window for Budget vs Actual — and returns the
verdict.
"""

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class PlanOutcome:
    #: What the category planned to spend: the assignment, floored at zero.
    plan: Decimal
    #: `plan - spent`. Negative only when real spending exceeded a real plan,
    #: which is what every screen tints red.
    variance: Decimal
    #: Spending exceeded the plan.
    over: bool

    @property
    def variance_pct(self) -> float:
        """Variance as a share of the plan; 0 where there was no plan to
        measure against, rather than a division by zero or a sign flip from
        a negative denominator."""
        return float(self.variance / self.plan * 100) if self.plan > ZERO else 0.0


def plan_outcome(assigned: Decimal, spent: Decimal) -> PlanOutcome:
    """The verdict for one category over one planning period.

    `spent` is a magnitude — what `PLANNED_SPEND_ROW` counts, always >= 0.
    """
    plan = max(assigned, ZERO)
    return PlanOutcome(plan=plan, variance=plan - spent, over=spent > plan)
