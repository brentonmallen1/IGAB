import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.db.models import Account, Category, Payee, ScheduledTransaction
from igab.domain.dates import add_months
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.services.ownership import require_in_budget
from igab.services.transaction_service import TransactionCreate, TransactionService
from igab.utils.clock import today_utc


@dataclass
class ScheduledTransactionCreate:
    account_id: uuid.UUID
    amount: Decimal
    frequency: str
    start_date: date
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    end_date: date | None = None
    auto_create: bool = False
    days_before_reminder: int = 3


class ScheduledTransactionService:
    def __init__(
        self,
        repo: ScheduledTransactionRepository,
        txn_service: TransactionService,
    ) -> None:
        self.repo = repo
        self.txn_service = txn_service

    async def list(self, budget_id: uuid.UUID) -> list[ScheduledTransaction]:
        return await self.repo.get_all(budget_id)

    async def create(
        self, budget_id: uuid.UUID, data: ScheduledTransactionCreate
    ) -> ScheduledTransaction:
        await self._validate_budget_refs(
            budget_id, data.account_id, data.category_id, data.payee_id
        )
        return await self.repo.create(
            budget_id=budget_id,
            account_id=data.account_id,
            amount=data.amount,
            payee_id=data.payee_id,
            category_id=data.category_id,
            memo=data.memo,
            frequency=data.frequency,
            start_date=data.start_date,
            end_date=data.end_date,
            auto_create=data.auto_create,
            days_before_reminder=data.days_before_reminder,
            next_occurrence_date=data.start_date,
        )

    async def update(self, id: uuid.UUID, **kwargs) -> ScheduledTransaction:
        if any(k in kwargs for k in ("account_id", "category_id", "payee_id")):
            existing = await self.repo.get(id)
            if existing is not None:
                await self._validate_budget_refs(
                    existing.budget_id,
                    kwargs.get("account_id"),
                    kwargs.get("category_id"),
                    kwargs.get("payee_id"),
                )
        return await self.repo.update(id, **kwargs)

    async def _validate_budget_refs(
        self,
        budget_id: uuid.UUID,
        account_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        payee_id: uuid.UUID | None,
    ) -> None:
        """Reject account/category/payee ids that belong to another budget.

        These arrive from the request body, so the route's ownership guard does
        not cover them.
        """
        session = self.txn_service.session
        await require_in_budget(session, Account, account_id, budget_id, "Account")
        await require_in_budget(session, Category, category_id, budget_id, "Category")
        await require_in_budget(session, Payee, payee_id, budget_id, "Payee")

    async def delete(self, id: uuid.UUID) -> None:
        await self.repo.soft_delete(id)

    async def skip(self, id: uuid.UUID) -> ScheduledTransaction:
        sched = await self.repo.get(id)
        if sched is None:
            return None  # type: ignore
        next_date = calculate_next(sched)
        return await self.repo.update(id, next_occurrence_date=next_date)

    async def enter_now(self, sched_id: uuid.UUID, budget_id: uuid.UUID) -> None:
        sched = await self.repo.get(sched_id)
        if sched is None:
            return
        await self.txn_service.create(
            budget_id,
            TransactionCreate(
                account_id=sched.account_id,
                date=today_utc(),
                amount=sched.amount,
                payee_id=sched.payee_id,
                category_id=sched.category_id,
                memo=sched.memo,
                cleared="uncleared",
                approved=True,
                # A scheduled transfer must materialize BOTH legs
                transfer_account_id=sched.transfer_account_id,
            ),
        )
        next_date = calculate_next(sched)
        await self.repo.update(
            sched_id, last_created_date=today_utc(), next_occurrence_date=next_date
        )

    async def process_due(self, budget_id: uuid.UUID) -> int:
        today = today_utc()
        due = [s for s in await self.repo.get_due(today) if str(s.budget_id) == str(budget_id)]
        created = 0
        for sched in due:
            if sched.end_date and today > sched.end_date:
                await self.repo.soft_delete(sched.id)
                continue
            if sched.auto_create:
                await self.enter_now(sched.id, budget_id)
                created += 1
            else:
                next_date = calculate_next(sched)
                await self.repo.update(sched.id, next_occurrence_date=next_date)
        return created


def calculate_next(sched: ScheduledTransaction) -> date:
    current = sched.next_occurrence_date
    freq = sched.frequency
    if freq == "daily":
        from datetime import timedelta

        return current + timedelta(days=1)
    elif freq == "weekly":
        from datetime import timedelta

        return current + timedelta(weeks=1)
    elif freq == "biweekly":
        from datetime import timedelta

        return current + timedelta(weeks=2)
    elif freq == "monthly":
        return add_months(current, 1)
    elif freq == "yearly":
        # add_months, not `replace(year=...)`: a schedule dated 29 February
        # raised ValueError every leap year and stalled the run.
        return add_months(current, 12)
    return current
