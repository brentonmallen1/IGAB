import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from igab.db.models import BudgetAssignment, Category, CategoryGroup
from igab.repositories.base import BaseRepository


class CategoryGroupRepository(BaseRepository[CategoryGroup]):
    model = CategoryGroup

    async def get_all(
        self, budget_id: uuid.UUID, include_hidden: bool = False
    ) -> list[CategoryGroup]:
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

    async def get_all(self, budget_id: uuid.UUID, include_hidden: bool = False) -> list[Category]:
        q = (
            select(Category)
            .options(selectinload(Category.tags))
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
            )
        )
        if not include_hidden:
            q = q.where(Category.is_hidden == False)  # noqa: E712
        q = q.order_by(Category.sort_order)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_all_with_group_names(
        self, budget_id: uuid.UUID, include_hidden: bool = False
    ) -> list[tuple[Category, str]]:
        """Categories paired with their group's name — for AI name matching,
        where the same category name in several groups must be
        disambiguated."""
        q = (
            select(Category, CategoryGroup.name)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
            )
        )
        if not include_hidden:
            q = q.where(Category.is_hidden == False)  # noqa: E712
        q = q.order_by(Category.sort_order)
        result = await self.session.execute(q)
        return [(row[0], row[1]) for row in result.all()]

    async def get_with_tags(self, category_id: uuid.UUID) -> Category | None:
        result = await self.session.execute(
            select(Category)
            .options(selectinload(Category.tags))
            .where(
                Category.id == category_id,
                Category.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_by_linked_liability(self, liability_id: uuid.UUID) -> Category | None:
        result = await self.session.execute(
            select(Category).where(
                Category.linked_liability_id == liability_id,
                Category.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalars().first()

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

    async def get_for_month(self, budget_id: uuid.UUID, month: date) -> list[BudgetAssignment]:
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

    async def get_all_for_budget(self, budget_id: uuid.UUID) -> list[BudgetAssignment]:
        result = await self.session.execute(
            select(BudgetAssignment)
            .where(BudgetAssignment.budget_id == budget_id)
            .order_by(BudgetAssignment.month)
        )
        return list(result.scalars().all())

    async def sum_after_month(self, budget_id: uuid.UUID, month: date) -> Decimal:
        """Total assigned across all months strictly after the given month."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(BudgetAssignment.assigned), 0)).where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month > month,
            )
        )
        return Decimal(str(result.scalar_one()))

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
