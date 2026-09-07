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
from igab.domain.money import quantize_cents
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
    target_duty: Decimal | None = None,
) -> Decimal | None:
    """Target assigned value for one category under a bulk strategy.

    None means the category is untouched by this strategy. History
    strategies SET assigned to the historical value (matching the existing
    per-category auto-assign semantics) — setting below current returns
    money to TBA.

    `target_duty` is the month's duty from `TargetService.duty`, not the
    target's raw amount: a weekly target's duty is the amount times the
    weeks in the month, and pulling back to the weekly figure would strip
    four fifths of a correctly funded envelope.
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
        # Mirror of "underfunded": categories assigned beyond their target come
        # back down to it and the excess returns to TBA.
        #
        # **Bounded by what is still in the envelope.** Money assigned above a
        # target has often been spent, and spent money cannot return to Ready
        # to Assign. Unbounded, this took a category with target 100, assigned
        # 150 and 400 spent — available −250 — down to 100 assigned and −300
        # available: it manufactured 50 of overspending and told the user it
        # was returning 50 of surplus. (That behaviour had a test asserting it,
        # written from the same "assigned > target" reading.)
        #
        # So the row set here is deliberately NARROWER than the overfunded
        # quick filter, which asks only whether assigned exceeds the target: a
        # category over its target with nothing left in it is over-*assigned*,
        # not over-funded, and there is nothing to pull back. Pinned by
        # `test_reduce_overfunded_never_pulls_back_spent_money`.
        if target_duty is None or available <= ZERO:
            return None
        pullback = min(current_assigned - target_duty, available)
        return current_assigned - pullback if pullback > ZERO else None
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
            proposed = min(needed, quantize_cents(proportion * available_tba))
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
    #: Categories this strategy would leave newly in the red, and by how much
    #: in total. Two strategies legitimately do this — the history ones SET
    #: assigned to a past figure, and Reset Assigned zeroes it — so money
    #: already spent from the envelope stops being funded. That is what the
    #: user asked for; a preview that does not say so is the surprise.
    #:
    #: "Newly": a category already overspent before the strategy runs is not
    #: counted, or every preview in an overspent month would carry a warning
    #: about a state it did not create.
    newly_overspent_count: int = 0
    newly_overspent_total: Decimal = ZERO
    # Set by apply(): the change-log batch the moves were recorded under, so
    # the caller can offer an undo of the whole strategy.
    batch_id: uuid.UUID | None = None


@dataclass
class AssignTotals:
    month: date
    tba: Decimal
    #: The same pair `BudgetSummary` serves, in the same words: the whole red,
    #: and how much of it rode onto a card. The dropdown's Cover row and the
    #: hero chip read one client-side implementation over this shape
    #: (frontend `budgetTotals.overspending`), which is what stops the two
    #: from drifting again — they carried `total_overspent_cash` and
    #: `total_overspent` respectively, and disagreed for a release.
    total_overspent: Decimal
    total_overspent_credit: Decimal
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

        # `is_fundable` (IS_FUNDABLE, category_filters.py) — where money may
        # ENTER, which is this endpoint's question. It used to read
        # `is_assignable`, which answers what a *picker* may offer, and the two
        # are not the same envelope set: a card's payment envelope lives in a
        # hidden group, so it failed `is_assignable` and a paydown target set
        # on a card silently never filled. The comment defending the old
        # conflation claimed excluding card envelopes "would" break exactly
        # that; measuring showed it already had.
        #
        # `include_archived=False` still: it filters the category's own flag,
        # and a card envelope's own flag is false — only its group is hidden.
        # An archived envelope is not a target this should fill.
        categories = await self.category_repo.get_all(budget_id, include_archived=False)
        eligible = [c for c in categories if c.is_fundable]

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

    def _duty_for(
        self, ctx: _AssignContext, category_id: uuid.UUID, assigned: Decimal, available: Decimal
    ) -> Decimal | None:
        """The month's duty for a category's target, or None without one."""
        target = ctx.targets.get(category_id)
        if target is None:
            return None
        return self.target_service.duty(
            target, assigned=assigned, available=available, month=ctx.month
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
                needed = self.target_service.calculate_needed(
                    target, bal.assigned, bal.available, month=ctx.month
                )
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
                    strategy,
                    current,
                    available,
                    ctx.histories[cat.id],
                    self._duty_for(ctx, cat.id, current, available),
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

        # What each touched envelope would hold afterwards. `available` moves
        # with `assigned` one for one, which is the same relation
        # `reset_available` inverts to empty an envelope exactly.
        newly_red: list[Decimal] = []
        for item in items:
            bal = ctx.balances.get(item.category_id)
            if bal is None or bal.available < ZERO:
                continue
            after = bal.available + item.delta
            if after < ZERO:
                newly_red.append(-after)

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
            newly_overspent_count=len(newly_red),
            newly_overspent_total=sum(newly_red, ZERO),
        )

    async def strategy_totals(self, budget_id: uuid.UUID, month: date) -> AssignTotals:
        ctx = await self._gather(budget_id, month)
        return AssignTotals(
            month=ctx.month,
            tba=ctx.summary.to_be_assigned,
            total_overspent=ctx.summary.total_overspent,
            total_overspent_credit=ctx.summary.total_overspent_credit,
            strategies=[self._build_preview(ctx, s) for s in ASSIGN_STRATEGIES],
        )

    async def preview(self, budget_id: uuid.UUID, month: date, strategy: str) -> AssignPreview:
        ctx = await self._gather(budget_id, month)
        return self._build_preview(ctx, strategy)

    async def apply(self, budget_id: uuid.UUID, month: date, strategy: str) -> AssignPreview:
        """Recompute the strategy fresh and apply it through move_money."""
        preview = await self.preview(budget_id, month, strategy)
        with self.budget_service.changes.batch() as batch_id:
            preview.batch_id = batch_id
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
