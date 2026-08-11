import uuid

from sqlalchemy import func, select, update

from igab.db.models import AIJob
from igab.repositories.base import BaseRepository

ACTIVE_STATUSES = ("queued", "processing")


class AIJobRepository(BaseRepository[AIJob]):
    model = AIJob

    async def claim_next(self) -> AIJob | None:
        """Claim the oldest runnable queued job.

        FOR UPDATE SKIP LOCKED makes this safe if the worker is ever made
        concurrent — two claimants can never grab the same row.
        """
        result = await self.session.execute(
            select(AIJob)
            .where(AIJob.status == "queued", AIJob.available_at <= func.now())
            .order_by(AIJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return result.scalar_one_or_none()

    async def list_for_budget(
        self,
        budget_id: uuid.UUID,
        status: str | None = None,
        kind: str | None = None,
        transaction_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AIJob], int]:
        conditions = [AIJob.budget_id == budget_id]
        if status:
            conditions.append(AIJob.status == status)
        if kind:
            conditions.append(AIJob.kind == kind)
        if transaction_id:
            conditions.append(AIJob.transaction_id == transaction_id)

        total = await self.session.scalar(
            select(func.count()).select_from(AIJob).where(*conditions)
        )
        result = await self.session.execute(
            select(AIJob)
            .where(*conditions)
            .order_by(AIJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def active_count(self, budget_id: uuid.UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(AIJob)
            .where(AIJob.budget_id == budget_id, AIJob.status.in_(ACTIVE_STATUSES))
        )
        return int(count or 0)

    async def reset_stale_processing(self) -> int:
        """Crash recovery: rows stuck in 'processing' from a previous run go
        back to 'queued' (attempts preserved) so they get picked up again."""
        result = await self.session.execute(
            update(AIJob)
            .where(AIJob.status == "processing")
            .values(status="queued", updated_at=func.now())
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)
