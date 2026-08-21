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
        # list[Any]: the elements are SQLAlchemy binary expressions whose
        # static types differ per model, and `where(*conditions)` cannot match
        # an overload against the inferred join of them.
        conditions: list[Any] = [self.model.id == id]  # type: ignore
        # Not every model is soft-deletable (e.g. BudgetAssignment)
        if hasattr(self.model, "is_deleted"):
            conditions.append(self.model.is_deleted == False)  # noqa: E712
        result = await self.session.execute(select(self.model).where(*conditions))
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
            update(self.model).where(self.model.id == id).values(**kwargs)  # type: ignore
        )
        await self.session.flush()
        return await self.get_or_raise(id)

    async def soft_delete(self, id: uuid.UUID) -> None:
        await self.session.execute(
            update(self.model)
            .where(self.model.id == id)  # type: ignore
            .values(is_deleted=True, updated_at=func.now())
        )
        await self.session.flush()
