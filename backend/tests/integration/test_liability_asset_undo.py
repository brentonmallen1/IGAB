"""Debts and assets are visible to ⌘Z.

Liabilities, their balance points, assets, and their value points all
mutated off the books before this — a deleted mortgage was gone from the
Debt page while ⌘Z reverted an older, unrelated change. Balance and value
points are hard rows (no is_deleted), and every value-point operation drags
the asset's derived (manual_value, value_as_of) pair along, so each records
as one batch: the point's move and the pair's move undo as a unit.
"""

from .factories import create_budget, create_category, create_category_group


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    return budget


async def _add_liability(api_client, budget, **body):
    body.setdefault("name", "Cedar Auto Loan")
    body.setdefault("liability_type", "auto")
    body.setdefault("manual_balance", "5200")
    body.setdefault("interest_rate", "6.5")
    body.setdefault("minimum_payment", "150")
    # Backdate the seeded balance point so a later dated point outranks it.
    body.setdefault("client_today", "2026-09-01")
    r = await api_client.post(f"/api/v1/{budget.id}/liabilities", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _add_asset(api_client, budget, **body):
    body.setdefault("name", "Cedar House")
    body.setdefault("asset_type", "property")
    r = await api_client.post(f"/api/v1/{budget.id}/assets", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _liabilities(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/liabilities")).json()


async def _assets(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/assets")).json()


class TestLiabilityUndo:
    async def test_create_undoes_away_with_its_seeded_point_and_redoes_back(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        liability = await _add_liability(api_client, budget)

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("liability", "create")
        assert await _liabilities(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [restored] = await _liabilities(api_client, budget)
        assert restored["id"] == liability["id"]
        assert restored["current_balance"] == 5200.0

    async def test_editing_terms_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        liability = await _add_liability(api_client, budget)
        r = await api_client.patch(
            f"/api/v1/{budget.id}/liabilities/{liability['id']}",
            json={"interest_rate": "7.25", "payment_due_day": 15},
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("liability", "update")
        [after] = await _liabilities(api_client, budget)
        assert after["interest_rate"] == 6.5
        assert after["payment_due_day"] is None

    async def test_delete_undo_restores_the_debt_and_its_paydown_category(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget)
        category = await create_category(db_session, budget, group, name="Loan Paydown")
        await db_session.commit()
        liability = await _add_liability(api_client, budget)
        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/link-liability",
            json={"liability_id": liability["id"]},
        )
        assert r.status_code == 200, r.text

        r = await api_client.delete(f"/api/v1/{budget.id}/liabilities/{liability['id']}")
        assert r.status_code == 204
        assert await _liabilities(api_client, budget) == []

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("liability", "delete")
        [restored] = await _liabilities(api_client, budget)
        assert restored["id"] == liability["id"]
        # The unlink was in the same batch, so the category points back too.
        assert restored["linked_category_id"] == str(category.id)

    async def test_a_balance_point_undoes_with_the_balance_it_dragged(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        liability = await _add_liability(api_client, budget)
        r = await api_client.post(
            f"/api/v1/{budget.id}/liabilities/{liability['id']}/balance-snapshots",
            json={"balance": "4900", "date": "2026-09-04"},
        )
        assert r.status_code == 201, r.text
        [current] = await _liabilities(api_client, budget)
        assert current["current_balance"] == 4900.0

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("liability_snapshot", "create")
        [after] = await _liabilities(api_client, budget)
        assert after["current_balance"] == 5200.0

    async def test_moving_the_paydown_link_undoes_both_ends(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget)
        first = await create_category(db_session, budget, group, name="Old Paydown")
        second = await create_category(db_session, budget, group, name="New Paydown")
        await db_session.commit()
        liability = await _add_liability(api_client, budget)
        for cat in (first, second):
            r = await api_client.put(
                f"/api/v1/{budget.id}/categories/{cat.id}/link-liability",
                json={"liability_id": liability["id"]},
            )
            assert r.status_code == 200, r.text
        [linked] = await _liabilities(api_client, budget)
        assert linked["linked_category_id"] == str(second.id)

        await _undo(api_client, budget)
        [after] = await _liabilities(api_client, budget)
        assert after["linked_category_id"] == str(first.id)


class TestAssetUndo:
    async def test_create_with_value_undoes_as_one_unit(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        asset = await _add_asset(api_client, budget, value="320000", value_as_of="2026-09-01")

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("asset", "create")
        assert await _assets(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [restored] = await _assets(api_client, budget)
        assert restored["id"] == asset["id"]
        assert restored["current_value"] == 320000.0
        assert restored["value_as_of"] == "2026-09-01"

    async def test_a_new_value_point_undoes_back_to_the_prior_pair(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        asset = await _add_asset(api_client, budget, value="320000", value_as_of="2026-09-01")
        r = await api_client.post(
            f"/api/v1/{budget.id}/assets/{asset['id']}/values",
            json={"value": "335000", "date": "2026-09-04"},
        )
        assert r.status_code == 201, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("asset_value", "create")
        [after] = await _assets(api_client, budget)
        assert after["current_value"] == 320000.0
        assert after["value_as_of"] == "2026-09-01"

    async def test_removing_the_newest_point_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        asset = await _add_asset(api_client, budget, value="320000", value_as_of="2026-09-01")
        r = await api_client.post(
            f"/api/v1/{budget.id}/assets/{asset['id']}/values",
            json={"value": "335000", "date": "2026-09-04"},
        )
        newest_id = r.json()["id"]
        r = await api_client.delete(f"/api/v1/{budget.id}/assets/{asset['id']}/values/{newest_id}")
        assert r.status_code == 204
        [dropped] = await _assets(api_client, budget)
        assert dropped["current_value"] == 320000.0  # fell back to the prior point

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("asset_value", "delete")
        [after] = await _assets(api_client, budget)
        assert after["current_value"] == 335000.0
        assert after["value_as_of"] == "2026-09-04"
        values = (await api_client.get(f"/api/v1/{budget.id}/assets/{asset['id']}/values")).json()
        assert newest_id in [v["id"] for v in values]  # the same row, back under its id

    async def test_deleting_an_asset_undo_relinks_the_debt_it_secured(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        asset = await _add_asset(api_client, budget, value="320000")
        liability = await _add_liability(
            api_client, budget, name="Cedar Mortgage", liability_type="mortgage"
        )
        r = await api_client.put(
            f"/api/v1/{budget.id}/liabilities/{liability['id']}/link-asset",
            json={"asset_id": asset["id"]},
        )
        assert r.status_code == 200, r.text

        r = await api_client.delete(f"/api/v1/{budget.id}/assets/{asset['id']}")
        assert r.status_code == 204
        [unlinked] = await _liabilities(api_client, budget)
        assert unlinked["linked_asset_id"] is None

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("asset", "delete")
        [restored] = await _assets(api_client, budget)
        assert restored["id"] == asset["id"]
        [relinked] = await _liabilities(api_client, budget)
        assert relinked["linked_asset_id"] == asset["id"]
