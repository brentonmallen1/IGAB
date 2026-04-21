import uuid
from decimal import Decimal

from sqlalchemy import func, select, update

from igab.db.models import Account, Transaction
from igab.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def get_all(self, budget_id: uuid.UUID, include_closed: bool = False) -> list[Account]:
        q = select(Account).where(
            Account.budget_id == budget_id,
            Account.is_deleted == False,  # noqa: E712
        )
        if not include_closed:
            q = q.where(Account.is_closed == False)  # noqa: E712
        q = q.order_by(Account.sort_order, Account.name)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_balance(self, account_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared != "pending",
            )
        )
        return result.scalar_one()

    async def get_cleared_balance(self, account_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared.in_(["cleared", "reconciled"]),
            )
        )
        return result.scalar_one()

    async def get_uncategorized_count(self, account_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.category_id.is_(None),
                Transaction.cleared != "pending",
                Transaction.transfer_id.is_(None),
            )
        )
        return result.scalar_one()

    async def get_on_budget(self, budget_id: uuid.UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.on_budget == True,  # noqa: E712
                Account.is_deleted == False,  # noqa: E712
                Account.is_closed == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def soft_delete(self, id: uuid.UUID) -> None:
        await self.session.execute(
            update(Transaction)
            .where(Transaction.account_id == id, Transaction.is_deleted == False)  # noqa: E712
            .values(is_deleted=True)
        )
        await super().soft_delete(id)

    async def get_by_simplefin_id(self, budget_id: uuid.UUID, simplefin_id: str) -> Account | None:
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.simplefin_account_id == simplefin_id,
                Account.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()
