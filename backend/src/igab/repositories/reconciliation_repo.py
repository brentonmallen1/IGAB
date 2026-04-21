import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import ReconciliationSnapshot
from igab.db.session import AsyncSession


class ReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        account_id: uuid.UUID,
        statement_balance: Decimal,
        cleared_balance: Decimal,
        adjustment_amount: Decimal = Decimal("0"),
        adjustment_transaction_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> ReconciliationSnapshot:
        snap = ReconciliationSnapshot(
            account_id=account_id,
            statement_balance=statement_balance,
            cleared_balance=cleared_balance,
            adjustment_amount=adjustment_amount,
            adjustment_transaction_id=adjustment_transaction_id,
            note=note,
            reconciled_at=datetime.now(tz=UTC),
        )
        self.session.add(snap)
        await self.session.flush()
        await self.session.refresh(snap)
        return snap

    async def get_history(self, account_id: uuid.UUID) -> list[ReconciliationSnapshot]:
        result = await self.session.execute(
            select(ReconciliationSnapshot)
            .where(ReconciliationSnapshot.account_id == account_id)
            .order_by(ReconciliationSnapshot.reconciled_at.desc())
        )
        return list(result.scalars().all())
