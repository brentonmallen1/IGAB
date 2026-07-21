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
        # Leaf rows: split parents legitimately have no category, while an
        # uncategorized split child is a real gap the user should fill.
        # Transfer legs whose partner account is OFF-budget are spending and
        # need a category too; on-budget↔on-budget legs never do.
        from sqlalchemy import or_
        from sqlalchemy.orm import aliased

        partner = aliased(Transaction)
        partner_account = aliased(Account)
        result = await self.session.execute(
            select(func.count(Transaction.id))
            .select_from(Transaction)
            .outerjoin(partner, Transaction.transfer_id == partner.id)
            .outerjoin(partner_account, partner.account_id == partner_account.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.is_split == False,  # noqa: E712
                Transaction.category_id.is_(None),
                Transaction.cleared != "pending",
                or_(
                    Transaction.transfer_id.is_(None),
                    partner_account.on_budget == False,  # noqa: E712
                ),
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

    async def get_linked_simplefin_accounts(self, budget_id: uuid.UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.simplefin_account_id.isnot(None),
                Account.is_deleted == False,  # noqa: E712
                Account.is_closed == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get_sync_status(self, budget_id: uuid.UUID) -> list[Account]:
        """Return all accounts with SimpleFIN link info for sidebar status display."""
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.simplefin_account_id.isnot(None),
                Account.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())
