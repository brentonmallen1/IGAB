import uuid

from sqlalchemy import func, select

from igab.db.models import CategoryPlan
from igab.repositories.base import BaseRepository


class CategoryPlanRepository(BaseRepository[CategoryPlan]):
    model = CategoryPlan

    async def get_all(self, budget_id: uuid.UUID) -> list[CategoryPlan]:
        result = await self.session.execute(
            select(CategoryPlan)
            .where(CategoryPlan.budget_id == budget_id)
            .order_by(CategoryPlan.created_at, CategoryPlan.name)
        )
        return list(result.scalars())

    async def get_for_budget(self, budget_id: uuid.UUID, plan_id: uuid.UUID) -> CategoryPlan | None:
        result = await self.session.execute(
            select(CategoryPlan).where(
                CategoryPlan.id == plan_id, CategoryPlan.budget_id == budget_id
            )
        )
        return result.scalar_one_or_none()

    async def count(self, budget_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(CategoryPlan)
            .where(CategoryPlan.budget_id == budget_id)
        )
        return int(result.scalar_one())

    async def delete(self, plan: CategoryPlan) -> None:
        # Hard delete: plans are scratchpads with no history to preserve, so
        # there is no is_deleted column for BaseRepository.soft_delete to set.
        await self.session.delete(plan)
        await self.session.flush()

    async def name_exists(self, budget_id: uuid.UUID, name: str) -> bool:
        result = await self.session.execute(
            select(CategoryPlan.id).where(
                CategoryPlan.budget_id == budget_id,
                func.lower(CategoryPlan.name) == name.lower(),
            )
        )
        return result.first() is not None
