import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Liability, LiabilityBalanceSnapshot
from igab.repositories.base import BaseRepository


class LiabilityRepository(BaseRepository[Liability]):
    model = Liability

    async def get_all(self, budget_id: uuid.UUID) -> list[Liability]:
        result = await self.session.execute(
            select(Liability)
            .where(Liability.budget_id == budget_id, Liability.is_deleted == False)  # noqa: E712
            .order_by(Liability.name)
        )
        return list(result.scalars().all())

    async def get_by_linked_account(self, account_id: uuid.UUID) -> Liability | None:
        result = await self.session.execute(
            select(Liability).where(
                Liability.linked_account_id == account_id,
                Liability.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_snapshots(self, liability_id: uuid.UUID) -> list[LiabilityBalanceSnapshot]:
        result = await self.session.execute(
            select(LiabilityBalanceSnapshot)
            .where(LiabilityBalanceSnapshot.liability_id == liability_id)
            .order_by(LiabilityBalanceSnapshot.date)
        )
        return list(result.scalars().all())

    async def upsert_snapshot(
        self,
        liability_id: uuid.UUID,
        snapshot_date: date,
        balance: Decimal,
        source: str = "manual",
    ) -> LiabilityBalanceSnapshot:
        """One snapshot per day: a second entry for the same date replaces it."""
        result = await self.session.execute(
            select(LiabilityBalanceSnapshot).where(
                LiabilityBalanceSnapshot.liability_id == liability_id,
                LiabilityBalanceSnapshot.date == snapshot_date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.balance = balance
            existing.source = source
            await self.session.flush()
            return existing
        snapshot = LiabilityBalanceSnapshot(
            liability_id=liability_id, date=snapshot_date, balance=balance, source=source
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
