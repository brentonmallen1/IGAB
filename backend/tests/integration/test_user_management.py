"""User administration: admin-only mutations, the env-admin's special status,
and the global-surface gates (settings writes, backups) that go live the
moment a second user exists."""

from igab.config import settings as app_settings

from .factories import create_user
from .test_budget_membership import as_user


class TestUserEndpoints:
    async def test_any_user_can_list_users(self, db_session, api_client):
        plain = await create_user(db_session)
        with as_user(plain):
            resp = await api_client.get("/api/v1/users")
            assert resp.status_code == 200
            assert any(u["id"] == str(plain.id) for u in resp.json())

    async def test_non_admin_cannot_create_or_edit_users(self, db_session, api_client):
        plain = await create_user(db_session)
        with as_user(plain):
            create = await api_client.post(
                "/api/v1/users",
                json={"email": "new@example.com", "password": "longenough"},
            )
            assert create.status_code == 403
            edit = await api_client.patch(
                f"/api/v1/users/{plain.id}", json={"display_name": "Sneaky"}
            )
            assert edit.status_code == 403

    async def test_admin_creates_and_edits_users(self, db_session, api_client):
        created = await api_client.post(
            "/api/v1/users",
            json={"email": "partner@example.com", "password": "longenough", "display_name": "P"},
        )
        assert created.status_code == 201, created.text
        uid = created.json()["id"]

        dup = await api_client.post(
            "/api/v1/users", json={"email": "partner@example.com", "password": "longenough"}
        )
        assert dup.status_code == 409

        edited = await api_client.patch(
            f"/api/v1/users/{uid}", json={"display_name": "Partner", "is_active": False}
        )
        assert edited.status_code == 200
        assert edited.json()["display_name"] == "Partner"
        assert edited.json()["is_active"] is False

    async def test_admin_cannot_deactivate_self(self, db_session, api_client):
        me = api_client.test_user
        resp = await api_client.patch(f"/api/v1/users/{me.id}", json={"is_active": False})
        assert resp.status_code == 400

    async def test_env_admin_account_is_protected(self, db_session, api_client, monkeypatch):
        env_admin = await create_user(db_session, email="root@test.local", is_admin=True)
        monkeypatch.setattr(app_settings, "ADMIN_EMAIL", "root@test.local")

        deact = await api_client.patch(f"/api/v1/users/{env_admin.id}", json={"is_active": False})
        assert deact.status_code == 400
        reset = await api_client.patch(
            f"/api/v1/users/{env_admin.id}", json={"password": "newpassword"}
        )
        assert reset.status_code == 400
        assert "ADMIN_PASSWORD" in reset.json()["detail"]

        # The listing tells the UI which account is env-managed
        listing = await api_client.get("/api/v1/users")
        flags = {u["email"]: u["is_env_admin"] for u in listing.json()}
        assert flags["root@test.local"] is True
        assert all(v is False for e, v in flags.items() if e != "root@test.local")

    async def test_short_password_rejected(self, db_session, api_client):
        resp = await api_client.post(
            "/api/v1/users", json={"email": "s@example.com", "password": "short"}
        )
        assert resp.status_code == 422


class TestGlobalSurfaceGates:
    async def test_non_admin_cannot_write_settings_or_run_backups(self, db_session, api_client):
        plain = await create_user(db_session)
        with as_user(plain):
            reads = await api_client.get("/api/v1/settings")
            assert reads.status_code == 200
            write = await api_client.put("/api/v1/settings/ollama_model", json={"value": "gemma4"})
            assert write.status_code == 403
            run = await api_client.post("/api/v1/backups/run")
            assert run.status_code == 403
            restore = await api_client.post("/api/v1/backups/restore", json={"filename": "x.dump"})
            assert restore.status_code == 403

    async def test_admin_can_still_write_settings(self, db_session, api_client):
        resp = await api_client.put("/api/v1/settings/ollama_model", json={"value": "gemma4"})
        assert resp.status_code == 200
