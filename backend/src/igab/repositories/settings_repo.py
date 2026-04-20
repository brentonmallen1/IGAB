from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import AppSetting


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> AppSetting | None:
        result = await self.session.execute(select(AppSetting).where(AppSetting.key == key))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[AppSetting]:
        result = await self.session.execute(select(AppSetting).order_by(AppSetting.key))
        return list(result.scalars().all())

    async def set(self, key: str, value: str) -> AppSetting:
        existing = await self.get(key)
        if existing is None:
            obj = AppSetting(key=key, value=value)
            self.session.add(obj)
            await self.session.flush()
            await self.session.refresh(obj)
            return obj
        existing.value = value
        self.session.add(existing)
        await self.session.flush()
        return existing
