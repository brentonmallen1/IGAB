"""Category targets are visible to ⌘Z.

Targets were the highest-value hard-delete gap in the change log: a goal is a
money rule (Fill Underfunded moves what it says), yet setting or clearing one
recorded nothing, so undo-latest silently reverted something older instead.
`category_targets` has no is_deleted column, so this is also the proving
ground for the hard-row inverse: undo of a delete re-inserts the recorded row
under its original id, and refuses when a newer target has taken the slot.
"""

from .factories import create_budget, create_category, create_category_group


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group, name="New Roof")
    await db_session.commit()
    return budget, category


def _target_url(category) -> str:
    return f"/api/v1/categories/{category.id}/target"


async def _set_target(api_client, category, **body):
    body.setdefault("target_type", "savings_balance")
    body.setdefault("target_amount", "1200")
    r = await api_client.post(_target_url(category), json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _read_target(api_client, category):
    r = await api_client.get(_target_url(category))
    assert r.status_code == 200, r.text
    return r.json()


class TestTargetUndo:
    async def test_setting_a_goal_records_and_cmdz_removes_it(self, db_session, api_client):
        budget, category = await _setup(db_session, api_client)
        await _set_target(api_client, category)

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_target", "create")
        assert await _read_target(api_client, category) is None

    async def test_redo_puts_the_goal_back_under_its_original_id(self, db_session, api_client):
        budget, category = await _setup(db_session, api_client)
        target = await _set_target(api_client, category)
        await _undo(api_client, budget)

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        restored = await _read_target(api_client, category)
        assert restored["id"] == target["id"]
        assert restored["target_amount"] == 1200.0

    async def test_editing_a_goal_undoes_back_to_the_old_figure(self, db_session, api_client):
        budget, category = await _setup(db_session, api_client)
        target = await _set_target(api_client, category, target_amount="1200")
        await _set_target(api_client, category, target_amount="2500")

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_target", "update")
        after = await _read_target(api_client, category)
        assert after["id"] == target["id"]  # same row, not a recreation
        assert after["target_amount"] == 1200.0

    async def test_deleting_a_goal_undo_reinserts_the_same_row(self, db_session, api_client):
        budget, category = await _setup(db_session, api_client)
        target = await _set_target(
            api_client, category, target_amount="1200", target_date="2027-06-01"
        )

        r = await api_client.delete(_target_url(category))
        assert r.status_code == 204
        assert await _read_target(api_client, category) is None

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("category_target", "delete")
        restored = await _read_target(api_client, category)
        assert restored["id"] == target["id"]
        assert restored["target_amount"] == 1200.0
        assert restored["target_date"] == "2027-06-01"

    async def test_redo_of_a_delete_removes_it_again(self, db_session, api_client):
        budget, category = await _setup(db_session, api_client)
        await _set_target(api_client, category)
        await api_client.delete(_target_url(category))
        await _undo(api_client, budget)

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert await _read_target(api_client, category) is None

    async def test_undo_refuses_when_a_newer_goal_took_the_slot(self, db_session, api_client):
        """A new target set after the delete is a person's later decision;
        undo of the old delete must refuse, never overwrite it."""
        budget, category = await _setup(db_session, api_client)
        await _set_target(api_client, category, target_amount="1200")
        await api_client.delete(_target_url(category))
        replacement = await _set_target(api_client, category, target_amount="9000")

        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        delete_row = next(c for c in changes if c["action"] == "delete")
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{delete_row['id']}/undo")
        assert r.status_code == 409, r.text

        kept = await _read_target(api_client, category)
        assert kept["id"] == replacement["id"]
        assert kept["target_amount"] == 9000.0

    async def test_a_noop_upsert_records_nothing(self, db_session, api_client):
        budget, category = await _setup(db_session, api_client)
        await _set_target(api_client, category, target_amount="1200")
        await _set_target(api_client, category, target_amount="1200")

        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        target_rows = [c for c in changes if c["entity_type"] == "category_target"]
        assert len(target_rows) == 1
