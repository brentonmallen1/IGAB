"""The wishlist is visible to ⌘Z.

Born from a real miss: deleting a wish recorded nothing, so undo-latest
silently reverted an older, unrelated change. The rule now (see
change_log.py's docstring): every user-visible mutation records. These walk
the whole wishlist surface through the API and the same /changes/undo
endpoint the ⌘Z key hits.
"""

from decimal import Decimal

from .factories import create_budget


async def _budget(db_session, api_client):
    return await create_budget(db_session, api_client.test_user)


def _url(budget) -> str:
    return f"/api/v1/{budget.id}/wishlist"


async def _add(api_client, budget, **body):
    body.setdefault("name", "Bike")
    body.setdefault("cost", "1800")
    body.setdefault("cooling_days", 0)
    r = await api_client.post(_url(budget), json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _items(api_client, budget):
    return (await api_client.get(_url(budget))).json()["items"]


class TestWishUndo:
    async def test_cmdz_after_a_delete_restores_that_wish_not_something_else(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget, url="https://example.com/bike", notes="red")

        r = await api_client.delete(f"{_url(budget)}/{wish['id']}")
        assert r.status_code == 200
        assert await _items(api_client, budget) == []

        undone = await _undo(api_client, budget)
        assert undone["entity_type"] == "wishlist_item"
        assert undone["action"] == "delete"

        [restored] = await _items(api_client, budget)
        assert restored["id"] == wish["id"]  # the same row, not a recreation
        assert restored["url"] == "https://example.com/bike"
        assert restored["notes"] == "red"
        assert restored["created_at"] == wish["created_at"]  # review clock intact

    async def test_create_undoes_away_and_redoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("wishlist_item", "create")
        assert await _items(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert [w["id"] for w in await _items(api_client, budget)] == [wish["id"]]

    async def test_update_undo_restores_every_edited_field(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"name": "Canoe", "cost": "950", "is_priority": True},
        )
        assert r.status_code == 200

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("wishlist_item", "update")
        [row] = await _items(api_client, budget)
        assert row["name"] == "Bike"
        assert Decimal(row["cost"]) == Decimal("1800")
        assert row["is_priority"] is False

    async def test_affirm_is_a_recorded_change(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        r = await api_client.post(f"{_url(budget)}/{wish['id']}/affirm")
        assert r.status_code == 204
        assert (await _items(api_client, budget))[0]["last_affirmed_at"] is not None

        await _undo(api_client, budget)
        assert (await _items(api_client, budget))[0]["last_affirmed_at"] is None

    async def test_reorder_undo_restores_the_queue(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        a = await _add(api_client, budget, name="A")
        b = await _add(api_client, budget, name="B")
        c = await _add(api_client, budget, name="C")

        r = await api_client.post(
            f"{_url(budget)}/reorder", json={"item_ids": [c["id"], a["id"], b["id"]]}
        )
        assert r.status_code == 204
        assert [w["name"] for w in await _items(api_client, budget)] == ["C", "A", "B"]

        undone = await _undo(api_client, budget)
        assert undone["action"] == "reorder"
        assert [w["name"] for w in await _items(api_client, budget)] == ["A", "B", "C"]

    async def test_undo_restores_a_pin_even_past_the_cap(self, db_session, api_client):
        """Fidelity over the invariant, on purpose: the cap gates the pin
        ACTION, not what undo may restore. A fourth pin coming back is the
        honest inverse of the delete; the user unpins one themselves."""
        budget = await _budget(db_session, api_client)
        pinned = await _add(api_client, budget, name="P0")
        await api_client.patch(f"{_url(budget)}/{pinned['id']}", json={"is_priority": True})
        r = await api_client.delete(f"{_url(budget)}/{pinned['id']}")
        assert r.status_code == 200
        for i in range(3):
            w = await _add(api_client, budget, name=f"W{i}")
            r = await api_client.patch(f"{_url(budget)}/{w['id']}", json={"is_priority": True})
            assert r.status_code == 200

        # Undo the delete by its own change id (newer changes exist above it).
        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()
        delete_change = next(
            c
            for c in changes["changes"]
            if c["entity_type"] == "wishlist_item" and c["action"] == "delete"
        )
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{delete_change['id']}/undo")
        assert r.status_code == 200, r.text
        items = await _items(api_client, budget)
        assert sum(1 for w in items if w["is_priority"]) == 4


class TestProjectUndo:
    async def test_project_delete_undo_restores_it_and_repoints_its_wishes(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        pr = await api_client.post(f"{_url(budget)}/projects", json={"name": "Cabin"})
        project_id = pr.json()["id"]
        w1 = await _add(api_client, budget, name="Stove", project_id=project_id)
        w2 = await _add(api_client, budget, name="Chairs", project_id=project_id)

        r = await api_client.delete(f"{_url(budget)}/projects/{project_id}")
        assert r.status_code == 204
        body = (await api_client.get(_url(budget))).json()
        assert body["projects"] == []
        assert all(w["project_id"] is None for w in body["items"])

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("wishlist_project", "delete")
        body = (await api_client.get(_url(budget))).json()
        assert [p["id"] for p in body["projects"]] == [project_id]
        assert {w["id"]: w["project_id"] for w in body["items"]} == {
            w1["id"]: project_id,
            w2["id"]: project_id,
        }

    async def test_undo_does_not_steal_a_wish_reassigned_since(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        cabin = (await api_client.post(f"{_url(budget)}/projects", json={"name": "Cabin"})).json()
        porch = (await api_client.post(f"{_url(budget)}/projects", json={"name": "Porch"})).json()
        w = await _add(api_client, budget, name="Stove", project_id=cabin["id"])

        r = await api_client.delete(f"{_url(budget)}/projects/{cabin['id']}")
        assert r.status_code == 204
        # The person re-decides before the undo: the wish joins Porch.
        r = await api_client.patch(f"{_url(budget)}/{w['id']}", json={"project_id": porch["id"]})
        assert r.status_code == 200

        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()
        delete_change = next(
            c
            for c in changes["changes"]
            if c["entity_type"] == "wishlist_project" and c["action"] == "delete"
        )
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{delete_change['id']}/undo")
        assert r.status_code == 200, r.text
        body = (await api_client.get(_url(budget))).json()
        # Cabin is back, but the wish stays where the person put it.
        assert [p["name"] for p in body["projects"]] == ["Cabin", "Porch"]
        [row] = body["items"]
        assert row["project_id"] == porch["id"]

    async def test_project_reorder_undo(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        a = (await api_client.post(f"{_url(budget)}/projects", json={"name": "A"})).json()
        b = (await api_client.post(f"{_url(budget)}/projects", json={"name": "B"})).json()
        r = await api_client.post(
            f"{_url(budget)}/projects/reorder", json={"project_ids": [b["id"], a["id"]]}
        )
        assert r.status_code == 204
        body = (await api_client.get(_url(budget))).json()
        assert [p["name"] for p in body["projects"]] == ["B", "A"]

        await _undo(api_client, budget)
        body = (await api_client.get(_url(budget))).json()
        assert [p["name"] for p in body["projects"]] == ["A", "B"]

    async def test_undoing_an_own_envelope_wish_takes_its_envelope_and_goal_too(
        self, db_session, api_client
    ):
        """A wish born with its own envelope records the category, the goal
        and the wish as one batch — one ⌘Z, three rows back. Before the
        batch, undo peeled them off one keystroke at a time and left an
        orphan envelope carrying a goal for a wish that no longer existed."""
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget, name="Kayak", funding={"mode": "own"})
        envelope_id = wish["funding"]["category_id"]
        assert envelope_id is not None

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("wishlist_item", "create")
        assert await _items(api_client, budget) == []
        cats = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert envelope_id not in [c["id"] for c in cats]
        r = await api_client.get(f"/api/v1/categories/{envelope_id}/target")
        assert r.status_code == 404  # the category 404s, so its goal does too

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [restored] = await _items(api_client, budget)
        assert restored["id"] == wish["id"]
        assert restored["funding"]["category_id"] == envelope_id
        target = (await api_client.get(f"/api/v1/categories/{envelope_id}/target")).json()
        assert target["target_amount"] == 1800.0
