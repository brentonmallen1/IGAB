"""Database access for the Guide's own two tables."""

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import GuideBinding, GuideState


class GuideRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── bindings ─────────────────────────────────────────────────────────────

    async def bindings(self, budget_id: uuid.UUID) -> list[GuideBinding]:
        result = await self.session.execute(
            select(GuideBinding)
            .where(GuideBinding.budget_id == budget_id)
            .order_by(GuideBinding.created_at)
        )
        return list(result.scalars().all())

    async def replace_concept(
        self, budget_id: uuid.UUID, concept_key: str, rows: list[dict[str, Any]]
    ) -> list[GuideBinding]:
        """Swap every stored row for one concept.

        Replace rather than merge: the binding sheet always submits the whole
        picture for a concept, and a partial update would leave a stale
        dismissal or a removed entity behind — both of which would keep
        speaking after the user thought they had cleared them.
        """
        await self.session.execute(
            delete(GuideBinding).where(
                GuideBinding.budget_id == budget_id,
                GuideBinding.concept_key == concept_key,
            )
        )
        created: list[GuideBinding] = []
        for row in rows:
            binding = GuideBinding(budget_id=budget_id, concept_key=concept_key, **row)
            self.session.add(binding)
            created.append(binding)
        await self.session.flush()
        return created

    async def clear_concept(self, budget_id: uuid.UUID, concept_key: str) -> None:
        """Reset to automatic — what "use the app's guess again" means."""
        await self.session.execute(
            delete(GuideBinding).where(
                GuideBinding.budget_id == budget_id,
                GuideBinding.concept_key == concept_key,
            )
        )
        await self.session.flush()

    # ── state ────────────────────────────────────────────────────────────────

    async def state(self, budget_id: uuid.UUID) -> dict[str, dict]:
        result = await self.session.execute(
            select(GuideState).where(GuideState.budget_id == budget_id)
        )
        return {row.key: row.value for row in result.scalars().all()}

    async def set_state(self, budget_id: uuid.UUID, key: str, value: dict) -> None:
        existing = (
            await self.session.execute(
                select(GuideState).where(GuideState.budget_id == budget_id, GuideState.key == key)
            )
        ).scalar_one_or_none()
        if existing is None:
            self.session.add(GuideState(budget_id=budget_id, key=key, value=value))
        else:
            existing.value = value
        await self.session.flush()

    async def delete_state(self, budget_id: uuid.UUID, key: str) -> None:
        await self.session.execute(
            delete(GuideState).where(GuideState.budget_id == budget_id, GuideState.key == key)
        )
        await self.session.flush()
