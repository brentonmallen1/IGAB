import os

from igab.repositories.settings_repo import SettingsRepository

DEFAULTS: dict[str, str] = {
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.2",
}


class SettingsService:
    def __init__(self, repo: SettingsRepository) -> None:
        self.repo = repo

    async def get(self, key: str) -> str | None:
        db_val = await self.repo.get(key)
        if db_val is not None and db_val.value is not None:
            return db_val.value
        env_val = os.getenv(key.upper())
        if env_val:
            return env_val
        return DEFAULTS.get(key)

    async def get_all(self) -> dict[str, str | None]:
        rows = await self.repo.get_all()
        db_map = {r.key: r.value for r in rows}
        result: dict[str, str | None] = {}
        for key, default in DEFAULTS.items():
            env_val = os.getenv(key.upper())
            result[key] = db_map.get(key) or env_val or default
        return result

    async def set(self, key: str, value: str) -> None:
        await self.repo.set(key, value)

    async def seed_from_env(self) -> None:
        """Seed Ollama defaults from env vars if not already set in DB."""
        from igab.config import settings

        for key, env_val in [
            ("ollama_host", settings.OLLAMA_HOST),
            ("ollama_model", settings.OLLAMA_MODEL),
        ]:
            existing = await self.repo.get(key)
            if existing is None and env_val:
                await self.repo.set(key, env_val)
