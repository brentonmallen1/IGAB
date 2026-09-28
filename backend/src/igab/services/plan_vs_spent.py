"""Plan vs Spent: what each envelope had, spent and had left, month by month,
with a total per month and a total per category — the plan ledger and the
budget page's balances read once and folded three ways.

Budget vs Actual, Cumulative Variance and Plan vs Reality were three reports
over one dataset at three grains: a category over a window, a month over
every category, and the category-month matrix. So they are one report. The
matrix is the body; its row of month totals is what Cumulative Variance drew;
its column of category totals is what Budget vs Actual listed.

**Carryover counts** (`domain.plan`, owner's call 2026-09-28). A month
carries in what the month before had left, as the budget page does, and is
over only when the envelope went negative. It used to judge each month's
assignment alone, so an envelope funded once and spent over several months
read over plan in every one of them and was named chronic, while the budget
page showed it fine all along.

**Every total is its months walked** (`domain.plan.across_months`): a
category's Total starts from what the first complete month carried in and
ends at what the last one left; a month total adds its cells across
categories; the window's headline adds the categories' Totals.

Pure: takes `plan_ledger`'s output, the budget page's Available for each
category (`BudgetService.envelope_series`) and the window, returns the served
shape. The rules are `domain.plan`'s — `envelope_outcome` for a month,
`across_months` for a span, `is_chronic` for the flag — and `PlanMonth.quiet`
says which rows exist.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal

from igab.domain.carryover import next_carryover
from igab.domain.dates import ReportWindow
from igab.domain.money import quantize_cents
from igab.domain.plan import (
    CHRONIC_WINDOW,
    EnvelopeOutcome,
    across_months,
    envelope_outcome,
    is_chronic,
)
from igab.services.plan_ledger import PlanCategory, PlanMonth

ZERO = Decimal("0")

#: A category's Available month by month, as the budget page states it: the
#: month BEFORE the first month read, then each month read. None where the
#: page states no figure (before an import it cannot walk back through).
Balances = Mapping[uuid.UUID, Sequence[Decimal | None]]


def walk(
    cat: PlanCategory, months: Sequence[date], available: Sequence[Decimal | None] | None
) -> list[tuple[PlanMonth, EnvelopeOutcome]]:
    """One envelope's months in order, each carrying in what the one before
    left. `available` aligns with `[month before months[0], *months]`; a
    category with none (absent from the balances) is walked from the ledger
    alone, from nothing carried in."""
    if available is None:
        available = [None] * (len(months) + 1)
    before = available[0]
    carried: Decimal | None = None if before is None else next_carryover(before)
    out: list[tuple[PlanMonth, EnvelopeOutcome]] = []
    for m, left in zip(months, available[1:], strict=True):
        cell = cat.months.get(m) or PlanMonth()
        outcome = envelope_outcome(
            carried_in=carried,
            assigned=cell.assigned,
            moved_in=cell.moved_in,
            moved_out=cell.moved_out,
            spent=cell.spent,
            left=left,
        )
        out.append((cell, outcome))
        carried = next_carryover(outcome.left)
    return out


def _quiet(cat: PlanCategory) -> bool:
    """No month with anything assigned, moved or spent (`PlanMonth.quiet`).

    Month by month, not the months netted: 300 assigned in June and taken
    back in July nets to nothing, and is still a row that says so."""
    return all(cell.quiet for cell in cat.months.values())


def _span(pairs: Sequence[tuple[PlanMonth, EnvelopeOutcome]]) -> dict:
    """One category over a run of months — the Total column, and the AI's
    `budget_vs_actual` row. The one statement of a category's span.

    `over` is the server's, so no reader decides "overspent" from the
    figures again (a drained envelope drew as a red overrun that way)."""
    outcome = across_months([o for _, o in pairs])
    return {
        "carried_in": outcome.carried_in,
        "assigned": sum((c.assigned for c, _ in pairs), ZERO),
        "moved_in": sum((c.moved_in for c, _ in pairs), ZERO),
        "moved_out": sum((c.moved_out for c, _ in pairs), ZERO),
        "funded": outcome.funded,
        "spent": outcome.spent,
        "other": outcome.other,
        "left": outcome.left,
        "overspent": outcome.overspent,
        "over": outcome.over,
        "estimated": outcome.estimated,
    }


#: The figures a set of categories adds up — a month total, the headline.
_SUMMED = ("assigned", "moved_in", "moved_out", "funded", "spent", "other", "left", "overspent")


def _window_sums(totals: Iterable[dict]) -> dict:
    """The categories' totals added up — so a headline cannot say what the
    rows under it do not."""
    totals = list(totals)
    return {f"total_{key}": sum((t[key] for t in totals), ZERO) for key in _SUMMED}


def budget_vs_actual(
    ledger: Mapping[uuid.UUID, PlanCategory], months: Sequence[date], balances: Balances
) -> dict:
    """Each category over `months`, walked month by month.

    The Total column over any months a caller names — the AI's
    `budget_vs_actual` tool asks for arbitrary dates, widened to the whole
    months they touch (`domain.dates.months_touched`). A category with no
    activity at all (`PlanMonth.quiet`) is not a row; one whose money was all
    moved out is — a mortgage paid by a principal transfer is on plan, not
    missing."""
    categories: list[dict] = []
    for cat in ledger.values():
        if _quiet(cat):
            continue
        categories.append(
            {
                "category_id": str(cat.category_id),
                "category_name": cat.name,
                "category_group_name": cat.group,
                **_span(walk(cat, months, balances.get(cat.category_id))),
            }
        )
    categories.sort(key=lambda c: (-c["overspent"], -c["spent"], c["category_name"]))
    return {"categories": categories, **_window_sums(categories)}


@dataclass
class _MonthTotal:
    carried_in: Decimal = ZERO
    assigned: Decimal = ZERO
    moved_in: Decimal = ZERO
    moved_out: Decimal = ZERO
    funded: Decimal = ZERO
    spent: Decimal = ZERO
    other: Decimal = ZERO
    left: Decimal = ZERO
    overspent: Decimal = ZERO
    #: Categories over this month — never in the running month.
    over: int = 0

    def add(self, cell: PlanMonth, outcome: EnvelopeOutcome, *, over: bool) -> None:
        self.carried_in += outcome.carried_in or ZERO
        self.assigned += cell.assigned
        self.moved_in += cell.moved_in
        self.moved_out += cell.moved_out
        self.funded += outcome.funded
        self.spent += outcome.spent
        self.other += outcome.other
        self.left += outcome.left
        self.overspent += outcome.overspent
        self.over += int(over)


def plan_vs_spent(
    ledger: Mapping[uuid.UUID, PlanCategory], window: ReportWindow, balances: Balances
) -> dict:
    """The matrix, its month totals and its category totals.

    `balances` is each category's Available over `[month before window.start,
    *window.axis]` — the budget page's own figures, which each cell's `left`
    is. A cell is over by `envelope_outcome` — negative by a dollar and 1% of
    what it was funded with — and a category is chronic by `plan.is_chronic`
    over the window's last `CHRONIC_WINDOW` complete months. The Guide's
    checkup reads the served flag.

    The running month is drawn beside the complete ones, and no verdict or
    total reads it — a cell's `over`, chronic, months over, a month total's
    count over, the Total column and the headline sums all read complete
    months alone. A month whose assignment is all in and whose spending is a
    week old is neither over nor under yet.

    A category with no active month — nothing assigned, moved or spent
    anywhere in the window, the running month included (`PlanMonth.quiet`) —
    is not a row, whatever it holds.
    """
    per_month = {m: _MonthTotal() for m in window.axis}
    categories: list[dict] = []
    for cat in ledger.values():
        row = _category_row(cat, window, balances.get(cat.category_id), per_month)
        if row is not None:
            categories.append(row)
    categories.sort(
        key=lambda c: (
            not c["chronic"],
            -c["months_over"],
            -c["total"]["overspent"],
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
        **_window_sums(c["total"] for c in categories),
        "chronic_count": sum(int(c["chronic"]) for c in categories),
    }


def _category_row(
    cat: PlanCategory,
    window: ReportWindow,
    available: Sequence[Decimal | None] | None,
    per_month: dict,
) -> dict | None:
    """One category's row of the matrix and its total over the complete
    months, adding each cell to its month's total on the way. None for a
    category with no active month."""
    if _quiet(cat):
        return None
    recent = set(window.complete[-CHRONIC_WINDOW:])
    monthly: list[dict] = []
    months_over = months_active = recent_over = 0
    over_total = ZERO
    complete: list[tuple[PlanMonth, EnvelopeOutcome]] = []
    for m, (cell, outcome) in zip(window.axis, walk(cat, window.axis, available), strict=True):
        # A month is drawn when anything moved OR the envelope held money:
        # a balance carried through a quiet month is what it had, not nothing.
        active = not cell.quiet or outcome.left != ZERO or bool(outcome.carried_in)
        running = window.is_running(m)
        over = outcome.over and not running
        per_month[m].add(cell, outcome, over=active and over)
        if not running:
            complete.append((cell, outcome))
            if active:
                months_active += 1
                if over:
                    months_over += 1
                    over_total += outcome.overspent
                    recent_over += int(m in recent)
        monthly.append(
            {
                "month": m,
                "carried_in": outcome.carried_in,
                "assigned": cell.assigned,
                "moved_in": cell.moved_in,
                "moved_out": cell.moved_out,
                "funded": outcome.funded,
                "spent": outcome.spent,
                "other": outcome.other,
                "left": outcome.left,
                "overspent": outcome.overspent,
                "over": over,
                "active": active,
                "estimated": outcome.estimated,
            }
        )
    return {
        "category_id": str(cat.category_id),
        "category_name": cat.name,
        "category_group_name": cat.group,
        "monthly": monthly,
        "months_over": months_over,
        "months_active": months_active,
        "avg_overspend": quantize_cents(over_total / months_over) if months_over else ZERO,
        "chronic": is_chronic(recent_over),
        "total": _span(complete),
    }


def _month_rows(per_month: dict[date, _MonthTotal], window: ReportWindow) -> list[dict]:
    """The totals row: each month's cells summed across categories."""
    rows = []
    for m in window.axis:
        mt = per_month[m]
        figures = {f.name: getattr(mt, f.name) for f in fields(mt) if f.name != "over"}
        rows.append(
            {
                "month": m,
                "partial_month": window.is_running(m),
                **figures,
                "categories_over": mt.over,
            }
        )
    return rows
