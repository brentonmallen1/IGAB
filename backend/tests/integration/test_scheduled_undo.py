"""Scheduled transactions are visible to ⌘Z.

Every schedule mutation records — including "enter now", which is one batch
across two services: the created transaction (source "system", it came off a
schedule) and the schedule's advanced dates (source "manual", a person
pressed the button). ⌘Z finds the manual row and takes the whole batch back;
half an inverse would leave a transaction in the register with a schedule
that claims it has not run. The nightly scheduler shares these paths with
source "system", so its writes show in Activity without entering ⌘Z.
"""

from .factories import create_account, create_budget


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()
    return budget, account


async def _add(api_client, budget, account, **body):
    body.setdefault("account_id", str(account.id))
    body.setdefault("amount", "-45")
    body.setdefault("frequency", "monthly")
    body.setdefault("start_date", "2026-10-01")
    body.setdefault("memo", "Internet bill")
    r = await api_client.post(f"/api/v1/{budget.id}/scheduled-transactions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _schedules(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/scheduled-transactions")).json()


class TestScheduledUndo:
    async def test_create_undoes_away_and_redoes_back(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        sched = await _add(api_client, budget, account)

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("scheduled_transaction", "create")
        assert await _schedules(api_client, budget) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert [s["id"] for s in await _schedules(api_client, budget)] == [sched["id"]]

    async def test_update_undoes_back(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        sched = await _add(api_client, budget, account)
        r = await api_client.patch(
            f"/api/v1/scheduled-transactions/{sched['id']}",
            json={"amount": "-60", "memo": "Internet bill (new rate)"},
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("scheduled_transaction", "update")
        [after] = await _schedules(api_client, budget)
        assert after["amount"] == -45.0
        assert after["memo"] == "Internet bill"

    async def test_delete_undo_restores_the_same_row(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        sched = await _add(api_client, budget, account)
        r = await api_client.delete(f"/api/v1/scheduled-transactions/{sched['id']}")
        assert r.status_code == 204
        assert await _schedules(api_client, budget) == []

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("scheduled_transaction", "delete")
        [restored] = await _schedules(api_client, budget)
        assert restored["id"] == sched["id"]
        assert restored["memo"] == "Internet bill"

    async def test_skip_undoes_the_date_back(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        sched = await _add(api_client, budget, account)
        r = await api_client.post(f"/api/v1/scheduled-transactions/{sched['id']}/skip")
        assert r.status_code == 200, r.text
        assert r.json()["next_occurrence_date"] == "2026-11-01"

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("scheduled_transaction", "update")
        [after] = await _schedules(api_client, budget)
        assert after["next_occurrence_date"] == "2026-10-01"

    async def test_enter_now_undoes_the_transaction_and_the_dates_as_one(
        self, db_session, api_client
    ):
        budget, account = await _setup(db_session, api_client)
        sched = await _add(api_client, budget, account)
        r = await api_client.post(
            f"/api/v1/scheduled-transactions/{sched['id']}/enter?budget_id={budget.id}"
        )
        assert r.status_code == 204, r.text
        txns = (await api_client.get(f"/api/v1/accounts/{account.id}/transactions")).json()
        assert len(txns) == 1
        [advanced] = await _schedules(api_client, budget)
        assert advanced["last_created_date"] is not None

        undone = await _undo(api_client, budget)
        # The candidate is the manual schedule row; the batch takes the
        # system-created transaction with it.
        assert (undone["entity_type"], undone["action"]) == ("scheduled_transaction", "update")
        txns = (await api_client.get(f"/api/v1/accounts/{account.id}/transactions")).json()
        assert txns == []
        [rolled_back] = await _schedules(api_client, budget)
        assert rolled_back["last_created_date"] is None
        assert rolled_back["next_occurrence_date"] == "2026-10-01"
