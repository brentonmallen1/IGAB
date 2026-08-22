"""Self-service password change — real bcrypt, service-level (the API test
harness bypasses JWT/bcrypt entirely), plus the endpoint's env-admin refusal."""

import pytest

from igab.config import settings as app_settings
from igab.domain.exceptions import AuthenticationError
from igab.repositories.user_repo import UserRepository
from igab.services.auth_service import AuthService

from .test_budget_membership import as_user


class TestChangePasswordService:
    async def test_change_rotates_the_hash(self, db_session):
        auth = AuthService(UserRepository(db_session))
        user = await auth.create_user(email="p@test.local", password="original-pw")

        await auth.change_password(user, "original-pw", "brand-new-pw")

        access, _ = await auth.login("p@test.local", "brand-new-pw")
        assert access
        with pytest.raises(AuthenticationError):
            await auth.login("p@test.local", "original-pw")

    async def test_wrong_current_password_refused(self, db_session):
        auth = AuthService(UserRepository(db_session))
        user = await auth.create_user(email="q@test.local", password="original-pw")
        with pytest.raises(AuthenticationError):
            await auth.change_password(user, "not-the-password", "whatever-else")
        # Unchanged
        access, _ = await auth.login("q@test.local", "original-pw")
        assert access


class TestChangePasswordEndpoint:
    async def test_env_admin_is_refused_with_the_env_explanation(
        self, db_session, api_client, monkeypatch
    ):
        me = api_client.test_user
        monkeypatch.setattr(app_settings, "ADMIN_EMAIL", me.email)
        resp = await api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "anything", "new_password": "longenough"},
        )
        assert resp.status_code == 403
        assert "ADMIN_PASSWORD" in resp.json()["detail"]

    async def test_wrong_current_is_a_readable_400(self, db_session, api_client):
        # api_client's user has a placeholder (non-bcrypt) hash; verify fails
        # via the malformed-hash path — still a clean 400, never a 500.
        resp = await api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "nope", "new_password": "longenough"},
        )
        assert resp.status_code == 400

    async def test_user_can_change_their_own(self, db_session, api_client):
        auth = AuthService(UserRepository(db_session))
        real = await auth.create_user(email="self@test.local", password="original-pw")
        with as_user(real):
            resp = await api_client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "original-pw", "new_password": "brand-new-pw"},
            )
            assert resp.status_code == 204, resp.text
        access, _ = await auth.login("self@test.local", "brand-new-pw")
        assert access
