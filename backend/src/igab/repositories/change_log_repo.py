import uuid
from typing import Any

from sqlalchemy import func, select

from igab.db.models import (
    Account,
    Asset,
    Category,
    CategoryGroup,
    ChangeLog,
    Liability,
    Payee,
    Tag,
    User,
    WishlistProject,
)
from igab.repositories.base import BaseRepository

# Snapshot fields that are references, and what they point at. The log stores
# bare ids; the Activity page needs names — including for entities deleted
# since, whose names no list endpoint serves — so `display_names` resolves a
# page's worth in one query per model, is_deleted ignored on purpose.
_REFERENCE_FIELDS: dict[str, Any] = {
    "account_id": Account,
    "transfer_account_id": Account,
    "linked_account_id": Account,
    "payee_id": Payee,
    "category_id": Category,
    "prior_category_id": Category,
    "category_group_id": CategoryGroup,
    "linked_liability_id": Liability,
    "liability_id": Liability,
    "asset_id": Asset,
    "linked_asset_id": Asset,
    "project_id": WishlistProject,
}
# List-shaped bookkeeping references (tag membership dumps).
_REFERENCE_LIST_FIELDS: dict[str, Any] = {
    "_tag_ids": Tag,
}


class ChangeLogRepository(BaseRepository[ChangeLog]):
    model = ChangeLog

    async def display_names(self, changes: list[ChangeLog]) -> dict[uuid.UUID, str]:
        """id → display name for every reference these rows carry.

        Served beside the page rather than resolved client-side because the
        client is genuinely missing the input: a change row can point at an
        account or payee deleted since, and deleted names appear on no list
        endpoint. One map for the whole page keeps the client dumb — it looks
        up whichever ids it wants to show.
        """
        wanted: dict[Any, set[uuid.UUID]] = {}

        def collect(snapshot: dict[str, Any] | None) -> None:
            if not snapshot:
                return
            for field, value in snapshot.items():
                model = _REFERENCE_FIELDS.get(field)
                if model is not None and value:
                    wanted.setdefault(model, set()).add(uuid.UUID(str(value)))
                list_model = _REFERENCE_LIST_FIELDS.get(field)
                if list_model is not None and isinstance(value, list):
                    for item in value:
                        if item:
                            wanted.setdefault(list_model, set()).add(uuid.UUID(str(item)))

        for change in changes:
            collect(change.before)
            collect(change.after)

        names: dict[uuid.UUID, str] = {}
        for model, ids in wanted.items():
            result = await self.session.execute(
                select(model.id, model.name).where(model.id.in_(ids))
            )
            for row_id, name in result.all():
                names[row_id] = name
        return names

    async def list_for_budget(
        self, budget_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[tuple[ChangeLog, str | None]]:
        """Rows newest-first, each with the actor's display label (display
        name falling back to email; None for system/AI changes)."""
        actor_label = func.coalesce(User.display_name, User.email)
        result = await self.session.execute(
            select(ChangeLog, actor_label)
            .outerjoin(User, ChangeLog.user_id == User.id)
            .where(ChangeLog.budget_id == budget_id)
            .order_by(ChangeLog.seq.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def count_for_budget(self, budget_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(ChangeLog).where(ChangeLog.budget_id == budget_id)
        )
        return int(result.scalar_one())

    async def get_for_move(self, budget_id: uuid.UUID, move_id: uuid.UUID) -> list[ChangeLog]:
        """The assignment rows a budget move wrote (one per side), newest first.
        Keyed on the `_move_id` bookkeeping field move_money stamps into
        `after`, so a move can be undone on its own even when it shares a
        batch with fifty siblings from a bulk assign."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(
                ChangeLog.budget_id == budget_id,
                ChangeLog.entity_type == "assignment",
                ChangeLog.after["_move_id"].astext == str(move_id),
            )
            .order_by(ChangeLog.seq.desc())
        )
        return list(result.scalars().all())

    async def latest_live_manual(self, budget_id: uuid.UUID) -> ChangeLog | None:
        """The newest live change a bare ⌘Z may take back: manual rows only.

        Selection lives here, not on the client — the client used to pick
        from a 20-row window it fetched separately, which raced background
        writers and starved on a page of already-undone rows. Background and
        import sources are skipped: a SimpleFIN sync or an AI job landing
        between the user's action and their ⌘Z must not be what gets undone.
        Those rows keep their own explicit undo surfaces (the import toast,
        the Activity page, which can undo anything by id)."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(
                ChangeLog.budget_id == budget_id,
                ChangeLog.undone_at.is_(None),
                ChangeLog.source == "manual",
            )
            .order_by(ChangeLog.seq.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def latest_undone(self, budget_id: uuid.UUID) -> ChangeLog | None:
        """The most recently undone row — the redo candidate.

        Ordered by `undo_seq`, never `undone_at`: undone_at is the
        transaction timestamp, identical for every row one request undoes,
        and the old seq tie-break picked the NEWEST seq of a multi-row
        revert — the wrong end, since redo must replay the most recently
        undone (oldest-seq) row first. nulls_last() is a belt for rows
        undone before the column existed and missed by the backfill."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget_id, ChangeLog.undone_at.is_not(None))
            .order_by(ChangeLog.undo_seq.desc().nulls_last(), ChangeLog.seq.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def count_live_after_seq(self, budget_id: uuid.UUID, seq: int) -> int:
        """Live rows with a higher `seq` — a new action empties the redo
        stack, and a redo may never replay a row underneath a newer live
        change. Keyed on seq, the log's one total order; the old form
        compared `created_at` against `undone_at`, two clocks that agree
        only by luck."""
        result = await self.session.execute(
            select(func.count())
            .select_from(ChangeLog)
            .where(
                ChangeLog.budget_id == budget_id,
                ChangeLog.undone_at.is_(None),
                ChangeLog.seq > seq,
            )
        )
        return int(result.scalar_one())

    async def list_live_after(self, budget_id: uuid.UUID, seq: int) -> list[ChangeLog]:
        """Live rows recorded after `seq`, newest first — the order undo must
        apply them so later changes revert before the ones they built on.

        This is the whole selection behind "revert to here": the Activity
        page's line sits between two entries, and everything above it is
        exactly this list.
        """
        result = await self.session.execute(
            select(ChangeLog)
            .where(
                ChangeLog.budget_id == budget_id,
                ChangeLog.undone_at.is_(None),
                ChangeLog.seq > seq,
            )
            .order_by(ChangeLog.seq.desc())
        )
        return list(result.scalars().all())

    async def get_batch(self, budget_id: uuid.UUID, batch_id: uuid.UUID) -> list[ChangeLog]:
        """A batch's changes in reverse insertion order — the order undo must
        apply them so later changes revert before the ones they built on."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget_id, ChangeLog.batch_id == batch_id)
            .order_by(ChangeLog.seq.desc())
        )
        return list(result.scalars().all())
