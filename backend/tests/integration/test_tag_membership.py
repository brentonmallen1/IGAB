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


async def test_every_row_serves_implied_by(db_session, api_client):
    """Required on the schema: a row nothing implies says so with null — a
    user's own tag (no system key) included."""
    w = await _world(db_session, api_client)
    flexible = await create_tag(db_session, w["budget"], name="Flexible")
    await db_session.commit()
    tags = await _tags(api_client, w["budget"])
    for tag_id in (tags["essential"]["id"], str(flexible.id)):
        rows = await _membership(api_client, w["budget"], tag_id)
        assert rows and all(r["implied_by"] is None for r in rows.values())


# ─── Archived categories ─────────────────────────────────────────────────────
#
# `get_taggable_with_group_names` was the one category source with no archived
# rule, so the checklist offered every envelope the household had put away.


async def _archived_world(db_session, api_client) -> dict:
    w = await _world(db_session, api_client)
    budget = w["budget"]
    later = await create_category_group(db_session, budget, "Later")
    shelved = await create_category_group(db_session, budget, "Shelved")
    shelved.is_archived = True
    w["retired"] = await create_category(db_session, budget, later, "Retired Goal")
    w["kept"] = await create_category(db_session, budget, later, "Archived Rainy Day")
    w["old_buffer"] = await create_category(db_session, budget, shelved, "Old Buffer")
    w["old_trip"] = await create_category(db_session, budget, shelved, "Old Trip Fund")
    w["retired"].is_archived = True
    w["kept"].is_archived = True
    await tag_with_system_tags(db_session, w["kept"], "savings")
    await tag_with_system_tags(db_session, w["old_trip"], "savings")
    await db_session.commit()
    return w


async def test_archived_categories_leave_the_checklist(db_session, api_client):
    w = await _archived_world(db_session, api_client)
    budget = w["budget"]
    savings = (await _tags(api_client, budget))["savings"]["id"]

    rows = await _membership(api_client, budget, savings)

    assert "Retired Goal" not in rows, "archived itself, not carrying the tag"
    assert "Old Buffer" not in rows, "live, but its group is archived"
    assert "Groceries" in rows and "Emergency Fund" in rows


async def test_an_archived_category_still_carrying_the_tag_stays_listed(db_session, api_client):
    """Its tag still moves the savings report — the money is live — so the
    checklist is where it gets taken off."""
    w = await _archived_world(db_session, api_client)
    budget = w["budget"]
    savings = (await _tags(api_client, budget))["savings"]["id"]

    rows = await _membership(api_client, budget, savings)
    assert rows["Archived Rainy Day"]["member"] is True
    assert rows["Archived Rainy Day"]["is_archived"] is True
    assert rows["Old Trip Fund"]["member"] is True, "in an archived group, and tagged"

    r = await _put(api_client, budget, savings, remove=[str(w["kept"].id), str(w["old_trip"].id)])
    assert r.status_code == 200, r.text
    after = {c["name"] for c in r.json()["categories"]}
    assert "Archived Rainy Day" not in after, "untagged, it leaves with the rest"
    assert "Old Trip Fund" not in after


async def test_a_save_cannot_tag_an_archived_category(db_session, api_client):
    w = await _archived_world(db_session, api_client)
    budget = w["budget"]
    essential = (await _tags(api_client, budget))["essential"]["id"]

    for category in (w["retired"], w["old_buffer"]):
        r = await _put(api_client, budget, essential, add=[str(category.id)])
        assert r.status_code == 422, r.text
    assert (await _tags(api_client, budget))["essential"]["category_count"] == 0


# ─── Implied tags ────────────────────────────────────────────────────────────
#
# Essential implies Cost of living and Emergency fund implies Savings
# (`domain.tag_implication`). The checklist could not see a row's other tags,
# so the Cost of living checklist drew every Essential category unticked while
# the Cost of Living report counted it.


async def _implied_world(db_session, api_client) -> dict:
    w = await _world(db_session, api_client)
    budget = w["budget"]
    w["bills"] = await create_category_group(db_session, budget, "Bills")
    for key, name in [
        ("rent", "Rent"),
        ("power", "Electricity"),
        ("gym", "Gym"),
        ("water", "Water"),
    ]:
        w[key] = await create_category(db_session, budget, w["bills"], name)
    await tag_with_system_tags(db_session, w["rent"], "essential")
    await tag_with_system_tags(db_session, w["power"], "essential")
    await tag_with_system_tags(db_session, w["gym"], "cost_of_living")
    await tag_with_system_tags(db_session, w["water"], "essential", "cost_of_living")
    await tag_with_system_tags(db_session, w["fund"], "emergency_fund")
    await db_session.commit()
    return w


