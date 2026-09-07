"""Tags apply to categories. The payee routes are gone, and each migration
that removed payee memberships left a notice the Tags panel shows until
dismissed."""

from igab.guide.repo import GuideRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags

from .factories import create_budget, create_payee


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await seed_system_tags(db_session, budget.id)
    tag = await TagRepository(db_session).get_system_tag(budget.id, "subscription")
    payee = await create_payee(db_session, budget, "Streaming Co")
    await db_session.commit()
    return budget, tag, payee


async def test_the_payee_tag_routes_are_gone(db_session, api_client):
    """They used to exist and refuse the category-only tags. Now every tag is
    category-only, so the routes went rather than refusing everything — an
    endpoint that accepts writes nothing reads is worse than one that is not
    there, because it looks like it works."""
    budget, tag, payee = await _setup(db_session, api_client)
    r = await api_client.put(
        f"/api/v1/{budget.id}/payees/{payee.id}/tags", json={"tag_ids": [str(tag.id)]}
    )
    assert r.status_code == 404, r.text
    r = await api_client.post(
        f"/api/v1/{budget.id}/payees/{payee.id}/tags/add", json={"tag_ids": [str(tag.id)]}
    )
    assert r.status_code == 404, r.text


async def test_a_notice_is_listed_until_dismissed(db_session, api_client):
    budget, _, _ = await _setup(db_session, api_client)
    await GuideRepository(db_session).set_state(
        budget.id, "notice:subscription_tag_moved", {"payee_tags_removed": 3}
    )
    await db_session.commit()

    r = await api_client.get(f"/api/v1/{budget.id}/tags/notices")
    assert r.status_code == 200, r.text
    assert r.json() == [{"key": "subscription_tag_moved", "payload": {"payee_tags_removed": 3}}]

    r = await api_client.delete(f"/api/v1/{budget.id}/tags/notices/subscription_tag_moved")
    assert r.status_code == 204
    assert (await api_client.get(f"/api/v1/{budget.id}/tags/notices")).json() == []
