import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from igab.db.models import (
    BudgetFilter,
    BudgetFilterCategory,
    BudgetFilterTag,
    Category,
    Tag,
    category_tags,
)
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
            .options(
                selectinload(BudgetFilter.category_selections),
                selectinload(BudgetFilter.tag_selections),
            )
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
            .options(
                selectinload(BudgetFilter.category_selections),
                selectinload(BudgetFilter.tag_selections),
            )
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

    async def set_tags(self, filter_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> None:
        """Replace the filter's tag set, checked against its own budget the
        way `set_categories` checks category ids."""
        if tag_ids:
            owner_budget = (
                await self.session.execute(
                    select(BudgetFilter.budget_id).where(BudgetFilter.id == filter_id)
                )
            ).scalar_one_or_none()
            valid = set(
                (
                    await self.session.execute(
                        select(Tag.id).where(
                            Tag.id.in_(tag_ids),
                            Tag.budget_id == owner_budget,
                            Tag.is_deleted == False,  # noqa: E712
                        )
                    )
                )
                .scalars()
                .all()
            )
            if any(t not in valid for t in tag_ids):
                raise InvariantViolation("Tag does not belong to this budget")

        await self.session.execute(
            delete(BudgetFilterTag).where(BudgetFilterTag.filter_id == filter_id)
        )
        for tag_id in dict.fromkeys(tag_ids):
            self.session.add(BudgetFilterTag(filter_id=filter_id, tag_id=tag_id))
        await self.session.flush()

    async def effective_category_ids(
        self, filters: list[BudgetFilter]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """What each filter includes right now: its named categories plus
        every live category carrying one of its tags.

        One home for the rule, and one query for a whole list: the budget
        page reads it from the filter response and a report handed a
        filter_id resolves it here too, so the two cannot disagree about
        which rows a filter means.
        """
        tag_ids = {sel.tag_id for f in filters for sel in f.tag_selections}
        by_tag: dict[uuid.UUID, set[uuid.UUID]] = {}
        if tag_ids:
            rows = await self.session.execute(
                select(category_tags.c.tag_id, category_tags.c.category_id)
                .join(Category, Category.id == category_tags.c.category_id)
                .where(
                    category_tags.c.tag_id.in_(tag_ids),
                    Category.is_deleted == False,  # noqa: E712
                )
            )
            for tag_id, category_id in rows.all():
                by_tag.setdefault(tag_id, set()).add(category_id)
        out: dict[uuid.UUID, list[uuid.UUID]] = {}
        for f in filters:
            ids = {sel.category_id for sel in f.category_selections}
            for sel in f.tag_selections:
                ids |= by_tag.get(sel.tag_id, set())
            out[f.id] = sorted(ids, key=str)
        return out
