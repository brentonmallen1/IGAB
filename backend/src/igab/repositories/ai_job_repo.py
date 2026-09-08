import uuid
from datetime import datetime

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import with_expression

from igab.db.models import AIJob, Transaction
from igab.repositories.base import BaseRepository
from igab.repositories.txn_filters import AI_NEEDS_REVIEW

ACTIVE_STATUSES = ("queued", "processing")

#: Whether this job's transaction is still waiting for the user.
#:
#: A correlated EXISTS rather than a join, so a job with no transaction (one
#: still queued, or one whose row was deleted) reads False instead of dropping
#: out of the list — the log outlives what it created.
#:
#: The predicate itself is `AI_NEEDS_REVIEW`, the same one
#: `count_ai_needs_review` sums. That is the whole point of the field: the nav
#: badge's number and this page's sections are one population, not two.
NEEDS_REVIEW_EXPR = exists(
    select(1)
    .select_from(Transaction)
    .where(Transaction.id == AIJob.transaction_id, AI_NEEDS_REVIEW)
)


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

    @staticmethod
    def with_review(stmt):
        """Populate `AIJob.needs_review`. The only way to do it.

        Every path that serializes an `AIJobResponse` must go through here or
        through `get_with_review` — the schema requires the field, so one that
        forgets raises rather than reporting waiting work as done.
        """
        return stmt.options(with_expression(AIJob.needs_review, NEEDS_REVIEW_EXPR))

    async def get_with_review(self, job_id: uuid.UUID) -> AIJob | None:
        """Re-read a job with `needs_review` populated.

        `populate_existing` is load-bearing: retry and reprocess have just
        mutated the row, so it is already in the identity map with the field
        unset, and without this the loader would hand back that instance
        untouched.
        """
        result = await self.session.execute(
            self.with_review(select(AIJob).where(AIJob.id == job_id)).execution_options(
                populate_existing=True
            )
        )
        return result.scalar_one_or_none()

    async def list_for_budget(
        self,
        budget_id: uuid.UUID,
        status: str | None = None,
        kind: str | None = None,
        transaction_id: uuid.UUID | None = None,
        needs_review: bool | None = None,
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
        if needs_review is not None:
            # The page's two sections are this filter and its negation, so
            # every job lands in exactly one of them.
            conditions.append(NEEDS_REVIEW_EXPR if needs_review else ~NEEDS_REVIEW_EXPR)

        total = await self.session.scalar(
            select(func.count()).select_from(AIJob).where(*conditions)
        )
        result = await self.session.execute(
            self.with_review(
                select(AIJob)
                .where(*conditions)
                .order_by(AIJob.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
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
