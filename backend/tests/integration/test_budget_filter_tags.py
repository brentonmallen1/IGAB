"""A saved filter can follow a tag.

A filter was a frozen list of category ids: tag a new category Essential and
the "Essentials" filter did not know. The tag axis makes the filter a rule —
named categories plus every category carrying one of its tags, resolved on
the server (one home) so the grid and a report handed a filter_id agree.
"""

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_tag,
)


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, "Everyday")
    rent = await create_category(db_session, budget, group, "Rent")
    groceries = await create_category(db_session, budget, group, "Groceries")
    fun = await create_category(db_session, budget, group, "Fun")
    essential = await create_tag(db_session, budget, "Essential")
    await db_session.commit()
    return budget, rent, groceries, fun, essential


async def _tag(api_client, budget, category, tag_ids):
    r = await api_client.put(
        f"/api/v1/{budget.id}/categories/{category.id}/tags",
        json={"tag_ids": [str(t) for t in tag_ids]},
    )
    assert r.status_code == 200, r.text


async def _create(api_client, budget, **body):
    body.setdefault("name", "Essentials")
    r = await api_client.post(f"/api/v1/{budget.id}/filters", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _read(api_client, filter_id):
    r = await api_client.get(f"/api/v1/filters/{filter_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def test_tagging_a_category_later_makes_it_appear(db_session, api_client):
    budget, rent, groceries, fun, essential = await _setup(db_session, api_client)
    await _tag(api_client, budget, rent, [essential.id])
    created = await _create(api_client, budget, tag_ids=[str(essential.id)])
    assert created["tag_ids"] == [str(essential.id)]
    assert created["category_ids"] == []
    assert created["category_ids_effective"] == [str(rent.id)]

    await _tag(api_client, budget, groceries, [essential.id])

    after = await _read(api_client, created["id"])
    assert sorted(after["category_ids_effective"]) == sorted([str(rent.id), str(groceries.id)])


async def test_removing_the_tag_removes_the_category(db_session, api_client):
    budget, rent, _, _, essential = await _setup(db_session, api_client)
    await _tag(api_client, budget, rent, [essential.id])
    created = await _create(api_client, budget, tag_ids=[str(essential.id)])
    assert created["category_ids_effective"] == [str(rent.id)]

    await _tag(api_client, budget, rent, [])

    assert (await _read(api_client, created["id"]))["category_ids_effective"] == []


async def test_an_explicit_selection_survives_beside_the_tag(db_session, api_client):
    budget, rent, _, fun, essential = await _setup(db_session, api_client)
    await _tag(api_client, budget, rent, [essential.id])
    created = await _create(
        api_client, budget, category_ids=[str(fun.id)], tag_ids=[str(essential.id)]
    )
    assert created["category_ids"] == [str(fun.id)]
    assert sorted(created["category_ids_effective"]) == sorted([str(fun.id), str(rent.id)])
    # Untagging leaves the named one.
    await _tag(api_client, budget, rent, [])
    assert (await _read(api_client, created["id"]))["category_ids_effective"] == [str(fun.id)]


async def test_the_list_carries_the_effective_set_for_every_filter(db_session, api_client):
    budget, rent, groceries, fun, essential = await _setup(db_session, api_client)
    await _tag(api_client, budget, rent, [essential.id])
    await _create(api_client, budget, name="Essentials", tag_ids=[str(essential.id)])
    await _create(api_client, budget, name="Just fun", category_ids=[str(fun.id)])
    listed = (await api_client.get(f"/api/v1/{budget.id}/filters")).json()
    by_name = {f["name"]: f for f in listed}
    assert by_name["Essentials"]["category_ids_effective"] == [str(rent.id)]
    assert by_name["Just fun"]["category_ids_effective"] == [str(fun.id)]


async def test_patch_replaces_the_tag_set(db_session, api_client):
    budget, rent, _, _, essential = await _setup(db_session, api_client)
    await _tag(api_client, budget, rent, [essential.id])
    created = await _create(api_client, budget)
    r = await api_client.patch(
        f"/api/v1/filters/{created['id']}", json={"tag_ids": [str(essential.id)]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["category_ids_effective"] == [str(rent.id)]
    r = await api_client.patch(f"/api/v1/filters/{created['id']}", json={"tag_ids": []})
    assert r.json()["tag_ids"] == [] and r.json()["category_ids_effective"] == []


async def test_a_tag_from_another_budget_is_refused(db_session, api_client):
    budget, *_ = await _setup(db_session, api_client)
    other = await create_budget(db_session, api_client.test_user, name="Other")
    foreign = await create_tag(db_session, other, "Theirs")
    await db_session.commit()
    r = await api_client.post(
        f"/api/v1/{budget.id}/filters", json={"name": "X", "tag_ids": [str(foreign.id)]}
    )
    assert r.status_code == 400
