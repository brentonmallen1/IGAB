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
            select(ScheduledTransaction)
            .where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.is_deleted == False,  # noqa: E712
            )
            .order_by(ScheduledTransaction.next_occurrence_date)
        )
        return list(result.scalars().all())

    async def get_due(
        self, as_of: date, *, budget_id: uuid.UUID | None = None
    ) -> list[ScheduledTransaction]:
        stmt = select(ScheduledTransaction).where(
            ScheduledTransaction.next_occurrence_date <= as_of,
            ScheduledTransaction.is_deleted == False,  # noqa: E712
        )
        if budget_id is not None:
            stmt = stmt.where(ScheduledTransaction.budget_id == budget_id)
        result = await self.session.execute(
            stmt.order_by(ScheduledTransaction.next_occurrence_date)
        )
        return list(result.scalars().all())

    async def get_existing_import_ids(self, budget_id: uuid.UUID, import_ids: set[str]) -> set[str]:
        """Which of these import ids already name a live schedule in the budget."""
        if not import_ids:
            return set()
        result = await self.session.execute(
            select(ScheduledTransaction.import_id).where(
                ScheduledTransaction.budget_id == budget_id,
                ScheduledTransaction.import_id.in_(import_ids),
                ScheduledTransaction.is_deleted == False,  # noqa: E712
            )
        )
        return {row for row in result.scalars().all() if row is not None}

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
