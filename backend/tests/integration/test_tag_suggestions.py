"""Proposals the import review offers, and the bulk write that accepts them.

The point of the endpoint pair is that a suggestion is *not* a write. The
importer applies two keys it is confident about; everything else is offered to
a person and stays offered until they say so.
"""

import pytest

from igab.repositories.tag_repo import TagRepository, seed_system_tags

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_user,
)


async def _budget_with(db_session, api_client, categories, *, group="Everyday", **group_kw):
    budget = await create_budget(db_session, api_client.test_user)
    grp = await create_category_group(db_session, budget, name=group, **group_kw)
    made = {}
    for name in categories:
        made[name] = await create_category(db_session, budget, grp, name=name)
    await seed_system_tags(db_session, budget.id)
    await db_session.flush()
    return budget, grp, made


async def _suggestions(api_client, budget_id):
    r = await api_client.get(f"/api/v1/{budget_id}/tags/suggestions")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_it_proposes_the_keys_the_importer_never_assigns(db_session, api_client):
    budget, _, made = await _budget_with(db_session, api_client, ["Groceries", "Amazon Prime"])

    by_category = {s["category_id"]: s for s in await _suggestions(api_client, budget.id)}

    assert by_category[str(made["Groceries"].id)]["system_key"] == "essential"
    assert by_category[str(made["Amazon Prime"].id)]["system_key"] == "subscription"
    # Said out loud, so a person can check the guess rather than take it on faith.
    assert by_category[str(made["Groceries"].id)]["matched_on"] == "Groceries"
    # And which of them the importer would have written, which is none of these.
    assert all(not s["applied_on_import"] for s in by_category.values())


@pytest.mark.asyncio
async def test_a_category_that_already_carries_the_key_is_not_re_proposed(db_session, api_client):
    budget, _, made = await _budget_with(db_session, api_client, ["Groceries"])
    repo = TagRepository(db_session)
    essential = await repo.get_system_tag(budget.id, "essential")
    await repo.set_category_tags(made["Groceries"].id, [essential.id])
    await db_session.flush()

    assert await _suggestions(api_client, budget.id) == []


@pytest.mark.asyncio
async def test_hidden_categories_are_still_offered(db_session, api_client):
    """A tag overrides classification, so hiding a wrong one keeps it wrong.

    A real import put "Harborstone Savings" in YNAB's Hidden Categories group and
    tagged it Savings; the savings report has counted it ever since.
    """
    budget, _, made = await _budget_with(db_session, api_client, ["Harborstone Savings"])
    made["Harborstone Savings"].is_hidden = True
    await db_session.flush()

    keys = {s["system_key"] for s in await _suggestions(api_client, budget.id)}
    assert "savings" in keys


@pytest.mark.asyncio
async def test_system_group_categories_are_not_offered(db_session, api_client):
    """Income holds no envelope money; classifying its spending is meaningless."""
    budget, _, _ = await _budget_with(
        db_session, api_client, ["Savings Transfer"], group="Income", is_system=True
    )
    assert await _suggestions(api_client, budget.id) == []


@pytest.mark.asyncio
async def test_it_seeds_a_budget_missing_a_system_tag(db_session, api_client):
    """The backfill migration predates three of the six keys.

    Suggesting a key whose tag row does not exist would offer a choice that
    cannot be accepted.
    """
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, name="Everyday")
    await create_category(db_session, budget, group, name="Groceries")
    await db_session.flush()  # deliberately never seeded

    assert {s["system_key"] for s in await _suggestions(api_client, budget.id)} == {"essential"}

    tags = await TagRepository(db_session).list_for_budget(budget.id)
    assert "essential" in {t.system_key for t in tags}


@pytest.mark.asyncio
async def test_wishlist_is_never_proposed(db_session, api_client):
    budget, _, _ = await _budget_with(db_session, api_client, ["Wishlist Fund"])
    keys = {s["system_key"] for s in await _suggestions(api_client, budget.id)}
    assert "wishlist" not in keys


class TestBulkWrite:
    @pytest.mark.asyncio
    async def test_it_sets_many_categories_in_one_call(self, db_session, api_client):
        budget, _, made = await _budget_with(
            db_session, api_client, ["Groceries", "Rent", "Amazon Prime"]
        )
        repo = TagRepository(db_session)
        essential = await repo.get_system_tag(budget.id, "essential")
        subscription = await repo.get_system_tag(budget.id, "subscription")

        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/tags",
            json={
                "updates": [
                    {"category_id": str(made["Groceries"].id), "tag_ids": [str(essential.id)]},
                    {"category_id": str(made["Rent"].id), "tag_ids": [str(essential.id)]},
                    {
                        "category_id": str(made["Amazon Prime"].id),
                        "tag_ids": [str(subscription.id)],
                    },
                ]
            },
        )
        assert r.status_code == 204, r.text

        held = await repo.get_tags_for_categories([c.id for c in made.values()])
        assert {t.system_key for t in held[made["Groceries"].id]} == {"essential"}
        assert {t.system_key for t in held[made["Rent"].id]} == {"essential"}
        assert {t.system_key for t in held[made["Amazon Prime"].id]} == {"subscription"}

    @pytest.mark.asyncio
    async def test_an_empty_list_removes_every_tag(self, db_session, api_client):
        """Untagging is how a wrong guess is undone, so it must be expressible."""
        budget, _, made = await _budget_with(db_session, api_client, ["Groceries"])
        repo = TagRepository(db_session)
        essential = await repo.get_system_tag(budget.id, "essential")
        await repo.set_category_tags(made["Groceries"].id, [essential.id])
        await db_session.flush()

        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/tags",
            json={"updates": [{"category_id": str(made["Groceries"].id), "tag_ids": []}]},
        )
        assert r.status_code == 204, r.text
        held = await repo.get_tags_for_categories([made["Groceries"].id])
        assert held[made["Groceries"].id] == []

    @pytest.mark.asyncio
    async def test_a_stray_id_fails_the_whole_call(self, db_session, api_client):
        """Half a review applied is worse than none: every id is checked first."""
        import uuid

        budget, _, made = await _budget_with(db_session, api_client, ["Groceries"])
        repo = TagRepository(db_session)
        essential = await repo.get_system_tag(budget.id, "essential")

        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/tags",
            json={
                "updates": [
                    {"category_id": str(made["Groceries"].id), "tag_ids": [str(essential.id)]},
                    {"category_id": str(uuid.uuid4()), "tag_ids": [str(essential.id)]},
                ]
            },
        )
        assert r.status_code == 404
        held = await repo.get_tags_for_categories([made["Groceries"].id])
        assert held[made["Groceries"].id] == []

    @pytest.mark.asyncio
    async def test_the_wishlist_tag_cannot_be_set_by_hand(self, db_session, api_client):
        """It is derived from the wish -> envelope link and would be overruled."""
        budget, _, made = await _budget_with(db_session, api_client, ["Groceries"])
        repo = TagRepository(db_session)
        wishlist = await repo.get_system_tag(budget.id, "wishlist")

        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/tags",
            json={"updates": [{"category_id": str(made["Groceries"].id), "tag_ids": [str(wishlist.id)]}]},
        )
        assert r.status_code == 400
        assert "wishlist" in r.json()["detail"].lower()
