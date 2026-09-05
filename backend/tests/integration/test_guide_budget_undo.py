"""Guide state, budget settings and membership are visible to ⌘Z.

Guide preferences, progress steps and wishlist settings share one KV store,
so they share one recorded spelling (`guide_state`, `_key`/`_value`
bookkeeping, `_value` None meaning the row was absent). Concept answers are
hard-replaced binding rows recorded as canonical `_rows` dumps. The checkup's
last-run stamp deliberately does NOT record: it is the timestamp of the run
itself, and undoing it would falsify history. Budget creates/deletes are the
other named exclusion — this log lives inside the budget.
"""

from .factories import create_budget, create_user


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    return budget


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


class TestGuideStateUndo:
    async def test_flipping_a_preference_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"checkup": False})
        assert r.status_code == 200, r.text
        assert r.json()["checkup"] is False

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("guide_state", "update")
        prefs = (await api_client.get(f"/api/v1/{budget.id}/guide/preferences")).json()
        assert prefs["checkup"] is True

    async def test_a_progress_step_undoes_to_undecided(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/progress/starter-fund", json={"state": "done"}
        )
        assert r.status_code == 204, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("guide_state", "update")
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/progress/starter-fund", json={"state": "done"}
        )
        assert r.status_code == 204  # settable again — the row really cleared

    async def test_wishlist_settings_undo_back_to_defaults(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(f"/api/v1/{budget.id}/wishlist/settings", json={"cooling_days": 9})
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("guide_state", "update")
        overview = (await api_client.get(f"/api/v1/{budget.id}/wishlist")).json()
        assert overview["settings"]["cooling_days"] != 9


class TestGuideBindingUndo:
    async def test_dismissing_a_concept_undoes_back_to_auto(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/employer_match",
            json={"mode": "dismissed", "note": "no employer plan"},
        )
        assert r.status_code == 204, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("guide_binding", "update")
        signals = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
        match = next(c for c in signals["concepts"] if c["key"] == "employer_match")
        assert match["tracked"] is True  # no longer dismissed

    async def test_changing_an_answer_undoes_to_the_previous_one(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        for answer in (True, False):
            r = await api_client.put(
                f"/api/v1/{budget.id}/guide/bindings/hsa",
                json={"mode": "answer", "answer": answer},
            )
            assert r.status_code == 204, r.text

        signals = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
        hsa = next(c for c in signals["concepts"] if c["key"] == "hsa")
        assert hsa["met"] is False

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("guide_binding", "update")
        signals = (await api_client.get(f"/api/v1/{budget.id}/guide/signals")).json()
        hsa = next(c for c in signals["concepts"] if c["key"] == "hsa")
        assert hsa["met"] is True  # the previous answer, back


class TestBudgetUndo:
    async def test_renaming_the_budget_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.patch(f"/api/v1/budgets/{budget.id}", json={"name": "Twenty-Seven"})
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget", "update")
        r = await api_client.get(f"/api/v1/budgets/{budget.id}")
        assert r.json()["name"] == budget.name


class TestMemberUndo:
    async def test_adding_a_member_undoes_away_and_removal_undoes_back(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        partner = await create_user(db_session)
        await db_session.commit()

        r = await api_client.post(f"/api/v1/{budget.id}/members", json={"user_id": str(partner.id)})
        assert r.status_code == 201, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_member", "create")
        members = (await api_client.get(f"/api/v1/{budget.id}/members")).json()
        assert str(partner.id) not in [m["user_id"] for m in members]

        # Add again, remove, and undo the removal: they come back as member.
        r = await api_client.post(f"/api/v1/{budget.id}/members", json={"user_id": str(partner.id)})
        assert r.status_code == 201, r.text
        r = await api_client.delete(f"/api/v1/{budget.id}/members/{partner.id}")
        assert r.status_code == 204, r.text
        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("budget_member", "delete")
        members = (await api_client.get(f"/api/v1/{budget.id}/members")).json()
        restored = next(m for m in members if m["user_id"] == str(partner.id))
        assert restored["role"] == "member"
