import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, Tag, category_tags, payee_tags
from igab.repositories.base import BaseRepository

TAG_COLOR_SLOTS = frozenset({"red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"})

#: Tags IGAB gives meaning to. Beyond labelling, the money ones OVERRIDE how a
#: transaction is classified (see igab.domain.activity_class): tagging a
#: category Savings makes spending from it count as saving even when no
#: transfer is involved, which is how a user says "I know better than the
#: inferred answer". Seeding is backfilled for existing budgets on first read
#: (api/v1/tags.py), so adding an entry here needs no migration.
SYSTEM_TAGS = [
    ("subscription", "Subscription", "purple"),
    ("savings", "Savings", "green"),
    ("long_term_expense", "Long-term expense", "teal"),
    ("debt_principal", "Debt principal", "orange"),
    # What a lean month costs. Drives the Essentials report, the Overview's
    # essentials card and the Guide's emergency-fund target — one figure,
    # three readers (see TransactionRepository.essential_spend). Applies to
    # categories and payees alike.
    ("essential", "Essential", "blue"),
    # Applied by the wishlist to every envelope that funds an open wish, and
    # removed when none does — derived from the wish→envelope link, never
    # hand-set, so reports that filter by it cannot disagree with the list.
    ("wishlist", "Wishlist", "pink"),
]

#: Name fragments that suggest a system tag on import, checked against the
#: category's own name and its group's.
#:
#: Only for a fresh import, where the alternative is a savings report that is
#: empty until the user finds a tag UI they have no reason to look for. It is
#: a suggestion made out loud — the import summary reports the count, and a
#: wrong guess is one click to remove — so the list stays short and obvious
#: rather than clever. Nothing here ever re-tags an existing category.
IMPORT_TAG_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("savings", ("saving", "emergency fund", "rainy day", "nest egg")),
    ("long_term_expense", ("true expense", "long term", "long-term", "sinking fund")),
]


def suggest_system_tag(category_name: str, group_name: str) -> str | None:
    """The system tag an imported category's names point at, if any.

    The category's own name wins: a "Vacation" category inside a "True
    Expenses" group is a long-term expense, but a "Savings" category in that
    same group is savings.
    """
    for haystack in (category_name, group_name):
        lowered = haystack.lower()
        for system_key, fragments in IMPORT_TAG_HINTS:
            if any(fragment in lowered for fragment in fragments):
                return system_key
    return None


