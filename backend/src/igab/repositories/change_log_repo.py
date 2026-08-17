import uuid

from sqlalchemy import func, select

from igab.db.models import ChangeLog
from igab.repositories.base import BaseRepository


class ChangeLogRepository(BaseRepository[ChangeLog]):
    model = ChangeLog

    async def list_for_budget(
        self, budget_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[ChangeLog]:
        result = await self.session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget_id)
            .order_by(ChangeLog.seq.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_budget(self, budget_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(ChangeLog).where(ChangeLog.budget_id == budget_id)
        )
        return int(result.scalar_one())

    async def get_batch(self, budget_id: uuid.UUID, batch_id: uuid.UUID) -> list[ChangeLog]:
        """A batch's changes in reverse insertion order — the order undo must
        apply them so later changes revert before the ones they built on."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget_id, ChangeLog.batch_id == batch_id)
            .order_by(ChangeLog.seq.desc())
        )
        return list(result.scalars().all())
