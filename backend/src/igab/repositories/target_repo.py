import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import CategoryTarget


class TargetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_category(self, category_id: uuid.UUID) -> CategoryTarget | None:
        result = await self.session.execute(
            select(CategoryTarget).where(CategoryTarget.category_id == category_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs: Any) -> CategoryTarget:
        obj = CategoryTarget(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, target_id: uuid.UUID, **kwargs: Any) -> CategoryTarget:
        kwargs["updated_at"] = func.now()
        await self.session.execute(
            update(CategoryTarget).where(CategoryTarget.id == target_id).values(**kwargs)
        )
        await self.session.flush()
        result = await self.session.execute(
            select(CategoryTarget).where(CategoryTarget.id == target_id)
        )
        return result.scalar_one()

    async def delete(self, category_id: uuid.UUID) -> None:
        from sqlalchemy import delete

        await self.session.execute(
            delete(CategoryTarget).where(CategoryTarget.category_id == category_id)
        )
        await self.session.flush()
