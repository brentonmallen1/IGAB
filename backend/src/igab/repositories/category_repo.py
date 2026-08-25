import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import selectinload, with_expression

from igab.db.models import BudgetAssignment, Category, CategoryGroup
from igab.domain.exceptions import InvariantViolation
from igab.repositories.base import BaseRepository
from igab.repositories.category_filters import IS_ASSIGNABLE, IS_CATEGORIZABLE


class CategoryGroupRepository(BaseRepository[CategoryGroup]):
    model = CategoryGroup

    async def reorder(self, budget_id: uuid.UUID, group_ids: list[uuid.UUID]) -> None:
        """Set every group's sort_order from its position in `group_ids`.

        The list must name each of the budget's *visible* live groups exactly
        once; **hidden** groups may be omitted, because the budget page drags
        against the list it shows and by default that list excludes them —
        demanding completeness the caller structurally cannot provide made
        every reorder fail for any budget that had ever hidden a group. An
        omitted hidden group keeps its old position among the others (stable
        interleave), so it re-appears where the user left it when re-shown.

        Everything else is still refused: a duplicate, an unknown or deleted
        id, or a *visible* group missing from the list — that last one is the
        stale client (a group added in another tab), which must fail loudly
        rather than shuffle rows the user never saw.
        """
        live = list(
            (
                await self.session.execute(
                    select(CategoryGroup)
                    .where(
                        CategoryGroup.budget_id == budget_id,
                        CategoryGroup.is_deleted == False,  # noqa: E712
                    )
                    .order_by(CategoryGroup.sort_order, CategoryGroup.name)
                )
            ).scalars()
        )
        given = set(group_ids)
        if len(group_ids) != len(given):
            raise InvariantViolation("Reorder must list each group at most once")
        live_ids = {g.id for g in live}
        if given - live_ids:
            raise InvariantViolation("Reorder names a group this budget does not have")
        visible = {g.id for g in live if not g.is_hidden}
        if visible - given:
            raise InvariantViolation("Reorder must list each of this budget's visible groups")

        # Omitted hidden groups hold their old slot; the given ids fill the
        # remaining slots in the given order.
        order: list[uuid.UUID | None] = [None] * len(live)
        for old_index, group in enumerate(live):
            if group.id not in given:
                order[old_index] = group.id
        it = iter(group_ids)
        final = [slot if slot is not None else next(it) for slot in order]

        for position, group_id in enumerate(final):
            await self.session.execute(
                update(CategoryGroup)
                .where(CategoryGroup.id == group_id)
                .values(sort_order=position)
            )
        await self.session.flush()

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

    @staticmethod
    def with_eligibility(stmt: Select[tuple[Category]]) -> Select[tuple[Category]]:
        """Load `is_assignable` and `is_categorizable` on a Category statement.

        Every path that serializes a `CategoryResponse` has to go through here.
        The fields are required in the schema, so a path that skips one raises
        rather than quietly reporting every category as ineligible — which
        would empty the move-money picker with no explanation.
        """
        return stmt.options(
            with_expression(Category.is_assignable, IS_ASSIGNABLE),
            with_expression(Category.is_categorizable, IS_CATEGORIZABLE),
        )

    async def get(self, id: uuid.UUID) -> Category | None:
        # Overrides BaseRepository.get to carry the eligibility flags.
        # populate_existing is load-bearing: after a flush the row is already
        # in the identity map, and SQLAlchemy leaves a with_expression
        # attribute unset on an object it has seen before — which would
        # surface as None on exactly the create/update responses.
        stmt = self.with_eligibility(
            select(Category).where(
                Category.id == id,
                Category.is_deleted == False,  # noqa: E712
            )
        ).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, **kwargs: Any) -> Category:
        # BaseRepository.create ends in session.refresh(), which takes no
        # loader options and would drop the expressions. Same round-trip count.
        obj = Category(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return await self.get_or_raise(obj.id)

    async def get_all(self, budget_id: uuid.UUID, include_hidden: bool = False) -> list[Category]:
        q = (
            self.with_eligibility(select(Category))
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
            .options(
                with_expression(Category.is_assignable, IS_ASSIGNABLE),
                with_expression(Category.is_categorizable, IS_CATEGORIZABLE),
            )
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
        # The eligibility expressions belong here too: this is the method the
        # create and update endpoints use to build a CategoryResponse, and the
        # response fields are required, so without them those endpoints 500.
        result = await self.session.execute(
            self.with_eligibility(select(Category))
            .options(selectinload(Category.tags))
            .execution_options(populate_existing=True)
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
