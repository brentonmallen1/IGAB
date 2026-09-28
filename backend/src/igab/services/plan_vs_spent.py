"""Plan vs Spent: each category's plan against its spending, month by month,
with a total per month and a total per category — the plan ledger read once
and folded three ways.

Budget vs Actual, Cumulative Variance and Plan vs Reality were three reports
over this one dataset — assigned against spent, carryover ignored — at three
grains: a category over a window, a month over every category, and the
category-month matrix. Their twelve-month totals were identical, their titles
were synonyms, they sat in two nav groups, and a reader could not tell which
one answered "am I keeping to my plan?". So they are one report. The matrix
is the body; its row of month totals is what Cumulative Variance drew; its
column of category totals is what Budget vs Actual listed.

Pure: takes `plan_ledger`'s output and the window, returns the served shape.
The rules are `domain.plan`'s — `plan_outcome` for every verdict,
`is_chronic` for the flag, `total_variance` for a headline — and
`PlanMonth.quiet` says which rows exist.

**The two totals floor at different grains, on purpose.** A month total is
its cells' verdicts summed, each plan floored at zero for its month (what
Cumulative Variance served); a category total floors once, over the window's
sums (what Budget vs Actual served). They agree wherever no month's plan went
below zero. Where one did — 300 moved back out of an envelope the month after
it was assigned — the month grain cannot see the assignment the move undid and
reads the envelope 300 under plan, while the window sees both and reads it on
plan. So the running total at the last complete month is never below the
window's total variance, and exceeds it by at most the money floored away in
single months; `tests/unit/services/test_plan_vs_spent.py` pins both.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from igab.domain.dates import ReportWindow
from igab.domain.money import quantize_cents
from igab.domain.plan import CHRONIC_WINDOW, is_chronic, plan_outcome, total_variance
from igab.services.plan_ledger import PlanCategory, PlanMonth

ZERO = Decimal("0")


def window_total(t: PlanMonth) -> dict:
    """One category over a window: what it planned, spent, and the verdict at
    that grain — the Total column, and the AI's `budget_vs_actual` row.

    `over` is the server's, so no reader decides "overspent" from
    `spent > assigned` again (a drained envelope drew as a red overrun that
    way). `plan` is served so no reader adds the moved money itself."""
    outcome = plan_outcome(t.assigned, t.spent, moved_in=t.moved_in, moved_out=t.moved_out)
    return {
        "assigned": t.assigned,
        "moved_in": t.moved_in,
        "moved_out": t.moved_out,
        "plan": outcome.plan,
        "spent": t.spent,
        "variance": outcome.variance,
        "variance_pct": outcome.variance_pct,
        "over": outcome.over,
    }


def _window_sums(totals: Iterable[PlanMonth]) -> dict:
    """Categories' window totals summed — so a headline cannot say what the
    rows under it do not. `total_variance` is the rows' floored verdicts
    summed (`plan.total_variance`), never `total_assigned - total_spent`,
    which disagrees with the rows wherever an envelope was drained."""
    totals = list(totals)
    outcomes = [
        plan_outcome(t.assigned, t.spent, moved_in=t.moved_in, moved_out=t.moved_out)
        for t in totals
    ]
    return {
        "total_assigned": sum((t.assigned for t in totals), ZERO),
        "total_moved_in": sum((t.moved_in for t in totals), ZERO),
        "total_moved_out": sum((t.moved_out for t in totals), ZERO),
        "total_plan": sum((o.plan for o in outcomes), ZERO),
        "total_spent": sum((t.spent for t in totals), ZERO),
        "total_variance": total_variance(outcomes),
    }


def budget_vs_actual(ledger: Mapping[uuid.UUID, PlanCategory]) -> dict:
    """Each category's plan for a whole ledger window against what it spent.

    The Total column over any window a caller names — the AI's
    `budget_vs_actual` tool asks it for arbitrary dates. A category with no
    activity at all (`PlanMonth.quiet`) is not a row; one whose plan floors to
    nothing is — a mortgage paid by a principal transfer is on plan, not
    missing."""
    categories: list[dict] = []
    totals: list[PlanMonth] = []
    for cat in ledger.values():
        t = cat.total()
        if t.quiet:
            continue
        totals.append(t)
        categories.append(
            {
                "category_id": str(cat.category_id),
                "category_name": cat.name,
                "category_group_name": cat.group,
                **window_total(t),
            }
        )
    categories.sort(key=lambda c: (-c["spent"], c["category_name"]))
    return {"categories": categories, **_window_sums(totals)}


@dataclass
class _MonthTotal:
    assigned: Decimal = ZERO
    moved_in: Decimal = ZERO
    moved_out: Decimal = ZERO
    plan: Decimal = ZERO
    spent: Decimal = ZERO
    variance: Decimal = ZERO
    #: Categories over plan this month — never in the running month.
    over: int = 0

    def add(self, cell: PlanMonth, plan: Decimal, variance: Decimal, *, over: bool) -> None:
        self.assigned += cell.assigned
        self.moved_in += cell.moved_in
        self.moved_out += cell.moved_out
        self.plan += plan
        self.spent += cell.spent
        self.variance += variance
        self.over += int(over)


def plan_vs_spent(ledger: Mapping[uuid.UUID, PlanCategory], window: ReportWindow) -> dict:
    """The matrix, its month totals and its category totals.

    Deliberately ignores carryover: this measures monthly plan discipline
    (did the month's spending fit the month's plan?), not envelope health — a
    category living off January's surplus still reads over plan in February
    if nothing was assigned or moved in.

    A cell is over by `plan_outcome` — past the plan by a dollar and 1% of it
    — and a category is chronic by `plan.is_chronic` over the window's last
    `CHRONIC_WINDOW` complete months. The Guide's checkup reads the served
    flag, so saving, a transfer into an envelope, a few cents of rounding or
    a sinking fund paying its bill can never be reported as a bad habit.

    The running month is drawn beside the complete ones, and no verdict or
    total reads it — a cell's `over`, chronic, months over, a month total's
    count over, the running total, the Total column and the headline sums all
    read complete months alone. A month whose assignment is all in and whose
    spending is a week old is neither over nor under yet; counting it made
    the running total leap "under budget" at the start of every month.

    A category with no active month — nothing assigned, moved or spent
    anywhere in the window, the running month included (`PlanMonth.quiet`) —
    is not a row.
    """
    per_month = {m: _MonthTotal() for m in window.axis}
    categories: list[dict] = []
    totals: list[PlanMonth] = []
    for cat in ledger.values():
        found = _category_row(cat, window, per_month)
        if found is None:
            continue
        row, t = found
        categories.append(row)
        totals.append(t)
    categories.sort(
        key=lambda c: (
            not c["chronic"],
            -c["months_over"],
            -c["total"]["spent"],
            c["category_name"],
        )
    )
    return {
        "months": window.axis,
        # Which column is still being written: the page marks it "so far"
        # rather than guessing.
        "running_month": window.running,
        # What the Total column and the headline sums cover, for the drills
        # that open them: the complete months, or None when there are none.
        "totals_start": window.complete[0] if window.complete else None,
        "totals_end": window.complete_end if window.complete else None,
        "categories": categories,
        "month_totals": _month_rows(per_month, window),
        **_window_sums(totals),
        "chronic_count": sum(int(c["chronic"]) for c in categories),
    }


def _category_row(
    cat: PlanCategory, window: ReportWindow, per_month: dict
) -> tuple[dict, PlanMonth] | None:
    """One category's row of the matrix and its total over the complete
    months, adding each cell to its month's total on the way. None for a
    category with no active month."""
    recent = set(window.complete[-CHRONIC_WINDOW:])
    monthly: list[dict] = []
    months_over = months_active = recent_over = 0
    over_total = ZERO
    shown = False
    t = PlanMonth()
    for m in window.axis:
        cell = cat.months.get(m) or PlanMonth()
        # One verdict for the chronic count, the cell's tint, its variance and
        # the month total: a drained envelope was once coloured overspent
        # while the chronic flag beside it disagreed.
        outcome = plan_outcome(
            cell.assigned, cell.spent, moved_in=cell.moved_in, moved_out=cell.moved_out
        )
        active = not cell.quiet
        running = window.is_running(m)
        over = outcome.over and not running
        shown = shown or active
        per_month[m].add(cell, outcome.plan, outcome.variance, over=active and over)
        if not running:
            t.assigned += cell.assigned
            t.moved_in += cell.moved_in
            t.moved_out += cell.moved_out
            t.spent += cell.spent
            if active:
                months_active += 1
                if over:
                    months_over += 1
                    over_total += -outcome.variance
                    recent_over += int(m in recent)
        monthly.append(
            {
                "month": m,
                "assigned": cell.assigned,
                "moved_in": cell.moved_in,
                "moved_out": cell.moved_out,
                "plan": outcome.plan,
                "spent": cell.spent,
                "variance": outcome.variance,
                "over": over,
                "active": active,
            }
        )
    if not shown:
        return None
    row = {
        "category_id": str(cat.category_id),
        "category_name": cat.name,
        "category_group_name": cat.group,
        "monthly": monthly,
        "months_over": months_over,
        "months_active": months_active,
        "avg_overspend": quantize_cents(over_total / months_over) if months_over else ZERO,
        "chronic": is_chronic(recent_over, sinking_fund=cat.sinking_fund),
        "sinking_fund": cat.sinking_fund,
        "total": window_total(t),
    }
    return row, t


def _month_rows(per_month: dict, window: ReportWindow) -> list[dict]:
    """The totals row: each month's cells summed, and the running total of
    the complete months through it (None on the running month)."""
    rows = []
    cumulative = ZERO
    for m in window.axis:
        mt = per_month[m]
        running = window.is_running(m)
        if not running:
            cumulative += mt.variance
        rows.append(
            {
                "month": m,
                "partial_month": running,
                "assigned": mt.assigned,
                "moved_in": mt.moved_in,
                "moved_out": mt.moved_out,
                "plan": mt.plan,
                "spent": mt.spent,
                "variance": mt.variance,
                "cumulative_variance": None if running else cumulative,
                "categories_over": mt.over,
            }
        )
    return rows
