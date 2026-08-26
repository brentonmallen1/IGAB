import uuid
from collections.abc import Sequence
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

    async def outflows_from(
        self,
        budget_id: uuid.UUID,
        category_ids: Sequence[uuid.UUID],
        start_month: date,
        end_month: date,
    ) -> list[BudgetMove]:
        """Money moved OUT of these envelopes, by budget month, newest first.

        The audit trail as a fact: to another envelope or back to To Be
        Assigned (`to_category_id` NULL). Read by the wishlist ("what pulled
        from your wants") and the Savings report — one query, two readers.
        """
        if not category_ids:
            return []
        result = await self.session.execute(
            select(BudgetMove)
            .where(
                BudgetMove.budget_id == budget_id,
                BudgetMove.from_category_id.in_(list(category_ids)),
                BudgetMove.month >= start_month,
                BudgetMove.month <= end_month,
            )
            .order_by(BudgetMove.created_at.desc())
        )
        return list(result.scalars().all())
