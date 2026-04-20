from unittest.mock import AsyncMock, MagicMock

import pytest

from igab.services.settings_service import DEFAULTS, SettingsService


def make_repo(db_value: str | None = None) -> MagicMock:
    repo = MagicMock()
    if db_value is not None:
        setting = MagicMock()
        setting.value = db_value
        repo.get = AsyncMock(return_value=setting)
    else:
        repo.get = AsyncMock(return_value=None)
    repo.set = AsyncMock()
    repo.get_all = AsyncMock(return_value=[])
    return repo


class TestSettingsServiceGet:
    async def test_returns_db_value(self):
        svc = SettingsService(make_repo("http://db-host:11434"))
        assert await svc.get("ollama_host") == "http://db-host:11434"

    async def test_db_takes_priority_over_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://env-host:11434")
        svc = SettingsService(make_repo("http://db-host:11434"))
        assert await svc.get("ollama_host") == "http://db-host:11434"

    async def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://env-host:11434")
        svc = SettingsService(make_repo(None))
        assert await svc.get("ollama_host") == "http://env-host:11434"

    async def test_falls_back_to_default(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        svc = SettingsService(make_repo(None))
        assert await svc.get("ollama_host") == DEFAULTS["ollama_host"]

    async def test_returns_none_for_unknown_key(self, monkeypatch):
        monkeypatch.delenv("UNKNOWN_KEY", raising=False)
        svc = SettingsService(make_repo(None))
        assert await svc.get("unknown_key") is None

    async def test_model_default(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        svc = SettingsService(make_repo(None))
        assert await svc.get("ollama_model") == DEFAULTS["ollama_model"]


class TestSettingsServiceGetAll:
    async def test_merges_defaults(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        svc = SettingsService(make_repo(None))
        result = await svc.get_all()
        assert result["ollama_host"] == DEFAULTS["ollama_host"]
        assert result["ollama_model"] == DEFAULTS["ollama_model"]

    async def test_db_value_in_get_all(self):
        repo = MagicMock()
        setting = MagicMock()
        setting.key = "ollama_host"
        setting.value = "http://custom:11434"
        repo.get_all = AsyncMock(return_value=[setting])
        svc = SettingsService(repo)
        result = await svc.get_all()
        assert result["ollama_host"] == "http://custom:11434"


class TestSeedFromEnv:
    async def test_seeds_when_not_in_db(self):
        repo = make_repo(None)
        svc = SettingsService(repo)
        await svc.seed_from_env()
        assert repo.set.call_count >= 1

    async def test_skips_when_already_in_db(self):
        repo = MagicMock()
        existing = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.set = AsyncMock()
        svc = SettingsService(repo)
        await svc.seed_from_env()
        repo.set.assert_not_called()
