"""The stored YNAB plan months of an import (`db.models.ImportPlanMonth`).

Read only for display — the Budget page's read-only months before the import
and the envelope series' history — never by a walk. Written once, by the
importer.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import ImportPlanMonth


class ImportPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_create(self, rows: list[ImportPlanMonth]) -> None:
        self.session.add_all(rows)
        await self.session.flush()

    async def earliest_month(self, budget_id: uuid.UUID) -> date | None:
        """The first month the import kept YNAB's figures for, or None for a
        budget whose import stored none (any import before they were kept)."""
        return await self.session.scalar(
            select(func.min(ImportPlanMonth.month)).where(ImportPlanMonth.budget_id == budget_id)
        )

    async def month(self, budget_id: uuid.UUID, month: date) -> list[ImportPlanMonth]:
        """One month's rows in YNAB's own display order."""
        result = await self.session.execute(
            select(ImportPlanMonth)
            .where(ImportPlanMonth.budget_id == budget_id, ImportPlanMonth.month == month)
            .order_by(ImportPlanMonth.position)
        )
        return list(result.scalars().all())

    async def available_before(
        self, budget_id: uuid.UUID, before: date
    ) -> dict[uuid.UUID, dict[date, Decimal]]:
        """{category: {month: YNAB's Available}} for every stored month before
        `before`, rows with no category or no readable figure left out."""
        result = await self.session.execute(
            select(
                ImportPlanMonth.category_id, ImportPlanMonth.month, ImportPlanMonth.available
            ).where(
                ImportPlanMonth.budget_id == budget_id,
                ImportPlanMonth.month < before,
                ImportPlanMonth.category_id.is_not(None),
                ImportPlanMonth.available.is_not(None),
            )
        )
        out: dict[uuid.UUID, dict[date, Decimal]] = {}
        for category_id, month, available in result.all():
            out.setdefault(category_id, {})[month] = available
        return out
