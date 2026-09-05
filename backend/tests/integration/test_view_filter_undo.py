"""Budget views and filters are visible to ⌘Z.

A view's groups and placements (and a filter's category set) are
hard-replaced rows on every save, so update records carry them as canonical
bookkeeping dumps and undo rebuilds the children instead of flipping fields.
Both tables hold their names unique among LIVE rows only, so restoring a
deleted one refuses — with words, not an IntegrityError — when the name has
been reused since.
"""

from .factories import create_budget, create_category, create_category_group


async def _setup(db_session, api_client, n_categories=3):
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget)
    categories = []
    for i in range(n_categories):
        categories.append(await create_category(db_session, budget, group, name=f"Cat {i}"))
    await db_session.commit()
    return budget, categories


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _views(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/views")).json()


class TestViewUndo:
    async def test_create_undoes_away_and_redo_brings_back_its_arrangement(
        self, db_session, api_client
    ):
        budget, cats = await _setup(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/views",
            json={
                "name": "Holiday",
                "groups": ["Trips"],
                "placements": [{"category_id": str(cats[0].id), "group_name": "Trips"}],
            },
        )
        assert r.status_code == 201, r.text
        view = r.json()

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_view", "create")
        assert await _views(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [restored] = await _views(api_client, budget)
        assert restored["id"] == view["id"]
        # A soft delete left the children in place, so they came back whole.
        assert [g["name"] for g in restored["groups"]] == ["Trips"]
        assert [p["category_id"] for p in restored["placements"]] == [str(cats[0].id)]

    async def test_rearranging_undoes_back_to_the_old_arrangement(self, db_session, api_client):
        budget, cats = await _setup(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/views",
            json={
                "name": "Holiday",
                "groups": ["Trips"],
                "placements": [{"category_id": str(cats[0].id), "group_name": "Trips"}],
            },
        )
        view = r.json()
        r = await api_client.patch(
            f"/api/v1/views/{view['id']}",
            json={
                "name": "Holidays",
                "groups": ["Trips", "Gifts"],
                "placements": [
                    {"category_id": str(cats[0].id), "group_name": "Gifts"},
                    {"category_id": str(cats[1].id), "group_name": "Trips"},
                ],
            },
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_view", "update")
        [after] = await _views(api_client, budget)
        assert after["name"] == "Holiday"
        assert [g["name"] for g in after["groups"]] == ["Trips"]
        [placement] = after["placements"]
        assert placement["category_id"] == str(cats[0].id)
        trips_id = after["groups"][0]["id"]
        assert placement["group_id"] == trips_id

        # Redo replays the rearrangement.
        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [redone] = await _views(api_client, budget)
        assert redone["name"] == "Holidays"
        assert sorted(g["name"] for g in redone["groups"]) == ["Gifts", "Trips"]
        assert len(redone["placements"]) == 2

    async def test_undo_refuses_when_rearranged_since(self, db_session, api_client):
        budget, cats = await _setup(db_session, api_client)
        view = (
            await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Holiday"})
        ).json()
        for name in ("First", "Second"):
            r = await api_client.patch(f"/api/v1/views/{view['id']}", json={"groups": [name]})
            assert r.status_code == 200, r.text

        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        first_update = [
            c for c in changes if c["entity_type"] == "budget_view" and c["action"] == "update"
        ][-1]
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{first_update['id']}/undo")
        assert r.status_code == 409, r.text

    async def test_delete_undo_restores_with_children_intact(self, db_session, api_client):
        budget, cats = await _setup(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/views",
            json={
                "name": "Holiday",
                "groups": ["Trips"],
                "placements": [{"category_id": str(cats[0].id), "group_name": "Trips"}],
            },
        )
        view = r.json()
        r = await api_client.delete(f"/api/v1/views/{view['id']}")
        assert r.status_code == 204
        assert await _views(api_client, budget) == []

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_view", "delete")
        [restored] = await _views(api_client, budget)
        assert restored["id"] == view["id"]
        assert [g["name"] for g in restored["groups"]] == ["Trips"]
        assert len(restored["placements"]) == 1

    async def test_restore_refuses_when_the_name_was_reused(self, db_session, api_client):
        budget, _ = await _setup(db_session, api_client, n_categories=0)
        view = (
            await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Holiday"})
        ).json()
        r = await api_client.delete(f"/api/v1/views/{view['id']}")
        assert r.status_code == 204
        r = await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Holiday"})
        assert r.status_code == 201, r.text

        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        delete_row = next(c for c in changes if c["action"] == "delete")
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{delete_row['id']}/undo")
        assert r.status_code == 409, r.text
        assert "already exists" in r.json()["detail"]["message"]


class TestFilterUndo:
    async def test_selection_change_undoes_back(self, db_session, api_client):
        budget, cats = await _setup(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/filters",
            json={"name": "Essentials", "category_ids": [str(cats[0].id)]},
        )
        assert r.status_code == 201, r.text
        filt = r.json()
        r = await api_client.patch(
            f"/api/v1/filters/{filt['id']}",
            json={"category_ids": [str(cats[1].id), str(cats[2].id)]},
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_filter", "update")
        filters = (await api_client.get(f"/api/v1/{budget.id}/filters")).json()
        assert filters[0]["category_ids"] == [str(cats[0].id)]

    async def test_delete_undo_and_name_reuse_conflict(self, db_session, api_client):
        budget, cats = await _setup(db_session, api_client)
        filt = (
            await api_client.post(
                f"/api/v1/{budget.id}/filters",
                json={"name": "Essentials", "category_ids": [str(cats[0].id)]},
            )
        ).json()
        r = await api_client.delete(f"/api/v1/filters/{filt['id']}")
        assert r.status_code == 204

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_filter", "delete")
        [restored] = (await api_client.get(f"/api/v1/{budget.id}/filters")).json()
        assert restored["id"] == filt["id"]
        assert restored["category_ids"] == [str(cats[0].id)]

        # Delete again, reuse the name, and the restore refuses.
        await api_client.delete(f"/api/v1/filters/{filt['id']}")
        r = await api_client.post(f"/api/v1/{budget.id}/filters", json={"name": "Essentials"})
        assert r.status_code == 201, r.text
        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        delete_row = next(
            c for c in changes if c["action"] == "delete" and c["entity_type"] == "budget_filter"
        )
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{delete_row['id']}/undo")
        assert r.status_code == 409, r.text
