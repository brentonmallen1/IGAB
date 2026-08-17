import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update

from igab.db.models import AIJob, Transaction
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

    async def existing_transaction_ids(self, txn_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        """Which of these transaction ids still resolve to a live (non-deleted)
        transaction — powers the 'transaction removed' badge in the log."""
        if not txn_ids:
            return set()
        result = await self.session.execute(
            select(Transaction.id).where(
                Transaction.id.in_(txn_ids),
                Transaction.is_deleted == False,  # noqa: E712
            )
        )
        return set(result.scalars().all())

    async def delete_finished_before(self, cutoff: datetime) -> list[uuid.UUID]:
        """Remove done/error jobs finished before the cutoff; returns the
        deleted ids so callers can clean up job-owned staging files."""
        result = await self.session.execute(
            select(AIJob.id).where(
                AIJob.status.in_(("done", "error")),
                func.coalesce(AIJob.finished_at, AIJob.created_at) < cutoff,
            )
        )
        ids = list(result.scalars().all())
        if ids:
            await self.session.execute(delete(AIJob).where(AIJob.id.in_(ids)))
            await self.session.flush()
        return ids

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
