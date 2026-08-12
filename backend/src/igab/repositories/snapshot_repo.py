import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import BudgetSnapshotMeta, CategoryMonthSnapshot


class SnapshotRepository:
    """Category balance snapshot cache (see CategoryMonthSnapshot docstring).

    Validity is the presence of the budget's BudgetSnapshotMeta row;
    igab.db.invalidation deletes meta rows on any relevant write.
    """

    _BULK_CHUNK = 1000

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_valid(self, budget_id: uuid.UUID) -> bool:
        result = await self.session.scalar(
            select(BudgetSnapshotMeta.budget_id).where(BudgetSnapshotMeta.budget_id == budget_id)
        )
        return result is not None

    async def latest_per_category(
        self, budget_id: uuid.UUID, month: date
    ) -> dict[uuid.UUID, CategoryMonthSnapshot]:
        """Most recent snapshot row at or before `month`, per category.

        A row at exactly `month` carries that month's assigned/activity; an
        older row means the queried month has no data of its own and its
        available is the floored carryover.
        """
        result = await self.session.execute(
            select(CategoryMonthSnapshot)
            .where(
                CategoryMonthSnapshot.budget_id == budget_id,
                CategoryMonthSnapshot.month <= month,
            )
            .distinct(CategoryMonthSnapshot.category_id)
            .order_by(CategoryMonthSnapshot.category_id, CategoryMonthSnapshot.month.desc())
        )
        return {row.category_id: row for row in result.scalars()}

    async def rows_for_range(
        self, budget_id: uuid.UUID, start_month: date, end_month: date
    ) -> list[CategoryMonthSnapshot]:
        result = await self.session.execute(
            select(CategoryMonthSnapshot)
            .where(
                CategoryMonthSnapshot.budget_id == budget_id,
                CategoryMonthSnapshot.month >= start_month,
                CategoryMonthSnapshot.month <= end_month,
            )
            .order_by(CategoryMonthSnapshot.category_id, CategoryMonthSnapshot.month)
        )
        return list(result.scalars().all())

    async def replace_for_budget(self, budget_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
        """Atomically swap in a freshly computed row set and mark it valid."""
        await self.session.execute(
            delete(CategoryMonthSnapshot).where(CategoryMonthSnapshot.budget_id == budget_id)
        )
        for i in range(0, len(rows), self._BULK_CHUNK):
            chunk = rows[i : i + self._BULK_CHUNK]
            # DO NOTHING absorbs the race where a concurrent request rebuilt
            # and committed first — its rows were computed from the same data.
            await self.session.execute(
                pg_insert(CategoryMonthSnapshot)
                .values(chunk)
                .on_conflict_do_nothing(constraint="uq_snapshot_category_month")
            )
        await self.session.execute(
            pg_insert(BudgetSnapshotMeta)
            .values(budget_id=budget_id)
            .on_conflict_do_update(
                index_elements=[BudgetSnapshotMeta.budget_id],
                set_={"computed_at": func.now()},
            )
        )
        await self.session.flush()
