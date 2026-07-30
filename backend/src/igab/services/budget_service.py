import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from igab.db.models import Category
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.ownership import require_in_budget

if TYPE_CHECKING:
    from igab.repositories.budget_move_repo import BudgetMoveRepository


def _prev_month(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def _months_back(d: date, n: int) -> list[date]:
    months = []
    cur = _prev_month(d)
    for _ in range(n):
        months.append(cur)
        cur = _prev_month(cur)
    return months


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def last_of_month(d: date) -> date:
    import calendar

    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last_day)


@dataclass
class CategoryBalance:
    category_id: uuid.UUID
    month: date
    assigned: Decimal
    activity: Decimal
    available: Decimal


@dataclass
class CategoryHistory:
    category_id: uuid.UUID
    last_month_assigned: Decimal
    last_month_spent: Decimal
    average_assigned: Decimal
    average_spent: Decimal
    months_included: int


@dataclass
class BudgetSummary:
    to_be_assigned: Decimal
    total_assigned: Decimal
    total_activity: Decimal
    total_overspent: Decimal
    category_balances: list[CategoryBalance]


@dataclass
class CoverOverspentItem:
    category_id: uuid.UUID
    category_name: str
    overspent: Decimal
    proposed_addition: Decimal
    remaining_after: Decimal


@dataclass
class CoverOverspentPreview:
    items: list[CoverOverspentItem]
    total_overspent: Decimal
    total_addition: Decimal
    tba_before: Decimal
    tba_after: Decimal


