"""What each category planned, had moved in, and spent, month by month — the
one read behind every figure that holds a category's spending to its plan.

Budget vs Actual, Cumulative Variance and Plan vs Reality each ran their own
pair of queries over assignments and spending. The predicates had been
extracted (`BUDGETED_ENVELOPE`, then `planned_spend_filter`), but the reading
of a row was still spelled three times — `abs(amount)` of an outflow — and all
three dropped every row filed INTO an envelope. A transfer from savings that
paid a medical bill read as the whole bill overspent, on all three at once,
while the budget page showed the envelope on plan.

So the rows are read once, here, and what each does to the plan — spent,
moved in, moved out, or nothing — is `domain.plan.plan_effect`. Category
History, Volatility and Anomalies read the same `spent`, so "spent" in a
category means one thing on every report that shows it beside a plan or
measures its swing.

Orchestration only: two queries and a fold. The rule is `plan_effect`; the
row shape is `txn_filters.PLAN_LEDGER_ROW`; the envelope rules are
`category_filters.BUDGETED_ENVELOPE` / `PLANNED_ENVELOPE`.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import BudgetAssignment, Category, CategoryGroup, Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, apply_class_joins
from igab.domain.dates import ReportWindow, month_starts
from igab.domain.money import quantize_cents
from igab.domain.plan import NO_EFFECT, plan_effect
from igab.repositories.category_filters import (
    BUDGETED_ENVELOPE,
    IS_SAVINGS_CATEGORY,
    IS_SINKING_FUND,
)
from igab.repositories.txn_filters import BUDGET_MONTH, PLAN_LEDGER_ROW
from igab.services.report_scope import scoped

ZERO = Decimal("0")


@dataclass
class PlanMonth:
    """One category's month. `spent` is net: negative only when its refunds
    beat its spending."""

    assigned: Decimal = ZERO
    moved_in: Decimal = ZERO
    #: Non-negative: money moved out of the envelope that was not spent.
    moved_out: Decimal = ZERO
    spent: Decimal = ZERO

    @property
    def quiet(self) -> bool:
        """Nothing assigned, moved in, moved out or spent: the one statement of
        "this row has no activity", which Plan vs Spent reads to leave a cell
        (and a row) empty, and the AI's `budget_vs_actual` to drop a category.

        All four, not the floored plan and spent. Read that way, a Mortgage
        envelope assigned 1,500 and paid by a 1,500 principal transfer — plan
        0, spent 0 — vanished from both reports, which reads as the mortgage
        missing; it is a row that says "assigned 1,500, moved out 1,500, on
        plan". A drained envelope (a negative assignment) is a row for the
        same reason."""
        return (
            self.assigned == ZERO
            and self.moved_in == ZERO
            and self.moved_out == ZERO
            and self.spent == ZERO
        )


@dataclass
class PlanCategory:
    category_id: uuid.UUID
    name: str
    group: str
    #: Tagged Long-term expense (`IS_SINKING_FUND`): not tested for
    #: anomalies — a bill it saved for is its plan working, not a spike.
    sinking_fund: bool
    months: dict[date, PlanMonth] = field(default_factory=dict)

    def month(self, m: date) -> PlanMonth:
        return self.months.setdefault(m, PlanMonth())

    def total(self) -> PlanMonth:
        out = PlanMonth()
        for cell in self.months.values():
            out.assigned += cell.assigned
            out.moved_in += cell.moved_in
            out.moved_out += cell.moved_out
            out.spent += cell.spent
        return out


def _as_date(value) -> date:
    return value.date() if hasattr(value, "date") and callable(value.date) else value


async def plan_ledger(
    session: AsyncSession,
    budget_id: uuid.UUID,
    start: date,
    end: date,
    *,
    category_ids: Sequence[uuid.UUID] | None = None,
    assignments: bool = True,
) -> dict[uuid.UUID, PlanCategory]:
    """Every category with a planned or ledger row in the window, by month.

    Rows are read from `start` through `end`; assignments for every month the
    window touches. `assignments=False` reads the spending side alone — for
    Volatility and Anomalies, which have no plan to hold it to.

    A category appears once it has an assignment or a row with an effect; its
    months are only those that carried one — callers zero-fill the grid they
    report on.
    """
    ledger: dict[uuid.UUID, PlanCategory] = {}

    def entry(category_id, name: str, group: str, sinking: bool) -> PlanCategory:
        if category_id not in ledger:
            ledger[category_id] = PlanCategory(category_id, name, group, bool(sinking))
        return ledger[category_id]

    if assignments:
        assign_q = (
            select(
                BudgetAssignment.category_id,
                BudgetAssignment.month,
                func.sum(BudgetAssignment.assigned).label("assigned"),
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
                IS_SINKING_FUND.label("sinking"),
            )
            .join(Category, BudgetAssignment.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month.in_(month_starts(start, end)),
                BUDGETED_ENVELOPE,
            )
            .group_by(
                BudgetAssignment.category_id,
                BudgetAssignment.month,
                Category.name,
                CategoryGroup.name,
                IS_SINKING_FUND,
            )
        )
        assign_q = scoped(assign_q, BudgetAssignment.category_id, category_ids)
        for r in (await session.execute(assign_q)).all():
            cat = entry(r.category_id, r.category_name, r.group_name, r.sinking)
            cat.month(_as_date(r.month)).assigned += Decimal(str(r.assigned))

    # Grouped by everything `plan_effect` reads, so each bucket's sum stands
    # for its rows exactly (the rule is linear within a bucket).
    #
    # By `BUDGET_MONTH`, the envelope's own bucket: a month's activity is
    # paired with that month's assignment here, and a late arrival dated in
    # the anchor month is paid for by the import month's envelope. The lower
    # bound admits it by the same test — for every other row the bucket is
    # the first of its own month, so `BUDGET_MONTH >= start` never reaches a
    # row `date >= start` would not.
    month_col = BUDGET_MONTH
    cls = ACTIVITY_CLASS
    savings = IS_SAVINGS_CATEGORY
    inflow = Transaction.amount > 0
    rows_q = (
        select(
            Transaction.category_id,
            month_col.label("month"),
            cls.label("cls"),
            savings.label("savings_envelope"),
            inflow.label("inflow"),
            func.sum(Transaction.amount).label("amount"),
            Category.name.label("category_name"),
            CategoryGroup.name.label("group_name"),
            IS_SINKING_FUND.label("sinking"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
        .where(
            Transaction.budget_id == budget_id,
            or_(Transaction.date >= start, BUDGET_MONTH >= start),
            Transaction.date <= end,
            PLAN_LEDGER_ROW,
        )
        .group_by(
            Transaction.category_id,
            month_col,
            cls,
            savings,
            inflow,
            Category.name,
            CategoryGroup.name,
            IS_SINKING_FUND,
        )
    )
    rows_q = scoped(apply_class_joins(rows_q), Transaction.category_id, category_ids)
    for r in (await session.execute(rows_q)).all():
        effect = plan_effect(
            Decimal(str(r.amount)), r.cls, savings_envelope=bool(r.savings_envelope)
        )
        if effect == NO_EFFECT:
            continue
        cell = entry(r.category_id, r.category_name, r.group_name, r.sinking).month(
            _as_date(r.month)
        )
        cell.spent += effect.spent
        cell.moved_in += effect.moved_in
        cell.moved_out += effect.moved_out
    return ledger


class LedgerRow(NamedTuple):
    """One category-month of net spent, in the shape a transaction row has —
    `amount` signed, an outflow negative — so the statistics that read rows
    (`report_stats.volatility_stats`) read the ledger unchanged."""

    date: date
    amount: Decimal
    category_id: uuid.UUID
    category_name: str
    group_name: str


@dataclass(frozen=True)
class SpentSeries:
    """One category's spent and moved money over a month list, and its
    average spent over the list's complete months."""

    spent: list[Decimal]
    moved_in: list[Decimal]
    moved_out: list[Decimal]
    average_spent: Decimal
    months_averaged: int


