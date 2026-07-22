import uuid
from datetime import date

from sqlalchemy import select

from igab.db.models import BudgetMove
from igab.repositories.base import BaseRepository


class BudgetMoveRepository(BaseRepository[BudgetMove]):
    model = BudgetMove

    async def get_for_month(self, budget_id: uuid.UUID, month: date) -> list[BudgetMove]:
        result = await self.session.execute(
            select(BudgetMove)
            .where(BudgetMove.budget_id == budget_id, BudgetMove.month == month)
            .order_by(BudgetMove.created_at.desc())
        )
        return list(result.scalars().all())
