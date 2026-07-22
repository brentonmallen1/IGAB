import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository

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
    category_balances: list[CategoryBalance]


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

        for cat in categories:
            bal = await self.get_category_balance(
                cat.id, month_start, activity_by_month=all_activity_by_month.get(cat.id, {})
            )
            balances.append(bal)
            # Exclude system (Income) categories: income adds to TBA, not reduces it
            if cat.category_group_id not in system_group_ids:
                total_category_balance += bal.available
            total_assigned += bal.assigned
            total_activity += bal.activity

        to_be_assigned = total_account_balance - total_category_balance

        return BudgetSummary(
            to_be_assigned=to_be_assigned,
            total_assigned=total_assigned,
            total_activity=total_activity,
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
        category_id: uuid.UUID,
        current_month: date,
        lookback: int = 6,
    ) -> "CategoryHistory":
        month_start = first_of_month(current_month)
        past_months = _months_back(month_start, lookback)

        assignments = await self.assignment_repo.get_for_category(category_id)
        assigned_by_month = {a.month: a.assigned for a in assignments}

        activity_by_month = await self.transaction_repo.sum_by_category_by_month(
            category_id, end_date=last_of_month(past_months[-1] if past_months else month_start)
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
        history = await self.get_category_history(category_id, month)
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
