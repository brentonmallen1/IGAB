"""What each category planned, had moved in, and spent, month by month — the
one read behind every figure that holds a category's spending to its plan.

Budget vs Actual, Cumulative Variance and Plan vs Reality each ran their own
pair of queries over assignments and spending. The predicates had been
extracted (`BUDGETED_ENVELOPE`, then `planned_spend_filter`), but the reading
of a row was still spelled three times — `abs(amount)` of an outflow — and all
three dropped every row filed INTO an envelope. A transfer from savings that
paid a medical bill read as the whole bill overspent, on all three at once,
while the budget page showed the envelope on plan.

So the rows are read once, here, and what each does to the plan is
`domain.plan.plan_effect`. Category History, Volatility and Anomalies read
the same `spent`, so "spent" in a category means one thing on every report
that shows it beside a plan or measures its swing.

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

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import BudgetAssignment, Category, CategoryGroup, Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, apply_class_joins
from igab.domain.dates import month_end, month_start, month_starts
from igab.domain.money import quantize_cents
from igab.domain.plan import plan_effect
from igab.repositories.category_filters import (
    BUDGETED_ENVELOPE,
    IS_SAVINGS_CATEGORY,
    IS_SINKING_FUND,
)
from igab.repositories.txn_filters import PLAN_LEDGER_ROW
from igab.services.report_scope import scoped

ZERO = Decimal("0")


@dataclass
class PlanMonth:
    """One category's month. `spent` is net: negative only when its refunds
    beat its spending."""

    assigned: Decimal = ZERO
    moved_in: Decimal = ZERO
    spent: Decimal = ZERO

    @property
    def quiet(self) -> bool:
        """Nothing planned, moved or spent — the "$0 / $0" a report drops."""
        return self.assigned == ZERO and self.moved_in == ZERO and self.spent == ZERO


@dataclass
class PlanCategory:
    category_id: uuid.UUID
    name: str
    group: str
    #: Tagged Long-term expense (`IS_SINKING_FUND`): never chronic, and not
    #: tested for anomalies — a bill it saved for is its plan working.
    sinking_fund: bool
    months: dict[date, PlanMonth] = field(default_factory=dict)

    def month(self, m: date) -> PlanMonth:
        return self.months.setdefault(m, PlanMonth())

    def total(self) -> PlanMonth:
        out = PlanMonth()
        for cell in self.months.values():
            out.assigned += cell.assigned
            out.moved_in += cell.moved_in
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
    month_col = func.date_trunc(literal_column("'month'"), Transaction.date)
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
            Transaction.date >= start,
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
        if effect.spent == ZERO and effect.moved_in == ZERO:
            continue
        cell = entry(r.category_id, r.category_name, r.group_name, r.sinking).month(
            _as_date(r.month)
        )
        cell.spent += effect.spent
        cell.moved_in += effect.moved_in
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
    """One category's spent and moved-in money over a month list, and its
    average spent over the list's complete months."""

    spent: list[Decimal]
    moved_in: list[Decimal]
    average_spent: Decimal
    months_averaged: int


async def spent_series(
    session: AsyncSession,
    budget_id: uuid.UUID,
    category_id: uuid.UUID,
    month_list: Sequence[date],
    today: date,
) -> SpentSeries:
    """Category History's Spent: the ledger for one category, month by month.

    The page drew `max(-activity, 0)`: the budget page's net Activity with
    every net-positive month clipped to nothing. Activity nets the money moved
    in, so a medical bill paid by a transfer from savings read as no spending
    at all there, and as the whole bill on Plan vs Reality one tab over. This
    is the plan family's figure, so the two tabs agree.

    The average is over the COMPLETE months in the list: the month in
    progress is month-to-date, and averaging it in read a steady category as
    falling every month until the month closed.
    """
    ledger = await plan_ledger(
        session,
        budget_id,
        month_list[0],
        month_end(month_list[-1]),
        category_ids=[category_id],
        assignments=False,
    )
    cat = ledger.get(category_id)
    cells = [cat.months.get(m, PlanMonth()) if cat else PlanMonth() for m in month_list]
    running = month_start(today)
    complete = [c.spent for m, c in zip(month_list, cells, strict=True) if m < running]
    average = quantize_cents(sum(complete, ZERO) / len(complete)) if complete else ZERO
    return SpentSeries(
        spent=[c.spent for c in cells],
        moved_in=[c.moved_in for c in cells],
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
