import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, not_, select, update
from sqlalchemy.orm import selectinload, with_expression

from igab.db.models import BudgetAssignment, Category, CategoryGroup
from igab.domain.ordering import merge_reorder
from igab.repositories.base import BaseRepository
from igab.repositories.category_filters import (
    IN_SYSTEM_GROUP,
    IS_ASSIGNABLE,
    IS_CATEGORIZABLE,
)

#: Groups the app seeds and protects by key. Kept the way SYSTEM_TAGS is —
#: (key, name) — and seeded the same lazy way: adopt a same-named group the
#: user already made rather than colliding with it. These are ordinary,
#: assignable envelope groups; `is_system` means something else entirely.
SYSTEM_GROUPS: list[tuple[str, str]] = [("wishlist", "Wishlist")]


class CategoryGroupRepository(BaseRepository[CategoryGroup]):
    model = CategoryGroup

    async def get_by_system_key(
        self, budget_id: uuid.UUID, system_key: str
    ) -> CategoryGroup | None:
        result = await self.session.execute(
            select(CategoryGroup).where(
                CategoryGroup.budget_id == budget_id,
                CategoryGroup.system_key == system_key,
                CategoryGroup.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def ensure_system_group(self, budget_id: uuid.UUID, system_key: str) -> CategoryGroup:
        """The keyed group, seeded on first need.

        A live group the user already named the same is ADOPTED and stamped
        with the key, as `seed_system_tags` does — creating a second
        "Wishlist" would collide on the name, and skipping would leave their
        group unprotected and the wishlist's wishes homeless.
        """
        existing = await self.get_by_system_key(budget_id, system_key)
        if existing is not None:
            return existing
        name = dict(SYSTEM_GROUPS)[system_key]
        claimed = (
            await self.session.execute(
                select(CategoryGroup).where(
                    CategoryGroup.budget_id == budget_id,
                    func.lower(CategoryGroup.name) == name.lower(),
                    CategoryGroup.system_key.is_(None),
                    CategoryGroup.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if claimed is not None:
            claimed.system_key = system_key
            await self.session.flush()
            return claimed
        return await self.create(
            budget_id=budget_id,
            name=name,
            system_key=system_key,
            is_system=False,
        )

    async def next_sort_order(self, budget_id: uuid.UUID) -> int:
        """The position after the budget's last live group."""
        last = (
            await self.session.execute(
                select(func.coalesce(func.max(CategoryGroup.sort_order), -1)).where(
                    CategoryGroup.budget_id == budget_id,
                    CategoryGroup.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one()
        return int(last) + 1

    async def create(self, **kwargs: Any) -> CategoryGroup:
        # A new group goes last unless the caller says where it belongs. The
        # one rule for a new row's position: the budget page used to send its
        # own count of the rows it happened to be showing, the API took
        # whatever it was sent, and the importer sent nothing.
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = await self.next_sort_order(kwargs["budget_id"])
        return await super().create(**kwargs)

    async def reorder(self, budget_id: uuid.UUID, group_ids: list[uuid.UUID]) -> None:
        """Set every group's sort_order from its position in `group_ids`.

        The list must name each of the budget's *visible* live groups exactly
        once. **Hidden** groups may be omitted, because the budget page drags
        against the list it shows and by default that list excludes them —
        demanding completeness the caller structurally cannot provide made
        every reorder fail for any budget that had ever hidden a group. So may
        **system** groups (Income), which the grid never draws. An omitted
        group keeps its old position among the others (stable interleave), so
        it re-appears where the user left it when shown. The rule itself is
        `domain.ordering.merge_reorder`, shared with categories.
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
        final = merge_reorder(
            [(g.id, g.is_hidden or g.is_system) for g in live], group_ids, noun="group"
        )
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

    async def next_sort_order(self, group_id: uuid.UUID) -> int:
        """The position after the group's last live category."""
        last = (
            await self.session.execute(
                select(func.coalesce(func.max(Category.sort_order), -1)).where(
                    Category.category_group_id == group_id,
                    Category.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one()
        return int(last) + 1

    async def create(self, **kwargs: Any) -> Category:
        # A new category goes last in its group unless the caller says where
        # it belongs — see CategoryGroupRepository.create.
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = await self.next_sort_order(kwargs["category_group_id"])
        # BaseRepository.create ends in session.refresh(), which takes no
        # loader options and would drop the expressions. Same round-trip count.
        obj = Category(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return await self.get_or_raise(obj.id)

    async def reorder(self, group_id: uuid.UUID, category_ids: list[uuid.UUID]) -> None:
        """Set the order of one group's categories from `category_ids`.

        Same contract as CategoryGroupRepository.reorder: every visible live
        category of the group exactly once, hidden ones may be omitted and
        keep their slot, anything else refused. Positions are per group —
        the grid buckets by group before it reads them.
        """
        live = list(
            (
                await self.session.execute(
                    select(Category)
                    .where(
                        Category.category_group_id == group_id,
                        Category.is_deleted == False,  # noqa: E712
                    )
                    .order_by(Category.sort_order, Category.name)
                )
            ).scalars()
        )
        final = merge_reorder(
            [(c.id, c.is_hidden) for c in live],
            category_ids,
            noun="category",
            plural="categories",
            scope="group",
        )
        for position, category_id in enumerate(final):
            await self.session.execute(
                update(Category).where(Category.id == category_id).values(sort_order=position)
            )
        await self.session.flush()

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
        # Name breaks ties, as the group listing does: rows sharing a position
        # (every category a YNAB import ever created, before positions were
        # assigned) came back in a different order on every read.
        q = q.order_by(Category.sort_order, Category.name)
        # populate_existing is load-bearing here as in `get`: a category the
        # session already holds keeps whatever `is_assignable` it was loaded
        # with, so hiding its group mid-session left it eligible to assign to.
        result = await self.session.execute(q.execution_options(populate_existing=True))
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
        q = q.order_by(Category.sort_order, Category.name)
        result = await self.session.execute(q.execution_options(populate_existing=True))
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
            .order_by(Category.sort_order, Category.name)
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
        """Total assigned across all months strictly after the given month.

        System-group categories are left out, as the category term of Ready
        to Assign leaves them out: an assignment on an income category
        (refused now, but rows from before exist) was deducted here while its
        category was excluded there. Deleted categories stay IN on purpose —
        an old-style delete left their assignments behind, and this term is
        how that stranded money still shows until the hygiene repair
        releases it (test_category_delete.py pins the figure).
        """
        result = await self.session.execute(
            select(func.coalesce(func.sum(BudgetAssignment.assigned), 0))
            .select_from(BudgetAssignment)
            .join(Category, Category.id == BudgetAssignment.category_id)
            .where(
                BudgetAssignment.budget_id == budget_id,
                BudgetAssignment.month > month,
                not_(IN_SYSTEM_GROUP),
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
