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

    async def latest_undone(self, budget_id: uuid.UUID) -> ChangeLog | None:
        """The most recently undone row — the redo candidate."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget_id, ChangeLog.undone_at.is_not(None))
            .order_by(ChangeLog.undone_at.desc(), ChangeLog.seq.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def count_live_after(self, budget_id: uuid.UUID, since) -> int:
        """Live rows recorded after `since` — a new action empties the redo stack."""
        result = await self.session.execute(
            select(func.count())
            .select_from(ChangeLog)
            .where(
                ChangeLog.budget_id == budget_id,
                ChangeLog.undone_at.is_(None),
                ChangeLog.created_at > since,
            )
        )
        return int(result.scalar_one())

    async def get_batch(self, budget_id: uuid.UUID, batch_id: uuid.UUID) -> list[ChangeLog]:
        """A batch's changes in reverse insertion order — the order undo must
        apply them so later changes revert before the ones they built on."""
        result = await self.session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget_id, ChangeLog.batch_id == batch_id)
            .order_by(ChangeLog.seq.desc())
        )
        return list(result.scalars().all())