def _facts(row: dict) -> tuple[bool, str | None]:
    return row["member"], row["implied_by"]


async def test_implied_rows_are_served_with_the_tag_they_count_through(db_session, api_client):
    w = await _implied_world(db_session, api_client)
    tags = await _tags(api_client, w["budget"])

    col = await _membership(api_client, w["budget"], tags["cost_of_living"]["id"])
    assert _facts(col["Rent"]) == (False, "Essential")
    assert _facts(col["Electricity"]) == (False, "Essential")
    assert _facts(col["Gym"]) == (True, None)
    # Tagged both: carries it, and is counted through Essential regardless.
    assert _facts(col["Water"]) == (True, "Essential")
    assert _facts(col["Groceries"]) == (False, None)

    savings = await _membership(api_client, w["budget"], tags["savings"]["id"])
    assert _facts(savings["Emergency Fund"]) == (False, "Emergency fund")
    assert _facts(savings["General Savings"]) == (True, None)

    # One way only: the lean tier and the fund imply nothing back.
    essential = await _membership(api_client, w["budget"], tags["essential"]["id"])
    assert _facts(essential["Gym"]) == (False, None)
    fund = await _membership(api_client, w["budget"], tags["emergency_fund"]["id"])
    assert _facts(fund["General Savings"]) == (False, None)


async def test_a_save_leaves_implied_rows_alone(db_session, api_client):
    """Adding Cost of living to an Essential category would change nothing
    but its tag list, and removing it could not take the category out."""
    w = await _implied_world(db_session, api_client)
    budget = w["budget"]
    col = (await _tags(api_client, budget))["cost_of_living"]["id"]

    before = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
    for body in (
        {"add": [str(w["rent"].id)]},
        {"remove": [str(w["water"].id)]},
        {"add": [str(w["groceries"].id), str(w["power"].id)]},
    ):
        r = await _put(api_client, budget, col, **body)
        assert r.status_code == 422, r.text
        assert "through Essential" in r.json()["detail"]
    after = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
    assert len(after) == len(before), "a refused save writes nothing"

    # A save naming only its own rows leaves the implied ones as they were.
    r = await _put(api_client, budget, col, add=[str(w["groceries"].id)], remove=[str(w["gym"].id)])
    assert r.status_code == 200, r.text
    rows = {c["name"]: c for c in r.json()["categories"]}
    assert _facts(rows["Rent"]) == (False, "Essential")
    assert _facts(rows["Water"]) == (True, "Essential")
    assert _facts(rows["Groceries"]) == (True, None)
    assert _facts(rows["Gym"]) == (False, None)


async def test_the_count_is_what_the_checklist_draws_ticked(db_session, api_client):
    """Direct plus implied, over the checklist's own rows. It counted raw
    `category_tags` rows, so a deleted or income category counted while the
    checklist drew neither, and an Essential row drawn ticked on the Cost of
    living checklist did not."""
    w = await _implied_world(db_session, api_client)
    budget = w["budget"]
    # Rows no checklist draws, each carrying Essential and Savings: a deleted
    # category and an income one.
    gone = await create_category(db_session, budget, w["bills"], "Old Rent")
    await tag_with_system_tags(db_session, gone, "essential", "savings")
    await tag_with_system_tags(db_session, w["paycheck"], "essential", "savings")
    gone.is_deleted = True
    # Archived ones carrying Essential — one itself, one by its group — which
    # Essential's checklist keeps (to be untagged) and Cost of living's does
    # not: an archived category is implied onto nothing.
    shelved = await create_category_group(db_session, budget, "Shelved")
    shelved.is_archived = True
    retired = await create_category(db_session, budget, w["bills"], "Retired Bill")
    stored = await create_category(db_session, budget, shelved, "Stored Bill")
    await tag_with_system_tags(db_session, retired, "essential")
    await tag_with_system_tags(db_session, stored, "essential")
    retired.is_archived = True
    await db_session.commit()

    tags = await _tags(api_client, budget)
    for key, expected in {
        # Gym and Water carry it; Rent and Electricity count through Essential.
        "cost_of_living": 4,
        # Rent, Electricity, Water — and Retired Bill and Stored Bill, archived
        # but carrying it.
        "essential": 5,
        # General Savings carries it; Emergency Fund counts through the fund.
        "savings": 2,
        "emergency_fund": 1,
        "subscription": 0,
    }.items():
        rows = await _membership(api_client, budget, tags[key]["id"])
        ticked = sorted(n for n, r in rows.items() if r["member"] or r["implied_by"] is not None)
        assert tags[key]["category_count"] == len(ticked) == expected, (key, ticked)
