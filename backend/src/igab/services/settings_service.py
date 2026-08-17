import os

from igab.repositories.settings_repo import SettingsRepository
from igab.services.ai_prompts import DEFAULT_PROMPTS

DEFAULTS: dict[str, str] = {
    # Master switch for AI features — false until the user explicitly enables
    "ai_enabled": "false",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.2",
    # Optional model used for vision tasks (receipt extraction). Empty means
    # "use ollama_model".
    "ollama_vision_model": "",
    # 'auto' = enable thinking only when the model advertises the capability;
    # 'on'/'off' force it.
    "ai_thinking": "auto",
    # JSON objects merged into every Ollama request's options. Vision options
    # are merged on top for vision tasks only.
    "ollama_options": "{}",
    "ollama_vision_options": "{}",
    # Request timeout for vision calls — big models on modest hardware are slow.
    "ai_vision_timeout_s": "300",
    # Backup agent settings — polled from the DB by scripts/db-backup.sh each
    # cycle, so UI changes apply without a container restart. Env vars
    # (BACKUP_INTERVAL_HOURS etc.) remain the defaults/fallback.
    "backup_interval_hours": "24",
    "backup_keep_days": "30",
    "backup_keep_min": "7",
    "backup_age_recipient": "",
    # Opt-in check against GitHub releases for self-hosted installs; off by
    # default — the app never phones home unless this is switched on.
    "update_check_enabled": "false",
    # How long finished (done/error) AI activity log entries are kept before
    # the nightly cleanup removes them. 0 = keep forever. Transactions and
    # their attachments are never touched — only the log rows and any
    # job-owned staging files.
    "ai_activity_retention_days": "30",
    **DEFAULT_PROMPTS,
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

    async def get_all_detailed(self) -> list[dict]:
        """All settings with override state, for the settings UI."""
        rows = await self.repo.get_all()
        db_map = {r.key: r.value for r in rows}
        result = []
        for key, default in DEFAULTS.items():
            env_val = os.getenv(key.upper())
            db_val = db_map.get(key)
            result.append(
                {
                    "key": key,
                    "value": db_val or env_val or default,
                    "is_overridden": db_val is not None,
                    "default_value": default,
                }
            )
        return result

    async def set(self, key: str, value: str) -> None:
        await self.repo.set(key, value)

    async def unset(self, key: str) -> None:
        """Remove the stored override so the key reverts to env/default."""
        await self.repo.delete(key)

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
