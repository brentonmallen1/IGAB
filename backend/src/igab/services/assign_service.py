"""Bulk assign strategies behind the TBA hero's Assign dropdown.

Each strategy computes, per eligible category, a target assigned value for
the month; the delta between current and target is what moves. Previews,
menu totals, and apply all run through the same builder so the number shown
in the dropdown row, the modal table, and the applied result can never
diverge. Apply recomputes server-side (the request carries no amounts) and
routes every nonzero delta through BudgetService.move_money so each change
lands in the budget_moves audit trail.

Eligibility: non-system, non-hidden categories. Hidden categories are
archived — silently re-funding them via "Assigned Last Month" would move
money into invisible envelopes. (Cover-overspent deliberately still includes
hidden categories; overspending participates in TBA regardless.)
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.db.models import Category, CategoryTarget
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.repositories.target_repo import TargetRepository
from igab.services.budget_service import (
    BudgetService,
    BudgetSummary,
    CategoryBalance,
    CategoryHistory,
    first_of_month,
)
from igab.services.target_service import TargetService

HISTORY_STRATEGIES = (
    "last_month_assigned",
    "last_month_spent",
    "average_assigned",
    "average_spent",
)
ASSIGN_STRATEGIES = (
    "underfunded",
    *HISTORY_STRATEGIES,
    "reduce_overfunded",
    "reset_available",
    "reset_assigned",
)

ZERO = Decimal("0")


def strategy_new_assigned(
    strategy: str,
    current_assigned: Decimal,
    available: Decimal,
    history: CategoryHistory,
    target: CategoryTarget | None = None,
) -> Decimal | None:
    """Target assigned value for one category under a bulk strategy.

    None means the category is untouched by this strategy. History
    strategies SET assigned to the historical value (matching the existing
    per-category auto-assign semantics) — setting below current returns
    money to TBA.
    """
    if strategy == "last_month_assigned":
        return history.last_month_assigned
    if strategy == "last_month_spent":
        return history.last_month_spent
    if strategy == "average_assigned":
        return history.average_assigned
    if strategy == "average_spent":
        return history.average_spent
    if strategy == "reduce_overfunded":
        # Mirror of "underfunded": categories assigned beyond their target
        # come back down to it and the excess returns to TBA. Uses the same
        # definition as the overfunded quick filter (assigned > target
        # amount), so the filter's rows are exactly what this strategy moves.
        if target is not None and current_assigned > target.target_amount:
            return target.target_amount
        return None
    if strategy == "reset_available":
        # Only positive available returns to TBA; overspent categories are
        # Cover Overspending's job. Assigned may legitimately go negative.
        if available > ZERO:
            return current_assigned - available
        return None
    if strategy == "reset_assigned":
        return ZERO if current_assigned != ZERO else None
    raise ValueError(f"Unknown assign strategy: {strategy}")


def distribute_fill(
    shortfalls: dict[uuid.UUID, Decimal],
    available_tba: Decimal,
) -> dict[uuid.UUID, Decimal]:
    """Fill-targets distribution: proportional within TBA, capped per need.

    Byte-identical to the original fill-targets endpoint math (half-even
    cent rounding) so underfunded previews keep their historical behavior.
    """
    available_tba = max(ZERO, available_tba)
    total_shortfall = sum(shortfalls.values(), ZERO)
    result: dict[uuid.UUID, Decimal] = {}
    for cat_id, needed in shortfalls.items():
        if total_shortfall > ZERO:
            proportion = needed / total_shortfall
            proposed = min(needed, (proportion * available_tba).quantize(Decimal("0.01")))
        else:
            proposed = ZERO
        result[cat_id] = proposed
    return result


@dataclass
class AssignPreviewItem:
    category_id: uuid.UUID
    category_name: str
    current_assigned: Decimal
    new_assigned: Decimal
    delta: Decimal


@dataclass
class AssignPreview:
    strategy: str
    items: list[AssignPreviewItem]
    total_amount: Decimal
    total_needed: Decimal | None  # underfunded only: unclamped total need
    to_assign: Decimal
    to_return: Decimal
    tba_before: Decimal
    tba_after: Decimal
    affected_count: int


@dataclass
class AssignTotals:
    month: date
    tba: Decimal
    total_overspent: Decimal
    strategies: list[AssignPreview]


@dataclass
class _AssignContext:
    month: date
    summary: BudgetSummary
    balances: dict[uuid.UUID, CategoryBalance]
    eligible: list[Category]
    histories: dict[uuid.UUID, CategoryHistory]
    targets: dict[uuid.UUID, CategoryTarget]


class AssignService:
    def __init__(
        self,
        budget_service: BudgetService,
        target_repo: TargetRepository,
        target_service: TargetService,
        category_repo: CategoryRepository,
        category_group_repo: CategoryGroupRepository,
    ) -> None:
        self.budget_service = budget_service
        self.target_repo = target_repo
        self.target_service = target_service
        self.category_repo = category_repo
        self.category_group_repo = category_group_repo

    async def _gather(self, budget_id: uuid.UUID, month: date) -> _AssignContext:
        month_start = first_of_month(month)
        summary = await self.budget_service.get_budget_summary(budget_id, month_start)
        balances = {b.category_id: b for b in summary.category_balances}

        # `is_assignable` is served by IS_ASSIGNABLE (category_filters.py) — the
        # same rule the move-money and assign pickers read, so what the client
        # offers and what this endpoint acts on cannot drift. It also closes a
        # gap the group-set rebuild had: get_all filters the category's
        # is_hidden but not the group's, so a hidden group's categories were
        # still eligible here.
        categories = await self.category_repo.get_all(budget_id, include_hidden=False)
        eligible = [c for c in categories if c.is_assignable]

        histories = {
            c.id: await self.budget_service.get_category_history(budget_id, c.id, month_start)
            for c in eligible
        }
        targets = await self.target_repo.get_by_category_ids([c.id for c in eligible])
        target_map = {t.category_id: t for t in targets}

        return _AssignContext(
            month=month_start,
            summary=summary,
            balances=balances,
            eligible=eligible,
            histories=histories,
            targets=target_map,
        )

    def _build_preview(self, ctx: _AssignContext, strategy: str) -> AssignPreview:
        total_needed: Decimal | None = None
        items: list[AssignPreviewItem] = []

        if strategy == "underfunded":
            shortfalls: dict[uuid.UUID, Decimal] = {}
            for cat in ctx.eligible:
                target = ctx.targets.get(cat.id)
                bal = ctx.balances.get(cat.id)
                if target is None or bal is None:
                    continue
                needed = self.target_service.calculate_needed(target, bal.assigned, bal.available)
                if needed > ZERO:
                    shortfalls[cat.id] = needed
            proposed = distribute_fill(shortfalls, ctx.summary.to_be_assigned)
            total_needed = sum(shortfalls.values(), ZERO)
            name_map = {c.id: c.name for c in ctx.eligible}
            for cat_id in shortfalls:
                bal = ctx.balances[cat_id]
                delta = proposed[cat_id]
                # Zero-delta rows stay visible in the preview: they show what
                # a too-small TBA couldn't reach.
                items.append(
                    AssignPreviewItem(
                        category_id=cat_id,
                        category_name=name_map[cat_id],
                        current_assigned=bal.assigned,
                        new_assigned=bal.assigned + delta,
                        delta=delta,
                    )
                )
        else:
            if strategy not in ASSIGN_STRATEGIES:
                raise ValueError(f"Unknown assign strategy: {strategy}")
            for cat in ctx.eligible:
                bal = ctx.balances.get(cat.id)
                current = bal.assigned if bal else ZERO
                available = bal.available if bal else ZERO
                new = strategy_new_assigned(
                    strategy, current, available, ctx.histories[cat.id], ctx.targets.get(cat.id)
                )
                if new is None or new == current:
                    continue
                items.append(
                    AssignPreviewItem(
                        category_id=cat.id,
                        category_name=cat.name,
                        current_assigned=current,
                        new_assigned=new,
                        delta=new - current,
                    )
                )

        items.sort(key=lambda i: (-abs(i.delta), i.category_name))
        to_assign = sum((i.delta for i in items if i.delta > ZERO), ZERO)
        to_return = sum((-i.delta for i in items if i.delta < ZERO), ZERO)
        affected_count = sum(1 for i in items if i.delta != ZERO)

        if strategy == "underfunded":
            total_amount = to_assign
        elif strategy in HISTORY_STRATEGIES:
            # The YNAB-style headline: the total the strategy would leave
            # assigned across every eligible category (unchanged ones included).
            total_amount = ZERO
            for cat in ctx.eligible:
                bal = ctx.balances.get(cat.id)
                current = bal.assigned if bal else ZERO
                available = bal.available if bal else ZERO
                new = strategy_new_assigned(strategy, current, available, ctx.histories[cat.id])
                total_amount += new if new is not None else current
        else:
            # Resets: net amount returned to TBA.
            total_amount = to_return - to_assign

        tba_before = ctx.summary.to_be_assigned
        return AssignPreview(
            strategy=strategy,
            items=items,
            total_amount=total_amount,
            total_needed=total_needed,
            to_assign=to_assign,
            to_return=to_return,
            tba_before=tba_before,
            tba_after=tba_before - to_assign + to_return,
            affected_count=affected_count,
        )

    async def strategy_totals(self, budget_id: uuid.UUID, month: date) -> AssignTotals:
        ctx = await self._gather(budget_id, month)
        return AssignTotals(
            month=ctx.month,
            tba=ctx.summary.to_be_assigned,
            total_overspent=ctx.summary.total_overspent,
            strategies=[self._build_preview(ctx, s) for s in ASSIGN_STRATEGIES],
        )

    async def preview(self, budget_id: uuid.UUID, month: date, strategy: str) -> AssignPreview:
        ctx = await self._gather(budget_id, month)
        return self._build_preview(ctx, strategy)

    async def apply(self, budget_id: uuid.UUID, month: date, strategy: str) -> AssignPreview:
        """Recompute the strategy fresh and apply it through move_money."""
        preview = await self.preview(budget_id, month, strategy)
        with self.budget_service.changes.batch():
            for item in preview.items:
                if item.delta > ZERO:
                    await self.budget_service.move_money(
                        budget_id, None, item.category_id, item.delta, month
                    )
                elif item.delta < ZERO:
                    await self.budget_service.move_money(
                        budget_id, item.category_id, None, -item.delta, month
                    )
        return preview
