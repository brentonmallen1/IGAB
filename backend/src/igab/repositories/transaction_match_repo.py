import uuid

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from igab.db.models import Transaction, TransactionMatch
from igab.repositories.txn_filters import NOT_DELETED, on_alias

_manual = aliased(Transaction)


def _pending_live_pairs(scope: ColumnElement[bool]) -> Select[tuple[TransactionMatch]]:
    """Pending matches whose two rows both still exist, oldest first.

    Both sides, not just the synced one. Undoing the import or sync that
    queued a pair deletes the row it created and leaves the match row behind;
    a review item for a row that is gone is a question nobody can answer, and
    accepting it only ever rejected it. The deleted side may come back (redo
    restores it), so the match is left pending rather than rejected — it is
    simply not offered while either row is gone. `scope` filters on the
    synced row (`Transaction`).
    """
    return (
        select(TransactionMatch)
        .join(Transaction, TransactionMatch.synced_transaction_id == Transaction.id)
        .join(_manual, TransactionMatch.manual_transaction_id == _manual.id)
        .where(
            scope,
            TransactionMatch.status == "pending",
            NOT_DELETED,
            on_alias(NOT_DELETED, _manual),
        )
        .order_by(TransactionMatch.created_at)
    )


class TransactionMatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        synced_transaction_id: uuid.UUID,
        manual_transaction_id: uuid.UUID,
        confidence_score: float,
        status: str = "pending",
    ) -> TransactionMatch:
        obj = TransactionMatch(
            synced_transaction_id=synced_transaction_id,
            manual_transaction_id=manual_transaction_id,
            confidence_score=confidence_score,
            status=status,
        )
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def get(self, match_id: uuid.UUID) -> TransactionMatch | None:
        result = await self.session.execute(
            select(TransactionMatch).where(TransactionMatch.id == match_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_for_budget(self, budget_id: uuid.UUID) -> list[TransactionMatch]:
        result = await self.session.execute(_pending_live_pairs(Transaction.budget_id == budget_id))
        return list(result.scalars().all())

    async def get_pending_for_account(self, account_id: uuid.UUID) -> list[TransactionMatch]:
        result = await self.session.execute(
            _pending_live_pairs(Transaction.account_id == account_id)
        )
        return list(result.scalars().all())

    async def exists_for_pair(self, txn_a_id: uuid.UUID, txn_b_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(TransactionMatch.id).where(
                (
                    (TransactionMatch.synced_transaction_id == txn_a_id)
                    & (TransactionMatch.manual_transaction_id == txn_b_id)
                )
                | (
                    (TransactionMatch.synced_transaction_id == txn_b_id)
                    & (TransactionMatch.manual_transaction_id == txn_a_id)
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def cancel_pending_for_transaction(self, transaction_id: uuid.UUID) -> int:
        """Reject all pending matches touching a transaction (delete/merge flows)."""
        from sqlalchemy import update

        result = await self.session.execute(
            update(TransactionMatch)
            .where(
                TransactionMatch.status == "pending",
                (TransactionMatch.synced_transaction_id == transaction_id)
                | (TransactionMatch.manual_transaction_id == transaction_id),
            )
            .values(status="rejected")
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def update_status(self, match_id: uuid.UUID, status: str) -> TransactionMatch:
        from sqlalchemy import update

        await self.session.execute(
            update(TransactionMatch).where(TransactionMatch.id == match_id).values(status=status)
        )
        await self.session.flush()
        result = await self.session.execute(
            select(TransactionMatch).where(TransactionMatch.id == match_id)
        )
        return result.scalar_one()