class TagRepository(BaseRepository[Tag]):
    model = Tag

    async def list_for_budget(self, budget_id: uuid.UUID) -> list[Tag]:
        result = await self.session.execute(
            select(Tag)
            .where(Tag.budget_id == budget_id, Tag.is_deleted == False)  # noqa: E712
            .order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def list_for_budget_with_counts(self, budget_id: uuid.UUID) -> list[tuple[Tag, int, int]]:
        category_count_subq = (
            select(func.count())
            .select_from(category_tags)
            .where(category_tags.c.tag_id == Tag.id)
            .correlate(Tag)
            .scalar_subquery()
        )
        payee_count_subq = (
            select(func.count())
            .select_from(payee_tags)
            .where(payee_tags.c.tag_id == Tag.id)
            .correlate(Tag)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Tag, category_count_subq, payee_count_subq)
            .where(Tag.budget_id == budget_id, Tag.is_deleted == False)  # noqa: E712
            .order_by(Tag.name)
        )
        return [(row[0], row[1] or 0, row[2] or 0) for row in result.all()]

    async def get_by_name(self, budget_id: uuid.UUID, name: str) -> Tag | None:
        result = await self.session.execute(
            select(Tag).where(
                Tag.budget_id == budget_id,
                func.lower(Tag.name) == func.lower(name),
                Tag.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_system_tag(self, budget_id: uuid.UUID, system_key: str) -> Tag | None:
        result = await self.session.execute(
            select(Tag).where(
                Tag.budget_id == budget_id,
                Tag.system_key == system_key,
                Tag.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def set_category_tags(self, category_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]) -> None:
        await self.session.execute(
            delete(category_tags).where(category_tags.c.category_id == category_id)
        )
        for tag_id in tag_ids:
            await self.session.execute(
                category_tags.insert().values(category_id=category_id, tag_id=tag_id)
            )
        await self.session.flush()

    async def set_payee_tags(self, payee_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]) -> None:
        await self.session.execute(delete(payee_tags).where(payee_tags.c.payee_id == payee_id))
        for tag_id in tag_ids:
            await self.session.execute(payee_tags.insert().values(payee_id=payee_id, tag_id=tag_id))
        await self.session.flush()

    async def add_category_tag(self, category_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        existing = await self.session.execute(
            select(category_tags).where(
                category_tags.c.category_id == category_id, category_tags.c.tag_id == tag_id
            )
        )
        if existing.first() is None:
            await self.session.execute(
                category_tags.insert().values(category_id=category_id, tag_id=tag_id)
            )
            await self.session.flush()

    async def remove_category_tag(self, category_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(category_tags).where(
                category_tags.c.category_id == category_id, category_tags.c.tag_id == tag_id
            )
        )
        await self.session.flush()

    async def add_payee_tag(self, payee_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        existing = await self.session.execute(
            select(payee_tags).where(
                payee_tags.c.payee_id == payee_id, payee_tags.c.tag_id == tag_id
            )
        )
        if existing.first() is None:
            await self.session.execute(payee_tags.insert().values(payee_id=payee_id, tag_id=tag_id))
            await self.session.flush()

    async def remove_payee_tag(self, payee_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(payee_tags).where(
                payee_tags.c.payee_id == payee_id, payee_tags.c.tag_id == tag_id
            )
        )
        await self.session.flush()

    async def get_category_system_keys(self, budget_id: uuid.UUID) -> dict[uuid.UUID, set[str]]:
        result = await self.session.execute(
            select(category_tags.c.category_id, Tag.system_key)
            .join(Tag, Tag.id == category_tags.c.tag_id)
            .join(Category, Category.id == category_tags.c.category_id)
            .where(
                Category.budget_id == budget_id,
                Tag.system_key.isnot(None),
                Tag.is_deleted == False,  # noqa: E712
            )
        )
        mapping: dict[uuid.UUID, set[str]] = {}
        for category_id, system_key in result.all():
            mapping.setdefault(category_id, set()).add(system_key)
        return mapping

    async def get_tags_for_categories(
        self, category_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Tag]]:
        if not category_ids:
            return {}
        result = await self.session.execute(
            select(category_tags.c.category_id, Tag)
            .join(Tag, Tag.id == category_tags.c.tag_id)
            .where(
                category_tags.c.category_id.in_(category_ids),
                Tag.is_deleted == False,  # noqa: E712
            )
            .order_by(Tag.name)
        )
        mapping: dict[uuid.UUID, list[Tag]] = {cid: [] for cid in category_ids}
        for category_id, tag in result.all():
            mapping[category_id].append(tag)
        return mapping

    async def get_tags_for_payees(
        self, payee_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Tag]]:
        if not payee_ids:
            return {}
        result = await self.session.execute(
            select(payee_tags.c.payee_id, Tag)
            .join(Tag, Tag.id == payee_tags.c.tag_id)
            .where(
                payee_tags.c.payee_id.in_(payee_ids),
                Tag.is_deleted == False,  # noqa: E712
            )
            .order_by(Tag.name)
        )
        mapping: dict[uuid.UUID, list[Tag]] = {pid: [] for pid in payee_ids}
        for payee_id, tag in result.all():
            mapping[payee_id].append(tag)
        return mapping

    async def delete_with_associations(self, tag_id: uuid.UUID) -> None:
        await self.session.execute(delete(category_tags).where(category_tags.c.tag_id == tag_id))
        await self.session.execute(delete(payee_tags).where(payee_tags.c.tag_id == tag_id))
        await self.soft_delete(tag_id)

    async def get_category_ids_by_tags(
        self, budget_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Get all category IDs that have any of the specified tags."""
        if not tag_ids:
            return set()
        result = await self.session.execute(
            select(category_tags.c.category_id)
            .join(Category, Category.id == category_tags.c.category_id)
            .where(
                category_tags.c.tag_id.in_(tag_ids),
                Category.budget_id == budget_id,
            )
        )
        return {row[0] for row in result.all()}

    async def get_payee_ids_by_tags(
        self, budget_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Get all payee IDs that have any of the specified tags."""
        if not tag_ids:
            return set()
        from igab.db.models import Payee

        result = await self.session.execute(
            select(payee_tags.c.payee_id)
            .join(Payee, Payee.id == payee_tags.c.payee_id)
            .where(
                payee_tags.c.tag_id.in_(tag_ids),
                Payee.budget_id == budget_id,
            )
        )
        return {row[0] for row in result.all()}

    async def get_category_ids_by_system_keys(
        self, budget_id: uuid.UUID, system_keys: Sequence[str]
    ) -> set[uuid.UUID]:
        """Get all category IDs that have tags with any of the specified system keys.

        For queries over things that are not transactions (assignments, the
        savings report's category list). A predicate over transaction rows
        is `txn_filters.category_tagged` — do not rebuild it from these ids.
        """
        if not system_keys:
            return set()
        result = await self.session.execute(
            select(category_tags.c.category_id)
            .join(Tag, Tag.id == category_tags.c.tag_id)
            .join(Category, Category.id == category_tags.c.category_id)
            .where(
                Tag.system_key.in_(system_keys),
                Category.budget_id == budget_id,
                Tag.is_deleted == False,  # noqa: E712
            )
        )
        return {row[0] for row in result.all()}

    async def get_payee_ids_by_system_keys(
        self, budget_id: uuid.UUID, system_keys: Sequence[str]
    ) -> set[uuid.UUID]:
        """Get all payee IDs that have tags with any of the specified system keys."""
        if not system_keys:
            return set()
        from igab.db.models import Payee

        result = await self.session.execute(
            select(payee_tags.c.payee_id)
            .join(Tag, Tag.id == payee_tags.c.tag_id)
            .join(Payee, Payee.id == payee_tags.c.payee_id)
            .where(
                Tag.system_key.in_(system_keys),
                Payee.budget_id == budget_id,
                Tag.is_deleted == False,  # noqa: E712
            )
        )
        return {row[0] for row in result.all()}


async def seed_system_tags(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """Give this budget the system tags it is missing.

    Per key, and safe to call repeatedly: a budget that has three of the four
    (anything predating `debt_principal`) gets the fourth rather than nothing.

    A same-named tag the user made themselves is ADOPTED rather than skipped.
    Skipping it is what the original backfill migration did, and the result
    was a budget where "Savings" existed, categories were tagged with it, and
    the savings report stayed empty forever — because the report looks up the
    system key, which that tag did not have. Adopting also avoids the unique
    name collision that creating a second "Savings" would hit.
    """
    repo = TagRepository(session)
    for system_key, name, color_slot in SYSTEM_TAGS:
        if await repo.get_system_tag(budget_id, system_key) is not None:
            continue
        claimed = (
            await session.execute(
                select(Tag).where(
                    Tag.budget_id == budget_id,
                    func.lower(Tag.name) == name.lower(),
                    Tag.system_key.is_(None),
                    Tag.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if claimed is not None:
            claimed.system_key = system_key
            claimed.color_slot = color_slot
            await session.flush()
            continue
        await repo.create(
            budget_id=budget_id,
            name=name,
            system_key=system_key,
            color_slot=color_slot,
        )
