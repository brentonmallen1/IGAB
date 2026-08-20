import uuid

from sqlalchemy import func, select

from igab.db.models import Account, AccountType
from igab.repositories.base import BaseRepository


class AccountTypeRepository(BaseRepository[AccountType]):
    model = AccountType

    async def get_all(self, budget_id: uuid.UUID) -> list[AccountType]:
        result = await self.session.execute(
            select(AccountType)
            .where(AccountType.budget_id == budget_id)
            .order_by(AccountType.is_system.desc(), AccountType.sort_order, AccountType.label)
        )
        return list(result.scalars().all())

    async def get_by_key(self, budget_id: uuid.UUID, key: str) -> AccountType | None:
        result = await self.session.execute(
            select(AccountType).where(AccountType.budget_id == budget_id, AccountType.key == key)
        )
        return result.scalar_one_or_none()

    async def account_count(self, type_id: uuid.UUID) -> int:
        """Accounts referencing the type — soft-deleted rows included, since
        they still hold the FK and would block a hard delete."""
        result = await self.session.execute(
            select(func.count()).where(Account.account_type_id == type_id)
        )
        return result.scalar_one()

    async def hard_delete(self, type_id: uuid.UUID) -> None:
        row = await self.get_or_raise(type_id)
        await self.session.delete(row)
        await self.session.flush()
