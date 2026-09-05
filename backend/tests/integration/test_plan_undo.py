"""Category plans are visible to ⌘Z.

Plans are hard rows (scratchpads, no is_deleted), so they ride the hard-row
inverse keyed (budget, name). The one that mattered most: apply-targets
creates categories, a Planned group and goals — covered entities every OTHER
route records — through repositories that bypassed the log entirely, so the
Activity feed showed category creates from everywhere except the planner.
Apply is one batch now, and one ⌘Z takes the whole application back.
"""

from .factories import create_budget


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    return budget


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _plans(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/category-plans")).json()


def _payload_with(*items):
    return {
        "cadence": "biweekly",
        "paycheck_count_override": None,
        "paychecks": [
            {
                "id": "00000000-0000-0000-0000-0000000000aa",
                "income_override_cents": None,
                "items": list(items),
            }
        ],
    }


class TestPlanUndo:
    async def test_create_undoes_away_and_redoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(f"/api/v1/{budget.id}/category-plans", json={"name": "Autumn"})
        assert r.status_code == 201, r.text
        plan = r.json()

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_plan", "create")
        assert await _plans(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert [p["id"] for p in await _plans(api_client, budget)] == [plan["id"]]

    async def test_rename_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = (
            await api_client.post(f"/api/v1/{budget.id}/category-plans", json={"name": "Autumn"})
        ).json()
        r = await api_client.patch(
            f"/api/v1/{budget.id}/category-plans/{plan['id']}", json={"name": "Winter"}
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_plan", "update")
        [after] = await _plans(api_client, budget)
        assert after["name"] == "Autumn"

    async def test_delete_undo_reinserts_the_same_document(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = (
            await api_client.post(f"/api/v1/{budget.id}/category-plans", json={"name": "Autumn"})
        ).json()
        r = await api_client.delete(f"/api/v1/{budget.id}/category-plans/{plan['id']}")
        assert r.status_code == 204
        assert await _plans(api_client, budget) == []

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_plan", "delete")
        r = await api_client.get(f"/api/v1/{budget.id}/category-plans/{plan['id']}")
        assert r.status_code == 200, r.text
        assert r.json()["payload"] == plan["payload"]  # the same document, back whole

    async def test_apply_targets_undoes_as_one_unit(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = (
            await api_client.post(
                f"/api/v1/{budget.id}/category-plans",
                json={
                    "name": "Autumn",
                    "payload": _payload_with(
                        {
                            "id": "00000000-0000-0000-0000-0000000000b1",
                            "name": "Firewood",
                            "amount_cents": 12000,
                            "category_id": None,
                        }
                    ),
                },
            )
        ).json()

        r = await api_client.post(f"/api/v1/{budget.id}/category-plans/{plan['id']}/apply-targets")
        assert r.status_code == 200, r.text
        cats = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        firewood = next(c for c in cats if c["name"] == "Firewood")
        target = (await api_client.get(f"/api/v1/categories/{firewood['id']}/target")).json()
        assert target["target_amount"] == 120.0

        await _undo(api_client, budget)
        cats = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert "Firewood" not in [c["name"] for c in cats]
        groups = (await api_client.get(f"/api/v1/{budget.id}/category-groups")).json()
        assert "Planned" not in [g["name"] for g in groups]
        # The plan's link-back went with the batch: the item is unlinked again.
        after = (await api_client.get(f"/api/v1/{budget.id}/category-plans/{plan['id']}")).json()
        assert after["payload"]["paychecks"][0]["items"][0]["category_id"] is None
