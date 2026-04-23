import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import TransactionMatch


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
        from igab.db.models import Transaction

        result = await self.session.execute(
            select(TransactionMatch)
            .join(Transaction, TransactionMatch.synced_transaction_id == Transaction.id)
            .where(
                Transaction.budget_id == budget_id,
                TransactionMatch.status == "pending",
            )
            .order_by(TransactionMatch.created_at)
        )
        return list(result.scalars().all())

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
