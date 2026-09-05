"""Reconciliation and duplicate-match decisions are visible to ⌘Z.

Finishing a reconciliation retroactively LOCKS rows against undo, so being
invisible in Activity meant the user met "reconciled transactions cannot be
removed" with no entry explaining when the lock happened — and no way back.
It records now as one batch (the lock, the account's stamp, the adjustment
transaction), and undoing it is the unreconcile that never existed:
`_transaction_ids` names exactly the rows the finish locked, so nothing
reconciled earlier flips with them.
"""

import uuid
from datetime import date
from decimal import Decimal

from igab.db.models import TransactionMatch

from .factories import create_account, create_budget, create_transaction


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    await db_session.commit()
    return budget, account


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _rows(api_client, account):
    return (await api_client.get(f"/api/v1/accounts/{account.id}/transactions")).json()


class TestReconcileUndo:
    async def test_undo_unlocks_exactly_what_the_finish_locked(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        # One row locked by an earlier reconciliation, one cleared since.
        await create_transaction(
            db_session, budget, account, "-40", date(2026, 8, 1), cleared="reconciled"
        )
        await create_transaction(
            db_session, budget, account, "-25", date(2026, 8, 20), cleared="cleared"
        )
        await db_session.commit()

        r = await api_client.post(
            f"/api/v1/accounts/{account.id}/reconcile/finish",
            json={"statement_balance": "-65"},
        )
        assert r.status_code == 200, r.text
        assert [t["cleared"] for t in await _rows(api_client, account)] == [
            "reconciled",
            "reconciled",
        ]

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("reconciliation", "create")
        by_date = {t["date"]: t["cleared"] for t in await _rows(api_client, account)}
        # The newly locked row unlocked; the OLD reconciliation's row did not.
        assert by_date["2026-08-20"] == "cleared"
        assert by_date["2026-08-01"] == "reconciled"
        history = (await api_client.get(f"/api/v1/accounts/{account.id}/reconcile/history")).json()
        assert history == []

    async def test_undo_takes_the_adjustment_with_it_and_redo_relocks(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        await create_transaction(
            db_session, budget, account, "-100", date(2026, 8, 10), cleared="cleared"
        )
        await db_session.commit()

        # Statement disagrees by $12.50 → an adjustment is created and locked.
        r = await api_client.post(
            f"/api/v1/accounts/{account.id}/reconcile/finish",
            json={"statement_balance": "-112.50"},
        )
        assert r.status_code == 200, r.text
        rows = await _rows(api_client, account)
        assert len(rows) == 2
        assert all(t["cleared"] == "reconciled" for t in rows)

        await _undo(api_client, budget)
        rows = await _rows(api_client, account)
        assert len(rows) == 1  # the adjustment went with the batch
        assert rows[0]["cleared"] == "cleared"

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        rows = await _rows(api_client, account)
        assert len(rows) == 2
        assert all(t["cleared"] == "reconciled" for t in rows)
        history = (await api_client.get(f"/api/v1/accounts/{account.id}/reconcile/history")).json()
        assert len(history) == 1


class TestMatchDecisionUndo:
    async def _make_pair(self, db_session, budget, account):
        synced = await create_transaction(
            db_session, budget, account, "-30", date(2026, 8, 12), sync_id="S-1"
        )
        manual = await create_transaction(db_session, budget, account, "-30", date(2026, 8, 11))
        match = TransactionMatch(
            id=uuid.uuid4(),
            synced_transaction_id=synced.id,
            manual_transaction_id=manual.id,
            confidence_score=Decimal("0.9"),
            status="pending",
        )
        db_session.add(match)
        await db_session.commit()
        return synced, manual, match

    async def test_rejecting_a_match_undoes_back_to_pending(self, db_session, api_client):
        budget, account = await _setup(db_session, api_client)
        _, _, match = await self._make_pair(db_session, budget, account)

        r = await api_client.post(f"/api/v1/simplefin/matches/{match.id}/reject")
        assert r.status_code in (200, 204), r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("transaction_match", "update")
        pending = (await api_client.get(f"/api/v1/simplefin/matches?budget_id={budget.id}")).json()
        assert str(match.id) in [m["id"] for m in pending]

    async def test_accepting_a_match_undoes_the_merge_and_the_decision(
        self, db_session, api_client
    ):
        budget, account = await _setup(db_session, api_client)
        synced, manual, match = await self._make_pair(db_session, budget, account)

        r = await api_client.post(f"/api/v1/simplefin/matches/{match.id}/accept")
        assert r.status_code in (200, 204), r.text
        rows = await _rows(api_client, account)
        assert len(rows) == 1  # merged

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("transaction_match", "update")
        rows = await _rows(api_client, account)
        assert len(rows) == 2  # both halves back
        pending = (await api_client.get(f"/api/v1/simplefin/matches?budget_id={budget.id}")).json()
        assert str(match.id) in [m["id"] for m in pending]
