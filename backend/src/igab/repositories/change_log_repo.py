import uuid

from sqlalchemy import func, select

from igab.db.models import ChangeLog, User
from igab.repositories.base import BaseRepository


class ChangeLogRepository(BaseRepository[ChangeLog]):
    model = ChangeLog

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
