"""One tag's checklist: every category it could be on, changed from the tag's side.

`services/tag_membership.py` writes the same `category_tags` records the
inspector does, plus the savings mode per row, and one save is one undo.

Invented names throughout.
"""

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_tag,
    tag_with_system_tags,
)


async def _world(db_session, api_client) -> dict:
    budget = await create_budget(db_session, api_client.test_user)
    goals = await create_category_group(db_session, budget, "Goals")
    everyday = await create_category_group(db_session, budget, "Everyday")
    income = await create_category_group(db_session, budget, "Income", is_system=True)
    w = {
        "budget": budget,
        "fund": await create_category(db_session, budget, goals, "Emergency Fund"),
        "general": await create_category(db_session, budget, goals, "General Savings"),
        "groceries": await create_category(db_session, budget, everyday, "Groceries"),
        "paycheck": await create_category(db_session, budget, income, "Northwind Payserv"),
    }
    await tag_with_system_tags(db_session, w["general"], "savings")
    await db_session.commit()
    return w


async def _tags(api_client, budget) -> dict:
    rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
    return {t["system_key"] or t["name"]: t for t in rows}


async def _membership(api_client, budget, tag_id) -> dict:
    r = await api_client.get(f"/api/v1/{budget.id}/tags/{tag_id}/membership")
    assert r.status_code == 200, r.text
    return {c["name"]: c for c in r.json()["categories"]}


async def _put(api_client, budget, tag_id, **body):
    return await api_client.put(f"/api/v1/{budget.id}/tags/{tag_id}/categories", json=body)


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text


async def test_get_serves_every_taggable_category_with_its_savings_role(db_session, api_client):
    w = await _world(db_session, api_client)
    tags = await _tags(api_client, w["budget"])

    r = await api_client.get(
        f"/api/v1/{w['budget'].id}/tags/{tags['emergency_fund']['id']}/membership"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tag"] == {
        "id": tags["emergency_fund"]["id"],
        "name": "Emergency fund",
        "system_key": "emergency_fund",
        "savings_tag": True,
    }
    rows = {c["name"]: c for c in body["categories"]}
    assert "Northwind Payserv" not in rows, "the income group is never taggable"
    assert rows["General Savings"]["savings_role"] == "sent_out"
    assert rows["General Savings"]["member"] is False
    assert rows["Groceries"]["savings_role"] == "none"
    assert rows["Groceries"]["group_name"] == "Everyday"
    assert rows["Groceries"]["savings_mode"] is None
    assert rows["Groceries"]["is_archived"] is False


async def test_membership_put_is_one_undo(db_session, api_client):
    """Two memberships and two modes in one save; one Cmd+Z puts all four back."""
    w = await _world(db_session, api_client)
    budget = w["budget"]
    ef = (await _tags(api_client, budget))["emergency_fund"]["id"]

    r = await _put(
        api_client,
        budget,
        ef,
        add=[str(w["fund"].id), str(w["general"].id)],
        savings_modes={str(w["fund"].id): "sent_out", str(w["general"].id): "kept_here"},
    )
    assert r.status_code == 200, r.text
    rows = {c["name"]: c for c in r.json()["categories"]}
    assert rows["Emergency Fund"]["member"] and rows["General Savings"]["member"]
    assert rows["Emergency Fund"]["savings_role"] == "sent_out"
    assert rows["General Savings"]["savings_mode"] == "kept_here"

    changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
    assert len({c["batch_id"] for c in changes[:4]}) == 1, "one batch"

    await _undo(api_client, budget)
    rows = await _membership(api_client, budget, ef)
    assert not rows["Emergency Fund"]["member"]
    assert not rows["General Savings"]["member"]
    assert rows["Emergency Fund"]["savings_mode"] is None
    assert rows["General Savings"]["savings_mode"] is None
    assert rows["General Savings"]["savings_role"] == "sent_out", "still tagged Savings"


