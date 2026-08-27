from unittest.mock import AsyncMock, MagicMock

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


class TestPromptPlaceholders:
    """The settings UI shows a prompt's placeholders; it must read them from
    the one registry rather than keep a copy."""

    async def test_prompt_rows_carry_their_placeholders(self):
        svc = SettingsService(make_repo(None))
        by_key = {r["key"]: r for r in await svc.get_all_detailed()}
        assert by_key["ai_prompt_suggest_regex"]["placeholders"] == ["{names}"]
        assert by_key["ai_prompt_receipt_gate"]["placeholders"] == []
        assert by_key["ollama_host"]["placeholders"] is None


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


class TestEmptyStringSemantics:
    """An explicit-but-empty DB row is how "vision override off" is stored.
    Every reader must let it beat an env var, or the settings UI shows a
    model the worker correctly ignores."""

    def _repo_with_empty(self, key: str) -> MagicMock:
        repo = MagicMock()
        setting = MagicMock()
        setting.key = key
        setting.value = ""
        repo.get = AsyncMock(return_value=setting)
        repo.get_all = AsyncMock(return_value=[setting])
        return repo

    async def test_get_returns_explicit_empty_over_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_VISION_MODEL", "env-model")
        svc = SettingsService(self._repo_with_empty("ollama_vision_model"))
        assert await svc.get("ollama_vision_model") == ""

    async def test_get_all_returns_explicit_empty_over_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_VISION_MODEL", "env-model")
        svc = SettingsService(self._repo_with_empty("ollama_vision_model"))
        result = await svc.get_all()
        assert result["ollama_vision_model"] == ""

    async def test_get_all_detailed_returns_explicit_empty_over_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_VISION_MODEL", "env-model")
        svc = SettingsService(self._repo_with_empty("ollama_vision_model"))
        detailed = await svc.get_all_detailed()
        row = next(r for r in detailed if r["key"] == "ollama_vision_model")
        assert row["value"] == ""
        assert row["is_overridden"] is True

    async def test_get_all_detailed_env_still_wins_when_no_db_row(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_VISION_MODEL", "env-model")
        svc = SettingsService(make_repo(None))
        detailed = await svc.get_all_detailed()
        row = next(r for r in detailed if r["key"] == "ollama_vision_model")
        assert row["value"] == "env-model"
        assert row["is_overridden"] is False
