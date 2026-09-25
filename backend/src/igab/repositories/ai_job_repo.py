import uuid
from datetime import datetime

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import with_expression

from igab.db.models import AIJob, Transaction
from igab.repositories.base import BaseRepository
from igab.repositories.card_ending_repo import card_ending_owner
from igab.repositories.txn_filters import AI_NEEDS_REVIEW
from igab.services.receipt_placement import UNPLACED

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
#:
#: A receipt waiting for an account needs the user too, and more urgently: it
#: has no row to approve until someone says where it goes. It is filed with
#: the rows to approve, and the badge counts it (`unplaced_count`).
NEEDS_REVIEW_EXPR = or_(
    AIJob.status == UNPLACED,
    exists(
        select(1)
        .select_from(Transaction)
        .where(Transaction.id == AIJob.transaction_id, AI_NEEDS_REVIEW)
    ),
)


def _of_live_transaction(column):
    """`column` of the job's transaction as it is NOW, NULL when there is none.

    A correlated scalar subquery for the same reason `NEEDS_REVIEW_EXPR` is an
    EXISTS: a job whose transaction was deleted, or which never created one,
    must still appear in the log. One helper for every such field, so they
    cannot disagree about which row "the job's transaction" is.
    """
    return (
        select(column)
        .where(Transaction.id == AIJob.transaction_id, Transaction.is_deleted == False)  # noqa: E712
        .scalar_subquery()
    )


#: The account the job's transaction is in now — see the model's comment for
#: why the payload's account_id is not an answer to that question.
TRANSACTION_ACCOUNT_EXPR = _of_live_transaction(Transaction.account_id)

#: The category the job's transaction is filed in now — see the model's
#: comment for why the draft's category is not an answer to that question.
TRANSACTION_CATEGORY_EXPR = _of_live_transaction(Transaction.category_id)

#: Whether the job's transaction is a split parent, whose own category is
#: NULL by construction. False with no transaction: there is nothing to
#: split, and a required boolean must not read NULL.
TRANSACTION_IS_SPLIT_EXPR = func.coalesce(_of_live_transaction(Transaction.is_split), False)


#: The account whose card paid for this job's receipt — see the model's
#: comment. The lookup is `card_ending_owner`, the same select the worker runs
#: to place a scan, embedded here as a correlated subquery.
CARD_ENDING_ACCOUNT_EXPR = card_ending_owner(
    AIJob.budget_id, AIJob.result["draft"]["card_last4"].astext
).scalar_subquery()


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

        `transaction_account_id`, `transaction_category_id` and
        `transaction_is_split` ride along rather than getting loaders of their
        own: two loaders is two things to forget, and a review list that
        cannot say where a row landed (which account, which category) is the
        defect these fields were added for.
        """
        return stmt.options(
            with_expression(AIJob.needs_review, NEEDS_REVIEW_EXPR),
            with_expression(AIJob.transaction_account_id, TRANSACTION_ACCOUNT_EXPR),
            with_expression(AIJob.transaction_category_id, TRANSACTION_CATEGORY_EXPR),
            with_expression(AIJob.transaction_is_split, TRANSACTION_IS_SPLIT_EXPR),
            with_expression(AIJob.card_ending_account_id, CARD_ENDING_ACCOUNT_EXPR),
        )

    async def get_with_review(self, job_id: uuid.UUID) -> AIJob | None:
        """Re-read a job with the loaded-on-demand fields populated.

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
        # populate_existing, as in `get_with_review`: every served field is a
        # fact about another table's row, and a job the session already holds
        # would otherwise keep the answers it was first loaded with.
        result = await self.session.execute(
            self.with_review(
                select(AIJob)
                .where(*conditions)
                .order_by(AIJob.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).execution_options(populate_existing=True)
        )
        return list(result.scalars().all()), int(total or 0)

    async def active_count(self, budget_id: uuid.UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(AIJob)
            .where(AIJob.budget_id == budget_id, AIJob.status.in_(ACTIVE_STATUSES))
        )
        return int(count or 0)

    async def delete_finished_before(self, cutoff: datetime) -> list[uuid.UUID]:
        """Remove done/error jobs finished before the cutoff; returns the
        deleted ids so callers can clean up job-owned staging files.

        Never one still waiting for the user (`NEEDS_REVIEW_EXPR`, the
        predicate "Needs you" lists by). Retention ages out the log, not the
        work: deleting by age alone dropped an unapproved scan off that list
        while its row waited on. It goes once its row is approved or deleted.
        """
        result = await self.session.execute(
            select(AIJob.id).where(
                AIJob.status.in_(("done", "error")),
                func.coalesce(AIJob.finished_at, AIJob.created_at) < cutoff,
                ~NEEDS_REVIEW_EXPR,
            )
        )
        ids = list(result.scalars().all())
        if ids:
            await self.session.execute(delete(AIJob).where(AIJob.id.in_(ids)))
            await self.session.flush()
        return ids

    async def unplaced_count(self, budget_id: uuid.UUID) -> int:
        """Receipts waiting for an account."""
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(AIJob)
                .where(AIJob.budget_id == budget_id, AIJob.status == UNPLACED)
            )
            or 0
        )

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
