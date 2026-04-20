import uuid
from datetime import date

from sqlalchemy import select

from igab.db.models import BudgetAssignment, Category, CategoryGroup
from igab.repositories.base import BaseRepository


class CategoryGroupRepository(BaseRepository[CategoryGroup]):
    model = CategoryGroup

    async def get_all(self, budget_id: uuid.UUID, include_hidden: bool = False) -> list[CategoryGroup]:
        q = select(CategoryGroup).where(
            CategoryGroup.budget_id == budget_id,
            CategoryGroup.is_deleted == False,  # noqa: E712
        )
        if not include_hidden:
            q = q.where(CategoryGroup.is_hidden == False)  # noqa: E712
        q = q.order_by(CategoryGroup.sort_order, CategoryGroup.name)
        result = await self.session.execute(q)
        return list(result.scalars().all())


class CategoryRepository(BaseRepository[Category]):
    model = Category

    async def get_all(
        self, budget_id: uuid.UUID, include_hidden: bool = False
    ) -> list[Category]:
        q = select(Category).where(
            Category.budget_id == budget_id,
            Category.is_deleted == False,  # noqa: E712
        )
        if not include_hidden:
            q = q.where(Category.is_hidden == False)  # noqa: E712
        q = q.order_by(Category.sort_order)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_by_group(self, group_id: uuid.UUID) -> list[Category]:
        result = await self.session.execute(
            select(Category)
            .where(
                Category.category_group_id == group_id,
                Category.is_deleted == False,  # noqa: E712
            )
            .order_by(Category.sort_order)
        )
        return list(result.scalars().all())

    async def get_by_linked_account(self, account_id: uuid.UUID) -> Category | None:
        result = await self.session.execute(
            select(Category).where(
                Category.linked_account_id == account_id,
                Category.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()


class BudgetAssignmentRepository(BaseRepository[BudgetAssignment]):
    model = BudgetAssignment

    async def get_for_month(
        self, budget_id: uuid.UUID, month: date
    ) -> list[BudgetAssignment]:
        result = await self.session.execute(
            select(BudgetAssignment).where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month == month,
            )
        )
        return list(result.scalars().all())

    async def get_for_category(
        self, category_id: uuid.UUID, through_month: date | None = None
    ) -> list[BudgetAssignment]:
        q = select(BudgetAssignment).where(
            BudgetAssignment.category_id == category_id,
        )
        if through_month:
            q = q.where(BudgetAssignment.month <= through_month)
        q = q.order_by(BudgetAssignment.month)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_or_create(
        self, budget_id: uuid.UUID, category_id: uuid.UUID, month: date
    ) -> BudgetAssignment:
        result = await self.session.execute(
            select(BudgetAssignment).where(
                BudgetAssignment.category_id == category_id,
                BudgetAssignment.month == month,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            assignment = await self.create(
                budget_id=budget_id,
                category_id=category_id,
                month=month,
                assigned=0,
            )
        return assignment
