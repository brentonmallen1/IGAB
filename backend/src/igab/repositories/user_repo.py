import uuid

from sqlalchemy import select

from igab.db.models import User
from igab.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get(self, id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == id, User.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email, User.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()
