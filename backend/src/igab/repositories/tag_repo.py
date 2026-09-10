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
    # The Subscriptions report reads categories tagged Subscription and groups
    # their charges by payee. It used to be a payee tag; a household files
    # subscriptions into categories far more reliably than it tags each payee
    # (migration b8e5d1c73a49). Every tag works that way now.
    ("subscription", "Subscription", "purple"),
    ("savings", "Savings", "green"),
    # Cadence, not classification. It marks an envelope that saves monthly
    # toward a known annual bill, so the Savings report lists it beside real
    # savings — but the bill itself is a cost, and classifying its payout as
    # SAVINGS hid a property-tax payment from every spending report while
    # telling the household it had saved that money (see activity_class rule 1).
    ("long_term_expense", "Long-term expense", "teal"),
    ("debt_principal", "Debt principal", "orange"),
    # The two necessity tiers, and Essentials is the strict subset.
    #
    # Essential is what a household could not cut: rent, utilities, groceries.
    # It sizes the emergency fund, so it has to stay the LEAN figure.
    #
    # Cost of living is the wider, non-discretionary set — everything that
    # leaves the account whether or not you feel like it. Subscriptions belong
    # here and not in Essential; so does a home-maintenance sinking fund. Debt
    # principal joins it by CLASS rather than by tag, so a household with a car
    # loan gets a truthful figure without tagging each loan envelope.
    #
    # The gap between the two is the point: what a lean month could shed. See
    # `domain.activity_class.NecessityTier`, which composes both predicates so
    # the nesting cannot drift.
    ("essential", "Essential", "blue"),
    ("cost_of_living", "Cost of living", "yellow"),
    # Applied by the wishlist to every envelope that funds an open wish, and
    # removed when none does — derived from the wish→envelope link, never
    # hand-set, so reports that filter by it cannot disagree with the list.
    ("wishlist", "Wishlist", "pink"),
]


#: System tags the payee tag routes refuse. One place, read by both payee
#: routes and by the client's payee pickers (SYSTEM_TAG_HELP says "on
#: categories"), so a tag cannot be offered on one and refused by the other.
class TagRepository(BaseRepository[Tag]):
    model = Tag

    async def list_for_budget(self, budget_id: uuid.UUID) -> list[Tag]:
        result = await self.session.execute(
            select(Tag)
            .where(Tag.budget_id == budget_id, Tag.is_deleted == False)  # noqa: E712
            .order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def list_for_budget_with_counts(self, budget_id: uuid.UUID) -> list[tuple[Tag, int]]:
        category_count_subq = (
            select(func.count())
            .select_from(category_tags)
            .where(category_tags.c.tag_id == Tag.id)
            .correlate(Tag)
            .scalar_subquery()
        )
        # No payee count: tags on payees are retired, so it would be a zero
        # printed beside every tag forever.
        result = await self.session.execute(
            select(Tag, category_count_subq)
            .where(Tag.budget_id == budget_id, Tag.is_deleted == False)  # noqa: E712
            .order_by(Tag.name)
        )
        return [(row[0], row[1] or 0) for row in result.all()]

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
