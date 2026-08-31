"""Opt-in update check: off by default (no GitHub contact), on when enabled,
and version comparison that never nags dev builds or unparseable tags."""

import pytest

from igab.services import update_service


@pytest.fixture(autouse=True)
def clear_release_cache():
    update_service._cache.clear()
    yield
    update_service._cache.clear()


class TestVersionCompare:
    def test_newer_patch_and_minor_and_major(self):
        assert update_service.is_newer("v1.0.1", "v1.0.0")
        assert update_service.is_newer("1.1.0", "1.0.9")
        assert update_service.is_newer("v2.0.0", "v1.9.9")

    def test_equal_or_older_is_not_newer(self):
        assert not update_service.is_newer("v1.0.0", "v1.0.0")
        assert not update_service.is_newer("v1.0.0", "1.0.0")
        assert not update_service.is_newer("v1.0.0", "v1.0.1")

    def test_dev_and_garbage_never_flag_an_update(self):
        assert not update_service.is_newer("v1.0.0", "dev")
        assert not update_service.is_newer("nightly", "v1.0.0")
        assert not update_service.is_newer(None, "v1.0.0")


class TestUpdateStatusEndpoint:
    async def test_disabled_by_default_and_never_contacts_github(self, api_client, monkeypatch):
        def boom(*args, **kwargs):  # pragma: no cover - must not be reached
            raise AssertionError("update check contacted GitHub while disabled")

        monkeypatch.setattr(update_service, "fetch_latest_release", boom)
        resp = await api_client.get("/api/v1/system/update-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["update_available"] is False
        assert body["latest_version"] is None

    async def test_enabled_reports_available_update(self, api_client, monkeypatch):
        async def fake_fetch():
            return "v9.9.9", "https://github.com/brentonmallen1/IGAB/releases/tag/v9.9.9"

        monkeypatch.setattr(update_service, "fetch_latest_release", fake_fetch)
        monkeypatch.setenv("APP_VERSION", "1.0.0")
        await api_client.put("/api/v1/settings/update_check_enabled", json={"value": "true"})
        resp = await api_client.get("/api/v1/system/update-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["current_version"] == "1.0.0"
        assert body["latest_version"] == "v9.9.9"
        assert body["update_available"] is True
        assert body["release_url"].endswith("v9.9.9")

    async def test_enabled_dev_build_reports_latest_without_nagging(self, api_client, monkeypatch):
        async def fake_fetch():
            return "v9.9.9", "https://example.test/release"

        monkeypatch.setattr(update_service, "fetch_latest_release", fake_fetch)
        monkeypatch.delenv("APP_VERSION", raising=False)
        await api_client.put("/api/v1/settings/update_check_enabled", json={"value": "true"})
        resp = await api_client.get("/api/v1/system/update-status")
        body = resp.json()
        assert body["current_version"] == "dev"
        assert body["latest_version"] == "v9.9.9"
        assert body["update_available"] is False

    async def test_setting_rejects_non_boolean(self, api_client):
        resp = await api_client.put("/api/v1/settings/update_check_enabled", json={"value": "yes"})
        assert resp.status_code == 422