async def spent_series(
    session: AsyncSession,
    budget_id: uuid.UUID,
    category_id: uuid.UUID,
    window: ReportWindow,
    today: date,
) -> SpentSeries:
    """Category History's Spent: the ledger for one category, month by month.

    The page drew `max(-activity, 0)`: the budget page's net Activity with
    every net-positive month clipped to nothing. Activity nets the money moved
    in, so a medical bill paid by a transfer from savings read as no spending
    at all there, and as the whole bill on Plan vs Reality one tab over. This
    is the plan family's figure, so the two tabs agree.

    One figure per month of `window.axis`, and the average over
    `window.complete` alone — the window's own statement of which months are
    over. The month in progress is month-to-date, and averaging it in read a
    steady category as falling every month until the month closed. This
    spelled "complete" again, as "before the running month", beside the
    window that already said it.
    """
    ledger = await plan_ledger(
        session,
        budget_id,
        window.start,
        today,
        category_ids=[category_id],
        assignments=False,
    )
    cat = ledger.get(category_id)
    cells = [cat.months.get(m, PlanMonth()) if cat else PlanMonth() for m in window.axis]
    complete = [cat.months.get(m, PlanMonth()).spent if cat else ZERO for m in window.complete]
    average = quantize_cents(sum(complete, ZERO) / len(complete)) if complete else ZERO
    return SpentSeries(
        spent=[c.spent for c in cells],
        moved_in=[c.moved_in for c in cells],
        moved_out=[c.moved_out for c in cells],
        average_spent=average,
        months_averaged=len(complete),
    )


def ledger_rows(ledger: Mapping[uuid.UUID, PlanCategory]) -> list[LedgerRow]:
    """Every category-month that spent something (net), as rows."""
    return [
        LedgerRow(month, -cell.spent, cat.category_id, cat.name, cat.group)
        for cat in ledger.values()
        for month, cell in sorted(cat.months.items())
        if cell.spent != ZERO
    ]
