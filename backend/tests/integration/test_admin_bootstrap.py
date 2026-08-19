"""Admin credential sync at boot. ADMIN_PASSWORD in the environment is the
app's ONLY credential source (there is no in-app change-password flow), so
boot must treat it as the truth. The regression: bootstrap created the admin
once and then ignored the env var forever — the first time the operator
edited ADMIN_PASSWORD, login rejected the new value ("Invalid email or
password") with no way back in."""

import pytest

from igab.domain.exceptions import AuthenticationError
from igab.repositories.user_repo import UserRepository
from igab.services.auth_service import AuthService


async def test_env_password_change_resyncs_and_old_password_stops_working(db_session):
    auth = AuthService(UserRepository(db_session))

    assert await auth.sync_admin("admin@test.local", "first-pw") == "created"
    # Unchanged env → boot is a no-op, the hash is not churned
    assert await auth.sync_admin("admin@test.local", "first-pw") is None

    # Operator edits ADMIN_PASSWORD → next boot re-hashes
    assert await auth.sync_admin("admin@test.local", "second-pw") == "updated"

    access, refresh = await auth.login("admin@test.local", "second-pw")
    assert access and refresh
    with pytest.raises(AuthenticationError):
        await auth.login("admin@test.local", "first-pw")


async def test_malformed_stored_hash_is_recovered(db_session):
    """A corrupt hash is unrecoverable through login; re-hashing from env is
    the only way back in, so sync treats it as out-of-sync rather than
    crashing the boot."""
    repo = UserRepository(db_session)
    auth = AuthService(repo)
    await repo.create(email="admin@test.local", password_hash="not-a-bcrypt-hash")

    assert await auth.sync_admin("admin@test.local", "rescue-pw") == "updated"
    access, _ = await auth.login("admin@test.local", "rescue-pw")
    assert access
