import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from igab.db.models import BudgetFilter, BudgetFilterCategory, Category
from igab.domain.exceptions import InvariantViolation
from igab.repositories.base import BaseRepository


class BudgetFilterRepository(BaseRepository[BudgetFilter]):
    model = BudgetFilter

    async def get_all(self, budget_id: uuid.UUID) -> list[BudgetFilter]:
        result = await self.session.execute(
            select(BudgetFilter)
            .where(
                BudgetFilter.budget_id == budget_id,
                BudgetFilter.is_deleted == False,  # noqa: E712
            )
            .options(selectinload(BudgetFilter.category_selections))
            .order_by(BudgetFilter.sort_order, BudgetFilter.name)
        )
        return list(result.scalars().all())

    async def get_with_categories(self, filter_id: uuid.UUID) -> BudgetFilter | None:
        result = await self.session.execute(
            select(BudgetFilter)
            .where(
                BudgetFilter.id == filter_id,
                BudgetFilter.is_deleted == False,  # noqa: E712
            )
            .options(selectinload(BudgetFilter.category_selections))
        )
        return result.scalar_one_or_none()

    async def set_categories(self, filter_id: uuid.UUID, category_ids: list[uuid.UUID]) -> None:
        """Replace the filter's category set.

        Ids are checked against the filter's own budget first. The route guard
        authorises the *filter*, not the ids in the body, so without this a
        member could attach another budget's category ids to a filter they
        legitimately own — and then read those category names back out of the
        filter list.
        """
        if category_ids:
            owner_budget = (
                await self.session.execute(
                    select(BudgetFilter.budget_id).where(BudgetFilter.id == filter_id)
                )
            ).scalar_one_or_none()
            valid = set(
                (
                    await self.session.execute(
                        select(Category.id).where(
                            Category.id.in_(category_ids),
                            Category.budget_id == owner_budget,
                        )
                    )
                )
                .scalars()
                .all()
            )
            foreign = [c for c in category_ids if c not in valid]
            if foreign:
                raise InvariantViolation("Category does not belong to this budget")

        await self.session.execute(
            delete(BudgetFilterCategory).where(BudgetFilterCategory.filter_id == filter_id)
        )
        for cat_id in category_ids:
            self.session.add(BudgetFilterCategory(filter_id=filter_id, category_id=cat_id))
        await self.session.flush()