def distribute_cover(
    shortfalls: dict[uuid.UUID, Decimal],
    available_tba: Decimal,
) -> dict[uuid.UUID, Decimal]:
    """Distribute TBA across overspent categories, proportionally when short.

    When TBA covers the total shortfall, every category is covered in full.
    When short, each category gets its proportional share rounded DOWN to
    cents — unlike fill-targets' half-even rounding, this guarantees the sum
    never exceeds TBA (apply hard-rejects overshoot, so a preview must never
    propose one). Leftover cents stay in TBA.
    """
    available_tba = max(Decimal("0"), available_tba)
    total_shortfall = sum(shortfalls.values(), Decimal("0"))
    result: dict[uuid.UUID, Decimal] = {}
    for cat_id, needed in shortfalls.items():
        if total_shortfall <= 0 or available_tba <= 0:
            proposed = Decimal("0")
        elif total_shortfall <= available_tba:
            proposed = needed
        else:
            # Multiply before dividing: needed/total loses exactness (1/3 ...),
            # and rounding an exact share like 100.00 down to 99.99 leaks cents.
            share = needed * available_tba / total_shortfall
            proposed = min(needed, share.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        result[cat_id] = proposed
    return result


class BudgetService:
    def __init__(
        self,
        account_repo: AccountRepository,
        category_repo: CategoryRepository,
        category_group_repo: CategoryGroupRepository,
        assignment_repo: BudgetAssignmentRepository,
        transaction_repo: TransactionRepository,
        move_repo: "BudgetMoveRepository | None" = None,
    ) -> None:
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.category_group_repo = category_group_repo
        self.assignment_repo = assignment_repo
        self.transaction_repo = transaction_repo
        self.move_repo = move_repo

    async def get_category_balance(
        self,
        category_id: uuid.UUID,
        month: date,
        activity_by_month: dict[date, Decimal] | None = None,
    ) -> CategoryBalance:
        """
        Compute available balance for a category through the given month.

        Replicates YNAB's overspending-coverage behavior: when a category ends a
        month negative (cash overspent), that negative amount is covered from TBA
        and the carryover into the next month is floored at zero.
        """
        month_start = first_of_month(month)

        assignments = await self.assignment_repo.get_for_category(
            category_id, through_month=month_start
        )
        this_assigned = next(
            (a.assigned for a in assignments if a.month == month_start), Decimal("0")
        )

        if activity_by_month is None:
            activity_by_month = await self.transaction_repo.sum_by_category_by_month(
                category_id, end_date=last_of_month(month_start)
            )

        this_activity = activity_by_month.get(month_start, Decimal("0"))

        # Month-by-month simulation flooring carryover at 0 between months.
        # This matches YNAB: cash overspending in month M is deducted from TBA
        # and the category starts month M+1 at zero rather than carrying negative.
        assignments_by_month = {a.month: a.assigned for a in assignments}
        all_months = sorted(set(assignments_by_month) | set(activity_by_month))
        carryover = Decimal("0")
        end_of_month = Decimal("0")
        last_simulated: date | None = None
        for m in all_months:
            if m > month_start:
                break
            end_of_month = (
                carryover
                + assignments_by_month.get(m, Decimal("0"))
                + activity_by_month.get(m, Decimal("0"))
            )
            # Floor the carryover into the next month; current month can show negative
            carryover = max(Decimal("0"), end_of_month)
            last_simulated = m

        # Only the month with its own data may show negative; any later month
        # starts from the floored carryover (overspending was absorbed by TBA).
        available = end_of_month if last_simulated == month_start else carryover

        return CategoryBalance(
            category_id=category_id,
            month=month_start,
            assigned=this_assigned,
            activity=this_activity,
            available=available,
        )

    async def get_budget_summary(self, budget_id: uuid.UUID, month: date) -> BudgetSummary:
        """
        Compute TBA and all category balances for a given month.

        TBA = sum(on-budget account balances) - sum(category balances)
        """
        month_start = first_of_month(month)

        # On-budget account total
        accounts = await self.account_repo.get_on_budget(budget_id)
        total_account_balance = Decimal("0")
        for acc in accounts:
            total_account_balance += await self.account_repo.get_balance(acc.id)

        # All category balances
        categories = await self.category_repo.get_all(budget_id, include_hidden=True)
        groups = await self.category_group_repo.get_all(budget_id, include_hidden=True)
        system_group_ids = {g.id for g in groups if g.is_system}

        # Batch per-month activity for all categories in a single query
        all_activity_by_month = await self.transaction_repo.sum_all_categories_by_month(
            [cat.id for cat in categories], end_date=last_of_month(month_start)
        )

        balances: list[CategoryBalance] = []
        total_category_balance = Decimal("0")
        total_assigned = Decimal("0")
        total_activity = Decimal("0")
        total_overspent = Decimal("0")

        for cat in categories:
            bal = await self.get_category_balance(
                cat.id, month_start, activity_by_month=all_activity_by_month.get(cat.id, {})
            )
            balances.append(bal)
            # Exclude system (Income) categories: income adds to TBA, not reduces it
            if cat.category_group_id not in system_group_ids:
                total_category_balance += bal.available
                if bal.available < 0:
                    total_overspent += -bal.available
            total_assigned += bal.assigned
            total_activity += bal.activity

        to_be_assigned = total_account_balance - total_category_balance

        return BudgetSummary(
            to_be_assigned=to_be_assigned,
            total_assigned=total_assigned,
            total_activity=total_activity,
            total_overspent=total_overspent,
            category_balances=balances,
        )

    async def set_assignment(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
        month: date,
        amount: Decimal,
    ) -> None:
        month_start = first_of_month(month)
        assignment = await self.assignment_repo.get_or_create(
            budget_id=budget_id,
            category_id=category_id,
            month=month_start,
        )
        await self.assignment_repo.update(assignment.id, assigned=amount)

    async def get_category_history(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
        current_month: date,
        lookback: int = 6,
    ) -> "CategoryHistory":
        # Guard: category_id may arrive from a request body (batch history),
        # bypassing the route's BudgetAccess check. Reject foreign categories
        # so history cannot be read across budgets.
        await require_in_budget(
            self.category_repo.session, Category, category_id, budget_id, "Category"
        )
        month_start = first_of_month(current_month)
        past_months = _months_back(month_start, lookback)

        assignments = await self.assignment_repo.get_for_category(category_id)
        assigned_by_month = {a.month: a.assigned for a in assignments}

        # Activity through the most RECENT past month (past_months[0]); the
        # current month's spending must not leak into history.
        activity_by_month = await self.transaction_repo.sum_by_category_by_month(
            category_id, end_date=last_of_month(past_months[0] if past_months else month_start)
        )
        # activity is negative for spending; flip sign for "spent" values
        spent_by_month = {m: -v for m, v in activity_by_month.items() if v < 0}

        last_month = past_months[0] if past_months else None
        last_assigned = (
            assigned_by_month.get(last_month, Decimal("0")) if last_month else Decimal("0")
        )
        last_spent = spent_by_month.get(last_month, Decimal("0")) if last_month else Decimal("0")

        months_with_data = [m for m in past_months if m in assigned_by_month or m in spent_by_month]
        n = len(months_with_data) if months_with_data else 1
        zero = Decimal("0")
        avg_assigned = sum((assigned_by_month.get(m, zero) for m in past_months), zero) / n
        avg_spent = sum((spent_by_month.get(m, zero) for m in past_months), zero) / n

        return CategoryHistory(
            category_id=category_id,
            last_month_assigned=last_assigned,
            last_month_spent=last_spent,
            average_assigned=avg_assigned.quantize(Decimal("0.01")),
            average_spent=avg_spent.quantize(Decimal("0.01")),
            months_included=n,
        )

    async def auto_assign(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
        month: date,
        action: str,
    ) -> None:
        history = await self.get_category_history(budget_id, category_id, month)
        amount_map = {
            "last_month_assigned": history.last_month_assigned,
            "last_month_spent": history.last_month_spent,
            "average_assigned": history.average_assigned,
            "average_spent": history.average_spent,
            "reset": Decimal("0"),
        }
        amount = amount_map.get(action, Decimal("0"))
        await self.set_assignment(budget_id, category_id, month, amount)

    async def move_money(
        self,
        budget_id: uuid.UUID,
        from_category_id: uuid.UUID | None,
        to_category_id: uuid.UUID | None,
        amount: Decimal,
        month: date,
    ) -> None:
        """Move funds between envelopes by adjusting assignments.

        A NULL side means To-Be-Assigned: from=None pulls money out of TBA
        into a category; to=None releases a category's money back to TBA.
        The move is recorded in the budget_moves audit trail.
        """
        from igab.domain.exceptions import InvariantViolation

        if amount <= 0:
            raise InvariantViolation("Amount to move must be positive")
        if from_category_id == to_category_id:
            raise InvariantViolation("Choose two different envelopes")

        month_start = first_of_month(month)

        for category_id in (from_category_id, to_category_id):
            if category_id is None:
                continue
            category = await self.category_repo.get(category_id)
            if category is None or str(category.budget_id) != str(budget_id):
                raise InvariantViolation("Category does not belong to this budget")

        if from_category_id is not None:
            from_assignment = await self.assignment_repo.get_or_create(
                budget_id, from_category_id, month_start
            )
            await self.assignment_repo.update(
                from_assignment.id, assigned=from_assignment.assigned - amount
            )
        if to_category_id is not None:
            to_assignment = await self.assignment_repo.get_or_create(
                budget_id, to_category_id, month_start
            )
            await self.assignment_repo.update(
                to_assignment.id, assigned=to_assignment.assigned + amount
            )

        if self.move_repo is not None:
            await self.move_repo.create(
                budget_id=budget_id,
                month=month_start,
                from_category_id=from_category_id,
                to_category_id=to_category_id,
                amount=amount,
            )

    async def get_move_history(self, budget_id: uuid.UUID, month: date):
        if self.move_repo is None:
            return []
        return await self.move_repo.get_for_month(budget_id, first_of_month(month))

    async def _overspent_shortfalls(
        self, budget_id: uuid.UUID, month: date
    ) -> tuple["BudgetSummary", dict[uuid.UUID, Decimal]]:
        """Current summary plus {category_id: overspent amount} for non-system
        categories. Hidden categories are included on purpose — they participate
        in the TBA math, so covering them is required to zero out overspending."""
        summary = await self.get_budget_summary(budget_id, month)
        groups = await self.category_group_repo.get_all(budget_id, include_hidden=True)
        system_group_ids = {g.id for g in groups if g.is_system}
        categories = await self.category_repo.get_all(budget_id, include_hidden=True)
        non_system_ids = {c.id for c in categories if c.category_group_id not in system_group_ids}
        shortfalls = {
            b.category_id: -b.available
            for b in summary.category_balances
            if b.available < 0 and b.category_id in non_system_ids
        }
        return summary, shortfalls

    async def cover_overspent_preview(
        self, budget_id: uuid.UUID, month: date
    ) -> CoverOverspentPreview:
        summary, shortfalls = await self._overspent_shortfalls(budget_id, month)
        proposed = distribute_cover(shortfalls, summary.to_be_assigned)

        categories = await self.category_repo.get_all(budget_id, include_hidden=True)
        name_map = {c.id: c.name for c in categories}

        items = [
            CoverOverspentItem(
                category_id=cat_id,
                category_name=name_map.get(cat_id, "Unknown"),
                overspent=shortfall,
                proposed_addition=proposed[cat_id],
                remaining_after=shortfall - proposed[cat_id],
            )
            for cat_id, shortfall in shortfalls.items()
        ]
        items.sort(key=lambda i: (-i.proposed_addition, str(i.category_id)))
        total_addition = sum((i.proposed_addition for i in items), Decimal("0"))

        return CoverOverspentPreview(
            items=items,
            total_overspent=summary.total_overspent,
            total_addition=total_addition,
            tba_before=summary.to_be_assigned,
            tba_after=summary.to_be_assigned - total_addition,
        )

    async def cover_overspent_apply(
        self,
        budget_id: uuid.UUID,
        month: date,
        items: list[tuple[uuid.UUID, Decimal]],
    ) -> None:
        """Apply a cover-overspent preview by moving money from TBA.

        Re-validates against fresh balances so a stale preview (transactions or
        assignments changed since it was fetched) cannot over-assign: each
        addition is capped by the category's current shortfall and the total by
        current TBA. Each cover routes through move_money, so it lands in the
        budget_moves audit trail as "TBA → category".
        """
        from igab.domain.exceptions import InvariantViolation

        summary, shortfalls = await self._overspent_shortfalls(budget_id, month)
        available_tba = max(Decimal("0"), summary.to_be_assigned)

        to_apply = [(cat_id, amount) for cat_id, amount in items if amount > 0]
        total = sum((amount for _, amount in to_apply), Decimal("0"))
        if total > available_tba:
            raise InvariantViolation(
                "Cover amount exceeds Ready to Assign — refresh the preview and try again"
            )
        for cat_id, amount in to_apply:
            shortfall = shortfalls.get(cat_id, Decimal("0"))
            if amount > shortfall:
                raise InvariantViolation(
                    "Cover amount exceeds current overspending — refresh the preview and try again"
                )

        for cat_id, amount in to_apply:
            await self.move_money(budget_id, None, cat_id, amount, month)
