import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import SimpleFINConnection


class SimpleFINRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, connection_id: uuid.UUID) -> SimpleFINConnection | None:
        result = await self.session.execute(
            select(SimpleFINConnection).where(SimpleFINConnection.id == connection_id)
        )
        return result.scalar_one_or_none()

    async def get_all_for_user(self, user_id: uuid.UUID) -> list[SimpleFINConnection]:
        result = await self.session.execute(
            select(SimpleFINConnection)
            .where(SimpleFINConnection.user_id == user_id)
            .order_by(SimpleFINConnection.created_at)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> SimpleFINConnection:
        obj = SimpleFINConnection(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, connection_id: uuid.UUID, **kwargs: Any) -> SimpleFINConnection:
        kwargs["updated_at"] = func.now()
        await self.session.execute(
            update(SimpleFINConnection)
            .where(SimpleFINConnection.id == connection_id)
            .values(**kwargs)
        )
        await self.session.flush()
        result = await self.session.execute(
            select(SimpleFINConnection).where(SimpleFINConnection.id == connection_id)
        )
        return result.scalar_one()

    async def delete(self, connection_id: uuid.UUID) -> None:
        from sqlalchemy import delete

        await self.session.execute(
            delete(SimpleFINConnection).where(SimpleFINConnection.id == connection_id)
        )
        await self.session.flush()
