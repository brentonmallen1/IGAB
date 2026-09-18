"""Minting, listing and revoking read-only API keys.

The guarantees that matter are about reach: a key can never read further than
the person who made it, and it stops working the moment it is revoked.
"""

from igab.db.models import ApiKey
from igab.services.api_key_service import authenticate, hash_key

from .factories import create_budget, create_user


async def _make(api_client, budget_ids, name="Claude on the laptop"):
    return await api_client.post(
        "/api/v1/api-keys",
        json={"name": name, "budget_ids": [str(b) for b in budget_ids]},
    )


class TestCreating:
    async def test_the_key_is_returned_once_and_only_its_hash_is_kept(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()

        made = await _make(api_client, [budget.id])
        assert made.status_code == 201, made.text
        body = made.json()
        raw = body["key"]
        assert raw.startswith("igab_")

        # Not recoverable: the list says which key a row is and nothing more.
        listed = await api_client.get("/api/v1/api-keys")
        row = next(r for r in listed.json() if r["id"] == body["id"])
        assert "key" not in row
        assert row["prefix"] == raw[: len(row["prefix"])]

        stored = await db_session.get(ApiKey, body["id"])
        assert stored is not None
        assert stored.key_hash == hash_key(raw)
        assert raw not in stored.key_hash

    async def test_it_is_read_only(self, api_client, db_session):
        """A scope column exists so that a write scope arriving later is a
        deliberate change rather than an omission."""
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()
        made = await _make(api_client, [budget.id])
        assert made.json()["scopes"] == "read"

    async def test_a_key_cannot_name_a_budget_its_maker_cannot_reach(self, api_client, db_session):
        """The reach rule: a key can never go further than the person who
        made it. Not-found rather than forbidden, so the refusal does not say
        which budget ids exist."""
        stranger = await create_user(db_session)
        theirs = await create_budget(db_session, stranger)
        await db_session.flush()

        refused = await _make(api_client, [theirs.id])
        assert refused.status_code == 404

    async def test_a_key_must_name_at_least_one_budget(self, api_client):
        """A key scoped to nothing would authenticate and read nothing, which
        is a confusing way to spend an afternoon."""
        empty = await _make(api_client, [])
        assert empty.status_code == 422


class TestRevoking:
    async def test_revoke_stops_the_key_working(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()
        made = await _make(api_client, [budget.id])
        raw = made.json()["key"]
        assert await authenticate(db_session, raw) is not None

        gone = await api_client.delete(f"/api/v1/api-keys/{made.json()['id']}")
        assert gone.status_code == 204
        await db_session.flush()

        assert await authenticate(db_session, raw) is None

    async def test_a_revoked_key_stays_listed(self, api_client, db_session):
        """A key that turns up in someone's config or a log has to be
        identifiable after it stops working."""
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()
        made = await _make(api_client, [budget.id])
        await api_client.delete(f"/api/v1/api-keys/{made.json()['id']}")

        listed = await api_client.get("/api/v1/api-keys")
        row = next(r for r in listed.json() if r["id"] == made.json()["id"])
        assert row["revoked_at"] is not None

    async def test_revoking_twice_is_not_an_error(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()
        made = await _make(api_client, [budget.id])
        key_id = made.json()["id"]
        assert (await api_client.delete(f"/api/v1/api-keys/{key_id}")).status_code == 204
        assert (await api_client.delete(f"/api/v1/api-keys/{key_id}")).status_code == 204

    async def test_someone_elses_key_is_not_revocable(self, api_client, db_session):
        stranger = await create_user(db_session)
        theirs = await create_budget(db_session, stranger)
        await db_session.flush()
        key = ApiKey(user_id=stranger.id, name="Theirs", key_hash="x" * 64, prefix="igab_zzzz")
        db_session.add(key)
        await db_session.flush()
        assert theirs is not None

        refused = await api_client.delete(f"/api/v1/api-keys/{key.id}")
        assert refused.status_code == 404


class TestAuthenticate:
    async def test_an_unknown_key_is_refused(self, db_session):
        assert await authenticate(db_session, "igab_nothing-like-a-real-key") is None

    async def test_a_session_token_is_refused(self, db_session):
        assert await authenticate(db_session, "eyJhbGciOiJIUzI1NiJ9.x.y") is None

    async def test_a_key_carries_the_budgets_it_may_read(self, api_client, db_session):
        first = await create_budget(db_session, api_client.test_user, "Household")
        second = await create_budget(db_session, api_client.test_user, "Harborstone")
        await db_session.flush()
        made = await _make(api_client, [first.id, second.id])
        await db_session.flush()

        principal = await authenticate(db_session, made.json()["key"])
        assert principal is not None
        assert set(principal.budget_ids) == {first.id, second.id}
        assert principal.may_read(first.id)

    async def test_a_key_cannot_read_a_budget_it_was_not_given(self, api_client, db_session):
        mine = await create_budget(db_session, api_client.test_user, "Household")
        other = await create_budget(db_session, api_client.test_user, "Harborstone")
        await db_session.flush()
        made = await _make(api_client, [mine.id])
        await db_session.flush()

        principal = await authenticate(db_session, made.json()["key"])
        assert principal is not None
        assert not principal.may_read(other.id)


class TestTheRestApiRefusesAKey:
    async def test_it_says_which_door_the_key_belongs_to(self, db_session):
        """Falling through to the JWT decoder would fail it as an 'invalid
        token' — true, useless, and the kind of answer that costs an
        evening."""
        from httpx import ASGITransport, AsyncClient

        from igab.db.session import get_session
        from igab.main import app

        async def _session_override():
            yield db_session

        app.dependency_overrides[get_session] = _session_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                refused = await client.get(
                    "/api/v1/budgets", headers={"Authorization": "Bearer igab_anything"}
                )
            assert refused.status_code == 401
            assert "MCP" in refused.json()["detail"]
        finally:
            app.dependency_overrides.clear()
