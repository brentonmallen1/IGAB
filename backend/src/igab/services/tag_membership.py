"""Which categories carry one tag — read and changed from the tag's side.

The category inspector sets a category's tags one category at a time. This is
the other direction: one tag, and the checklist of every category it could be
on (Settings → Tags → "N categories", and the emergency-fund picker's
Envelopes). Both directions write the same membership records, so an undo
cannot tell which screen made the change.

**The taggable set is the listing's.** Every id is checked against
`CategoryRepository.get_taggable_with_group_names` — the rows the checklist is
built from — so a request cannot tag a category the checklist would never have
offered (an income category, another budget's, a deleted one).

**One save, one undo.** Memberships and savings modes land inside one
`recorder.batch()`, so Cmd+Z puts back the whole checklist as it was, modes
included. A category whose membership did not move records nothing; neither
does a mode that already matches.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, Tag, category_tags
from igab.domain.exceptions import InvariantViolation
from igab.domain.tag_hints import DERIVED_KEYS
from igab.repositories.category_filters import SAVINGS_ROLE, SAVINGS_ROLE_NONE, SavingsMode
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.tag_repo import TagRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match


async def category_tag_ids(session: AsyncSession, category_id: uuid.UUID) -> list[str]:
    """The raw tag ids on one category, sorted for == — recorded as `_tag_ids`
    bookkeeping on membership updates (the rows are hard-replaced on every set,
    so undo rebuilds them rather than flipping fields)."""
    return sorted(
        str(t)
        for t in (
            await session.execute(
                select(category_tags.c.tag_id).where(category_tags.c.category_id == category_id)
            )
        ).scalars()
    )


async def record_membership(
    recorder: ChangeRecorder,
    budget_id: uuid.UUID,
    owner_id: uuid.UUID,
    before_ids: list[str],
    after_ids: list[str],
) -> None:
    """Record one category's tag set moving — the `category_tags` pseudo-subject
    every membership write path shares. Nothing when the set did not move."""
    if before_ids != after_ids:
        await recorder.record(
            budget_id=budget_id,
            entity_type="category_tags",
            entity_id=owner_id,
            action="update",
            before={"_tag_ids": before_ids},
            after={"_tag_ids": after_ids},
        )


@dataclass(frozen=True)
class MembershipRow:
    category: Category
    group_name: str
    member: bool


async def membership(session: AsyncSession, budget_id: uuid.UUID, tag: Tag) -> list[MembershipRow]:
    """Every taggable category, in Budget-page order, and whether it carries
    `tag`. The categories carry `savings_role` (the taggable loader serves it)."""
    rows = await CategoryRepository(session).get_taggable_with_group_names(budget_id)
    members = set(
        (
            await session.execute(
                select(category_tags.c.category_id).where(category_tags.c.tag_id == tag.id)
            )
        ).scalars()
    )
    return [MembershipRow(c, group_name, c.id in members) for c, group_name in rows]


def refuse_derived(tag: Tag) -> None:
    if tag.system_key in DERIVED_KEYS:
        raise InvariantViolation(
            f"The {tag.name} tag is set by the wishlist itself, from which envelopes fund "
            "an open wish. Setting it by hand would be undone on the next wishlist change."
        )


async def set_membership(
    session: AsyncSession,
    recorder: ChangeRecorder,
    budget_id: uuid.UUID,
    tag: Tag,
    add: set[uuid.UUID],
    remove: set[uuid.UUID],
    savings_modes: Mapping[uuid.UUID, SavingsMode | None],
) -> None:
    """Put `tag` on `add`, take it off `remove`, and store `savings_modes`.

    Idempotent: adding a member or removing a non-member changes and records
    nothing. `savings_modes` (None = back to the tags' default) is only for a
    category that is a savings category once the membership has moved —
    anything else is refused, because the choice would be stored and ignored
    (`SAVINGS_ROLE` serves 'none' for it) and the checklist would look saved.

    Raises `InvariantViolation` for a derived tag, a category outside the
    taggable set, an id both added and removed, or a mode for a category that
    is not a savings category. The writes sit in a savepoint that rolls back
    on it: the mode check runs after the membership writes, because whether a
    category is a savings category is `SAVINGS_ROLE`'s to say, not a second
    spelling here.
    """
    refuse_derived(tag)
    both = add & remove
    if both:
        raise InvariantViolation("A category cannot be both added to and removed from a tag.")
    taggable = {
        c.id for c, _ in await CategoryRepository(session).get_taggable_with_group_names(budget_id)
    }
    named = add | remove | set(savings_modes)
    if named - taggable:
        raise InvariantViolation(
            "Only this budget's own categories outside the income group can be tagged."
        )

    tags = TagRepository(session)
    # A savepoint, so a refused mode leaves no membership (or record) written
    # whatever the caller does with the transaction.
    with recorder.batch():
        async with session.begin_nested():
            for category_id in sorted(add | remove):
                before_ids = await category_tag_ids(session, category_id)
                if category_id in add:
                    await tags.add_category_tag(category_id, tag.id)
                else:
                    await tags.remove_category_tag(category_id, tag.id)
                after_ids = await category_tag_ids(session, category_id)
                await record_membership(recorder, budget_id, category_id, before_ids, after_ids)

            if savings_modes:
                await _set_savings_modes(session, recorder, budget_id, savings_modes)


async def _set_savings_modes(
    session: AsyncSession,
    recorder: ChangeRecorder,
    budget_id: uuid.UUID,
    savings_modes: Mapping[uuid.UUID, SavingsMode | None],
) -> None:
    result = await session.execute(
        select(Category.id, SAVINGS_ROLE).where(Category.id.in_(list(savings_modes)))
    )
    roles = {cid: role for cid, role in result.all()}
    if any(roles.get(cid, SAVINGS_ROLE_NONE) == SAVINGS_ROLE_NONE for cid in savings_modes):
        raise InvariantViolation(
            "How money counts as saved can only be set on a Savings or Emergency fund category."
        )
    repo = CategoryRepository(session)
    for category_id in sorted(savings_modes):
        current = await repo.get_or_raise(category_id)
        mode = savings_modes[category_id]
        if current.savings_mode == mode:
            continue
        before = snapshot("category", current)
        updated = await repo.update(category_id, savings_mode=mode)
        after = snapshot("category", updated)
        if snapshots_match(after, before):
            # The inspector's own record: `savings_mode` is a category field,
            # so undo restores it through the ordinary category inverse.
            await recorder.record(
                budget_id=budget_id,
                entity_type="category",
                entity_id=category_id,
                action="update",
                before=before,
                after=after,
            )
