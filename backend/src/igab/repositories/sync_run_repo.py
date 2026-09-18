"""Reading and writing the bank-sync log."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from igab.db.models import SyncRun, SyncRunAccount


class SyncRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, accounts: list[dict], **fields) -> SyncRun:
        run = SyncRun(**fields)
        self.session.add(run)
        await self.session.flush()
        for row in accounts:
            self.session.add(SyncRunAccount(sync_run_id=run.id, **row))
        await self.session.flush()
        return run

    async def list_runs(
        self,
        *,
        budget_id: uuid.UUID | None = None,
        connection_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SyncRun], int]:
        filters = []
        if budget_id is not None:
            filters.append(SyncRun.budget_id == budget_id)
        if connection_id is not None:
            filters.append(SyncRun.connection_id == connection_id)

        total = await self.session.scalar(select(func.count()).select_from(SyncRun).where(*filters))
        result = await self.session.execute(
            select(SyncRun).where(*filters).order_by(SyncRun.seq.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get(self, run_id: uuid.UUID) -> SyncRun | None:
        result = await self.session.execute(
            select(SyncRun).where(SyncRun.id == run_id).options(selectinload(SyncRun.accounts))
        )
        return result.scalar_one_or_none()

    async def latest_with_orphans(self, budget_id: uuid.UUID) -> SyncRun | None:
        """The most recent run, whatever it said.

        Deliberately the latest run rather than the latest run *with* orphans:
        the question the UI asks is "is anything broken right now", and a
        stale finding from three runs ago would answer it wrongly in both
        directions.
        """
        result = await self.session.execute(
            select(SyncRun)
            .where(SyncRun.budget_id == budget_id)
            .order_by(SyncRun.seq.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_undone(self, run: SyncRun) -> None:
        run.undone_at = datetime.now(UTC)
        await self.session.flush()

    async def purge_older_than(self, days: int) -> int:
        """Drop runs past the retention window. Returns how many went."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            delete(SyncRun).where(SyncRun.created_at < cutoff).returning(SyncRun.id)
        )
        return len(list(result.scalars().all()))
