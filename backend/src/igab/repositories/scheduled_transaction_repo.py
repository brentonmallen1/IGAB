import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import ScheduledTransaction


class ScheduledTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> ScheduledTransaction | None:
        result = await self.session.execute(
            select(ScheduledTransaction).where(
                ScheduledTransaction.id == id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_all(self, budget_id: uuid.UUID) -> list[ScheduledTransaction]:
        result = await self.session.execute(
            select(ScheduledTransaction).where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
            ).order_by(ScheduledTransaction.next_occurrence_date)
        )
        return list(result.scalars().all())

    async def get_due(self, as_of: date) -> list[ScheduledTransaction]:
        result = await self.session.execute(
            select(ScheduledTransaction).where(
                ScheduledTransaction.next_occurrence_date <= as_of,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ScheduledTransaction:
        obj = ScheduledTransaction(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: uuid.UUID, **kwargs: Any) -> ScheduledTransaction:
        kwargs["updated_at"] = func.now()
        await self.session.execute(
            update(ScheduledTransaction).where(ScheduledTransaction.id == id).values(**kwargs)
        )
        await self.session.flush()
        result = await self.session.execute(
            select(ScheduledTransaction).where(ScheduledTransaction.id == id)
        )
        return result.scalar_one()

    async def soft_delete(self, id: uuid.UUID) -> None:
        await self.session.execute(
            update(ScheduledTransaction)
            .where(ScheduledTransaction.id == id)
            .values(is_deleted=True, updated_at=func.now())
        )
        await self.session.flush()
