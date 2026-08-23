import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from igab.db.models import (
    BudgetView,
    BudgetViewGroup,
    BudgetViewPlacement,
    Category,
)
from igab.domain.exceptions import InvariantViolation
from igab.repositories.base import BaseRepository


class BudgetViewRepository(BaseRepository[BudgetView]):
    """Views: alternate arrangements of a budget's own categories.

    A view never edits the default arrangement in `category_groups`. It holds
    its own groups and a placement per category, so the same budget can be read
    two ways at once.
    """

    model = BudgetView

    _LOADED = (
        selectinload(BudgetView.groups),
        selectinload(BudgetView.placements),
    )

    async def get_all(self, budget_id: uuid.UUID) -> list[BudgetView]:
        result = await self.session.execute(
            select(BudgetView)
            .where(
                BudgetView.budget_id == budget_id,
                BudgetView.is_deleted == False,  # noqa: E712
            )
            .options(*self._LOADED)
            .order_by(BudgetView.sort_order, BudgetView.name)
        )
        return list(result.scalars().all())

    async def get_full(self, view_id: uuid.UUID) -> BudgetView | None:
        result = await self.session.execute(
            select(BudgetView)
            .where(
                BudgetView.id == view_id,
                BudgetView.is_deleted == False,  # noqa: E712
            )
            .options(*self._LOADED)
        )
        return result.scalar_one_or_none()

    async def _budget_of(self, view_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self.session.execute(select(BudgetView.budget_id).where(BudgetView.id == view_id))
        ).scalar_one_or_none()

    async def set_groups(self, view_id: uuid.UUID, names: list[str]) -> list[BudgetViewGroup]:
        """Replace the view's groups, in the order given.

        Groups are matched by name so that re-saving a view keeps existing
        placements pointing at the same group. Rebuilding them by identity
        would silently empty every group on each save.
        """
        existing = list(
            (
                await self.session.execute(
                    select(BudgetViewGroup).where(BudgetViewGroup.view_id == view_id)
                )
            )
            .scalars()
            .all()
        )
        by_name = {g.name: g for g in existing}
        wanted = list(dict.fromkeys(n.strip() for n in names if n.strip()))

        removed = [g for g in existing if g.name not in wanted]
        for gone in removed:
            # Placements fall back to Unassigned rather than disappearing —
            # the FK is SET NULL for exactly this.
            await self.session.delete(gone)
        if removed:
            # SQLAlchemy flushes INSERTs before DELETEs; a rename that reuses a
            # removed group's name would trip uq_budget_view_group_name unless
            # the deletes land first.
            await self.session.flush()

        out: list[BudgetViewGroup] = []
        for order, name in enumerate(wanted):
            group = by_name.get(name)
            if group is None:
                group = BudgetViewGroup(view_id=view_id, name=name, sort_order=order)
                self.session.add(group)
            else:
                group.sort_order = order
            out.append(group)
        await self.session.flush()
        return out

    async def set_placements(self, view_id: uuid.UUID, placements: list[dict]) -> None:
        """Replace where each category sits in this view.

        Each entry is {category_id, group_id? | group_name?, sort_order?,
        is_hidden?}. Both ids are checked against the view's own budget: the
        route guard authorises the *view*, not the ids in the body.

        `group_name` is resolved against this view's groups, so a caller that
        just created them in the same request can place categories without a
        second round trip.
        """
        budget_id = await self._budget_of(view_id)

        if any(p.get("group_name") and not p.get("group_id") for p in placements):
            by_name = {
                g.name: g.id
                for g in (
                    await self.session.execute(
                        select(BudgetViewGroup).where(BudgetViewGroup.view_id == view_id)
                    )
                )
                .scalars()
                .all()
            }
            for p in placements:
                if p.get("group_id") is None and p.get("group_name"):
                    p["group_id"] = by_name.get(p["group_name"])

        category_ids = [p["category_id"] for p in placements]
        if category_ids:
            valid = set(
                (
                    await self.session.execute(
                        select(Category.id).where(
                            Category.id.in_(category_ids), Category.budget_id == budget_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            if any(c not in valid for c in category_ids):
                raise InvariantViolation("Category does not belong to this budget")

        group_ids = {p.get("group_id") for p in placements if p.get("group_id")}
        if group_ids:
            own = set(
                (
                    await self.session.execute(
                        select(BudgetViewGroup.id).where(
                            BudgetViewGroup.id.in_(group_ids),
                            BudgetViewGroup.view_id == view_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if any(g not in own for g in group_ids):
                raise InvariantViolation("Group does not belong to this view")

        await self.session.execute(
            delete(BudgetViewPlacement).where(BudgetViewPlacement.view_id == view_id)
        )
        for order, p in enumerate(placements):
            self.session.add(
                BudgetViewPlacement(
                    view_id=view_id,
                    category_id=p["category_id"],
                    group_id=p.get("group_id"),
                    sort_order=p.get("sort_order", order),
                    is_hidden=p.get("is_hidden", False),
                )
            )
        await self.session.flush()
