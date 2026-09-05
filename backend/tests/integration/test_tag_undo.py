"""Tags and their memberships are visible to ⌘Z.

A tag delete strips its membership rows outright, so the record carries
`_category_ids`/`_payee_ids` and undo hands exactly those back — to owners
that still exist. Membership sets (one category's or payee's tag list) are
hard-replaced rows, recorded as `_tag_ids` bookkeeping on the pseudo-subjects
`category_tags`/`payee_tags`; the import review's bulk set is one batch, one
decision, one ⌘Z.
"""

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
)


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group, name="Groceries")
    payee = await create_payee(db_session, budget, name="Harborstone Market")
    await db_session.commit()
    return budget, category, payee


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _tag_names(api_client, budget):
    rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
    return [t["name"] for t in rows if t["system_key"] is None]


class TestTagUndo:
    async def test_create_undoes_away_and_redoes_back(self, db_session, api_client):
        budget, *_ = await _setup(db_session, api_client)
        r = await api_client.post(f"/api/v1/{budget.id}/tags", json={"name": "Splurge"})
        assert r.status_code == 201, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("tag", "create")
        assert await _tag_names(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert await _tag_names(api_client, budget) == ["Splurge"]

    async def test_rename_undoes_back(self, db_session, api_client):
        budget, *_ = await _setup(db_session, api_client)
        tag = (await api_client.post(f"/api/v1/{budget.id}/tags", json={"name": "Splurge"})).json()
        r = await api_client.patch(f"/api/v1/{budget.id}/tags/{tag['id']}", json={"name": "Treats"})
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("tag", "update")
        assert await _tag_names(api_client, budget) == ["Splurge"]

    async def test_delete_undo_hands_back_the_memberships_it_stripped(self, db_session, api_client):
        budget, category, payee = await _setup(db_session, api_client)
        tag = (await api_client.post(f"/api/v1/{budget.id}/tags", json={"name": "Splurge"})).json()
        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/tags", json={"tag_ids": [tag["id"]]}
        )
        assert r.status_code == 200, r.text
        r = await api_client.put(
            f"/api/v1/{budget.id}/payees/{payee.id}/tags", json={"tag_ids": [tag["id"]]}
        )
        assert r.status_code == 200, r.text

        r = await api_client.delete(f"/api/v1/{budget.id}/tags/{tag['id']}")
        assert r.status_code == 204

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("tag", "delete")
        rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        restored = next(t for t in rows if t["id"] == tag["id"])
        assert restored["category_count"] == 1
        assert restored["payee_count"] == 1

    async def test_restore_refuses_when_the_name_was_reused(self, db_session, api_client):
        budget, *_ = await _setup(db_session, api_client)
        tag = (await api_client.post(f"/api/v1/{budget.id}/tags", json={"name": "Splurge"})).json()
        await api_client.delete(f"/api/v1/{budget.id}/tags/{tag['id']}")
        r = await api_client.post(f"/api/v1/{budget.id}/tags", json={"name": "Splurge"})
        assert r.status_code == 201, r.text

        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        delete_row = next(c for c in changes if c["action"] == "delete")
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{delete_row['id']}/undo")
        assert r.status_code == 409, r.text

    async def test_setting_category_tags_undoes_back_to_the_old_set(self, db_session, api_client):
        budget, category, _ = await _setup(db_session, api_client)
        first = await create_tag(db_session, budget, name="Essential")
        second = await create_tag(db_session, budget, name="Splurge")
        await db_session.commit()
        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/tags",
            json={"tag_ids": [str(first.id)]},
        )
        assert r.status_code == 200, r.text
        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/tags",
            json={"tag_ids": [str(second.id)]},
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_tags", "update")
        rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        by_name = {t["name"]: t["category_count"] for t in rows}
        assert by_name["Essential"] == 1
        assert by_name["Splurge"] == 0

    async def test_additive_payee_tagging_undoes_only_the_addition(self, db_session, api_client):
        budget, _, payee = await _setup(db_session, api_client)
        held = await create_tag(db_session, budget, name="Grocery run")
        added = await create_tag(db_session, budget, name="Splurge")
        await db_session.commit()
        r = await api_client.put(
            f"/api/v1/{budget.id}/payees/{payee.id}/tags", json={"tag_ids": [str(held.id)]}
        )
        assert r.status_code == 200, r.text
        r = await api_client.post(
            f"/api/v1/{budget.id}/payees/{payee.id}/tags/add", json={"tag_ids": [str(added.id)]}
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("payee_tags", "update")
        rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        by_name = {t["name"]: t["payee_count"] for t in rows}
        assert by_name["Grocery run"] == 1  # the held tag survived the undo
        assert by_name["Splurge"] == 0

    async def test_bulk_review_undoes_as_one_decision(self, db_session, api_client):
        budget, category, _ = await _setup(db_session, api_client)
        group = await create_category_group(db_session, budget)
        other = await create_category(db_session, budget, group, name="Dining")
        tag = await create_tag(db_session, budget, name="Flexible")
        await db_session.commit()

        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/tags",
            json={
                "updates": [
                    {"category_id": str(category.id), "tag_ids": [str(tag.id)]},
                    {"category_id": str(other.id), "tag_ids": [str(tag.id)]},
                ]
            },
        )
        assert r.status_code == 204, r.text
        rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        assert next(t for t in rows if t["name"] == "Flexible")["category_count"] == 2

        await _undo(api_client, budget)
        rows = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        assert next(t for t in rows if t["name"] == "Flexible")["category_count"] == 0
