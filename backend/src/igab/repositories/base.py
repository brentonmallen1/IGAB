import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == id,  # type: ignore[attr-defined]
                self.model.is_deleted == False,  # type: ignore[attr-defined]  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, id: uuid.UUID) -> ModelT:
        from igab.domain.exceptions import NotFoundError

        obj = await self.get(id)
        if obj is None:
            raise NotFoundError(self.model.__tablename__, str(id))
        return obj

    async def create(self, **kwargs: Any) -> ModelT:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: uuid.UUID, **kwargs: Any) -> ModelT:
        kwargs["updated_at"] = func.now()
        await self.session.execute(
            update(self.model).where(self.model.id == id).values(**kwargs)  # type: ignore[attr-defined]
        )
        await self.session.flush()
        return await self.get_or_raise(id)

    async def soft_delete(self, id: uuid.UUID) -> None:
        await self.session.execute(
            update(self.model)
            .where(self.model.id == id)  # type: ignore[attr-defined]
            .values(is_deleted=True, updated_at=func.now())
        )
        await self.session.flush()