async def test_membership_put_leaves_other_tags_alone(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    flexible = await create_tag(db_session, budget, name="Flexible")
    await db_session.commit()
    await api_client.put(
        f"/api/v1/{budget.id}/categories/{w['general'].id}/tags",
        json={"tag_ids": [str(flexible.id), (await _tags(api_client, budget))["savings"]["id"]]},
    )
    ef = (await _tags(api_client, budget))["emergency_fund"]["id"]

    r = await _put(api_client, budget, ef, add=[str(w["general"].id)])
    assert r.status_code == 200, r.text
    r = await _put(api_client, budget, ef, remove=[str(w["general"].id)])
    assert r.status_code == 200, r.text

    tags = await _tags(api_client, budget)
    assert tags["Flexible"]["category_count"] == 1
    assert tags["savings"]["category_count"] == 1
    assert tags["emergency_fund"]["category_count"] == 0


async def test_membership_is_idempotent_and_records_nothing_for_a_no_op(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    savings = (await _tags(api_client, budget))["savings"]["id"]
    before = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]

    r = await _put(
        api_client,
        budget,
        savings,
        add=[str(w["general"].id)],
        remove=[str(w["groceries"].id)],
        savings_modes={str(w["general"].id): None},
    )
    assert r.status_code == 200, r.text

    after = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
    assert len(after) == len(before)
    assert (await _tags(api_client, budget))["savings"]["category_count"] == 1


async def test_membership_refuses_wishlist_and_system_groups(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    tags = await _tags(api_client, budget)
    assert tags["wishlist"]["hand_settable"] is False
    assert tags["savings"]["hand_settable"] is True

    r = await _put(api_client, budget, tags["wishlist"]["id"], add=[str(w["groceries"].id)])
    assert r.status_code == 422, r.text
    assert "wishlist" in r.json()["detail"]

    r = await _put(api_client, budget, tags["savings"]["id"], add=[str(w["paycheck"].id)])
    assert r.status_code == 422, r.text
    assert (
        tags["savings"]["category_count"]
        == (await _tags(api_client, budget))["savings"]["category_count"]
    )


async def test_membership_refuses_another_budgets_category(db_session, api_client):
    w = await _world(db_session, api_client)
    other = await create_budget(db_session, api_client.test_user)
    stray = await create_category(
        db_session, other, await create_category_group(db_session, other), "Groceries"
    )
    await db_session.commit()
    savings = (await _tags(api_client, w["budget"]))["savings"]["id"]

    r = await _put(api_client, w["budget"], savings, add=[str(stray.id)])
    assert r.status_code == 422, r.text


async def test_savings_modes_only_for_what_will_be_a_savings_category(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    tags = await _tags(api_client, budget)

    # Groceries is no savings category, before or after this save.
    r = await _put(
        api_client,
        budget,
        tags["savings"]["id"],
        savings_modes={str(w["groceries"].id): "kept_here"},
    )
    assert r.status_code == 422, r.text

    # Removing General Savings' only savings tag and setting its mode together.
    r = await _put(
        api_client,
        budget,
        tags["savings"]["id"],
        remove=[str(w["general"].id)],
        savings_modes={str(w["general"].id): "kept_here"},
    )
    assert r.status_code == 422, r.text
    rows = await _membership(api_client, budget, tags["savings"]["id"])
    assert rows["General Savings"]["member"], "a refused save writes nothing"

    # Adding the tag in the same save makes the mode valid.
    r = await _put(
        api_client,
        budget,
        tags["emergency_fund"]["id"],
        add=[str(w["groceries"].id)],
        savings_modes={str(w["groceries"].id): "sent_out"},
    )
    assert r.status_code == 200, r.text
    rows = {c["name"]: c for c in r.json()["categories"]}
    assert rows["Groceries"]["savings_role"] == "sent_out"


async def test_one_id_both_added_and_removed_is_refused(db_session, api_client):
    w = await _world(db_session, api_client)
    savings = (await _tags(api_client, w["budget"]))["savings"]["id"]
    r = await _put(
        api_client, w["budget"], savings, add=[str(w["fund"].id)], remove=[str(w["fund"].id)]
    )
    assert r.status_code == 422, r.text
