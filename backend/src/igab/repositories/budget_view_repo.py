import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from igab.db.models import BudgetView, BudgetViewCategory
from igab.repositories.base import BaseRepository


class BudgetViewRepository(BaseRepository[BudgetView]):
    model = BudgetView

    async def get_all(self, budget_id: uuid.UUID) -> list[BudgetView]:
        result = await self.session.execute(
            select(BudgetView)
            .where(
                BudgetView.budget_id == budget_id,
                BudgetView.is_deleted == False,  # noqa: E712
            )
            .options(selectinload(BudgetView.category_selections))
            .order_by(BudgetView.sort_order, BudgetView.name)
        )
        return list(result.scalars().all())

    async def get_with_categories(self, view_id: uuid.UUID) -> BudgetView | None:
        result = await self.session.execute(
            select(BudgetView)
            .where(
                BudgetView.id == view_id,
                BudgetView.is_deleted == False,  # noqa: E712
            )
            .options(selectinload(BudgetView.category_selections))
        )
        return result.scalar_one_or_none()

    async def set_categories(self, view_id: uuid.UUID, category_ids: list[uuid.UUID]) -> None:
        await self.session.execute(
            delete(BudgetViewCategory).where(BudgetViewCategory.view_id == view_id)
        )
        for cat_id in category_ids:
            self.session.add(BudgetViewCategory(view_id=view_id, category_id=cat_id))
        await self.session.flush()
