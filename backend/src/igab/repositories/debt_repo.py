import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Debt, DebtBalanceSnapshot
from igab.repositories.base import BaseRepository


class DebtRepository(BaseRepository[Debt]):
    model = Debt

    async def get_all(self, budget_id: uuid.UUID) -> list[Debt]:
        result = await self.session.execute(
            select(Debt)
            .where(Debt.budget_id == budget_id, Debt.is_deleted == False)  # noqa: E712
            .order_by(Debt.name)
        )
        return list(result.scalars().all())

    async def get_by_linked_account(self, account_id: uuid.UUID) -> Debt | None:
        result = await self.session.execute(
            select(Debt).where(
                Debt.linked_account_id == account_id,
                Debt.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_snapshots(self, debt_id: uuid.UUID) -> list[DebtBalanceSnapshot]:
        result = await self.session.execute(
            select(DebtBalanceSnapshot)
            .where(DebtBalanceSnapshot.debt_id == debt_id)
            .order_by(DebtBalanceSnapshot.date)
        )
        return list(result.scalars().all())

    async def upsert_snapshot(
        self,
        debt_id: uuid.UUID,
        snapshot_date: date,
        balance: Decimal,
        source: str = "manual",
    ) -> DebtBalanceSnapshot:
        """One snapshot per day: a second entry for the same date replaces it."""
        result = await self.session.execute(
            select(DebtBalanceSnapshot).where(
                DebtBalanceSnapshot.debt_id == debt_id,
                DebtBalanceSnapshot.date == snapshot_date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.balance = balance
            existing.source = source
            await self.session.flush()
            return existing
        snapshot = DebtBalanceSnapshot(
            debt_id=debt_id, date=snapshot_date, balance=balance, source=source
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
