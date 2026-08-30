"""Shared-budget membership semantics — the authorization trust surface.

budget_members is the source of truth: members get full day-to-day use,
owners additionally delete the budget and manage membership, non-members get
404 everywhere (existence must not leak). The foreign-user suites
(test_authorization*.py) already prove the non-member case across every
guard; this file covers the member/owner split and the membership API.
"""

from contextlib import contextmanager

from igab.dependencies import get_current_user
from igab.main import app

from .factories import add_budget_member, create_account, create_budget, create_user


@contextmanager
def as_user(user):
    """Swap the api_client's authenticated user for a block."""
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


async def _shared_budget(db_session, api_client):
    owner = api_client.test_user
    member = await create_user(db_session)
    budget = await create_budget(db_session, owner)
    account = await create_account(db_session, budget, "Checking")
    await add_budget_member(db_session, budget, member, role="member")
    return budget, account, owner, member


class TestMemberAccess:
    async def test_member_sees_and_uses_the_shared_budget(self, db_session, api_client):
        budget, account, _, member = await _shared_budget(db_session, api_client)

        with as_user(member):
            listed = await api_client.get("/api/v1/budgets")
            assert listed.status_code == 200
            mine = {b["id"]: b for b in listed.json()}
            assert str(budget.id) in mine
            assert mine[str(budget.id)]["role"] == "member"

            # Day-to-day use: read accounts, create a transaction, rename
            assert (await api_client.get(f"/api/v1/{budget.id}/accounts")).status_code == 200
            created = await api_client.post(
                f"/api/v1/{budget.id}/transactions",
                json={"account_id": str(account.id), "date": "2026-08-19", "amount": -12.5},
            )
            assert created.status_code in (200, 201), created.text
            renamed = await api_client.patch(
                f"/api/v1/budgets/{budget.id}", json={"name": "Renamed by member"}
            )
            assert renamed.status_code == 200

    async def test_member_cannot_delete_or_manage_members(self, db_session, api_client):
        budget, _, owner, member = await _shared_budget(db_session, api_client)
        outsider = await create_user(db_session)

        with as_user(member):
            assert (await api_client.delete(f"/api/v1/budgets/{budget.id}")).status_code == 403
            add = await api_client.post(
                f"/api/v1/{budget.id}/members", json={"user_id": str(outsider.id)}
            )
            assert add.status_code == 403
            kick = await api_client.delete(f"/api/v1/{budget.id}/members/{owner.id}")
            assert kick.status_code == 403

    async def test_member_cannot_export_or_restore(self, db_session, api_client):
        """A snapshot is the input to "create a budget I own containing your
        data" — the same class of decision as deleting a budget. A member who
        wants the numbers has /{budget_id}/reports/export."""
        budget, _, _, member = await _shared_budget(db_session, api_client)

        with as_user(member):
            export = await api_client.get(f"/api/v1/budgets/{budget.id}/snapshot")
            assert export.status_code == 403
            keep = await api_client.post(f"/api/v1/budgets/{budget.id}/snapshots")
            assert keep.status_code == 403
            restore = await api_client.post(
                f"/api/v1/budgets/{budget.id}/snapshot/restore",
                files={"file": ("s.igab.zip", b"x", "application/zip")},
                data={"confirm_name": "whatever"},
            )
            assert restore.status_code == 403
            # Listing stays open: seeing that backups exist is not the same
            # as being able to take one away.
            listed = await api_client.get(f"/api/v1/budgets/{budget.id}/snapshots")
            assert listed.status_code == 200

    async def test_member_can_leave(self, db_session, api_client):
        budget, _, _, member = await _shared_budget(db_session, api_client)

        with as_user(member):
            left = await api_client.delete(f"/api/v1/{budget.id}/members/{member.id}")
            assert left.status_code == 204
            # Gone from their world entirely
            assert (await api_client.get(f"/api/v1/budgets/{budget.id}")).status_code == 404
            assert (await api_client.get(f"/api/v1/{budget.id}/accounts")).status_code == 404


class TestOwnerControls:
    async def test_owner_shares_and_revokes(self, db_session, api_client):
        owner = api_client.test_user
        other = await create_user(db_session)
        budget = await create_budget(db_session, owner)

        added = await api_client.post(
            f"/api/v1/{budget.id}/members", json={"user_id": str(other.id)}
        )
        assert added.status_code == 201
        assert added.json()["role"] == "member"

        dup = await api_client.post(
            f"/api/v1/{budget.id}/members", json={"user_id": str(other.id)}
        )
        assert dup.status_code == 409

        with as_user(other):
            assert (await api_client.get(f"/api/v1/budgets/{budget.id}")).status_code == 200

        removed = await api_client.delete(f"/api/v1/{budget.id}/members/{other.id}")
        assert removed.status_code == 204

        with as_user(other):
            # Revoked → the budget no longer exists for them
            assert (await api_client.get(f"/api/v1/budgets/{budget.id}")).status_code == 404
            assert (await api_client.get(f"/api/v1/{budget.id}/transactions")).status_code == 404

    async def test_last_owner_cannot_be_removed(self, db_session, api_client):
        owner = api_client.test_user
        budget = await create_budget(db_session, owner)
        resp = await api_client.delete(f"/api/v1/{budget.id}/members/{owner.id}")
        assert resp.status_code == 400
        assert "owner" in resp.json()["detail"].lower()

    async def test_inactive_user_cannot_be_added(self, db_session, api_client):
        owner = api_client.test_user
        budget = await create_budget(db_session, owner)
        inactive = await create_user(db_session)
        inactive.is_active = False
        await db_session.flush()
        resp = await api_client.post(
            f"/api/v1/{budget.id}/members", json={"user_id": str(inactive.id)}
        )
        assert resp.status_code == 404


class TestCreationGrantsOwnership:
    async def test_created_budget_lists_with_owner_role(self, db_session, api_client):
        created = await api_client.post("/api/v1/budgets", json={"name": "Fresh"})
        assert created.status_code == 201
        listed = await api_client.get("/api/v1/budgets")
        roles = {b["name"]: b["role"] for b in listed.json()}
        assert roles["Fresh"] == "owner"

    async def test_change_log_records_the_actor(self, db_session, api_client):
        budget, account, owner, member = await _shared_budget(db_session, api_client)
        member.display_name = "Partner"
        await db_session.flush()

        with as_user(member):
            resp = await api_client.post(
                f"/api/v1/{budget.id}/transactions",
                json={"account_id": str(account.id), "date": "2026-08-19", "amount": -5},
            )
            assert resp.status_code in (200, 201)

        changes = await api_client.get(f"/api/v1/{budget.id}/changes")
        assert changes.status_code == 200
        newest = changes.json()["changes"][0]
        assert newest["user_id"] == str(member.id)
        assert newest["user_display_name"] == "Partner"
