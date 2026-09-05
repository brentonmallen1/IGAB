"""Accounts and account types are visible to ⌘Z.

Deleting an account was the single largest gap in the change log: one
DELETE soft-deleted the whole ledger, unlinked the payment category, and
converted the companion liability — all invisibly, so ⌘Z reverted something
older while the register sat empty. It records as one batch now:
`_transaction_ids` names every row the delete took, the category unlinks
and the companion's conversion are batch siblings, and
`_backfill_snapshot_ids` names the balance-history points the conversion
reconstructed (the undo removes them again — the re-linked companion reads
the restored ledger).
"""

import uuid
from datetime import date

from igab.db.models import Account

from .factories import create_account, create_budget, create_transaction


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    return budget


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _accounts(api_client, budget):
    return (await api_client.get(f"/api/v1/{budget.id}/accounts")).json()


class TestAccountUndo:
    async def test_creating_a_card_undoes_with_its_companion_and_envelope(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Sapphire Visa", "account_type": "credit_card"},
        )
        assert r.status_code == 201, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account", "create")
        assert await _accounts(api_client, budget) == []
        assert (await api_client.get(f"/api/v1/{budget.id}/liabilities")).json() == []
        cats = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert "Sapphire Visa" not in [c["name"] for c in cats]

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [restored] = await _accounts(api_client, budget)
        assert restored["name"] == "Sapphire Visa"
        assert len((await api_client.get(f"/api/v1/{budget.id}/liabilities")).json()) == 1

    async def test_renaming_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, name="Harborstone Checking")
        await db_session.commit()
        r = await api_client.patch(
            f"/api/v1/accounts/{account.id}", json={"name": "Everyday Checking"}
        )
        assert r.status_code == 200, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account", "update")
        [after] = await _accounts(api_client, budget)
        assert after["name"] == "Harborstone Checking"

    async def test_deleting_an_account_undo_restores_its_whole_ledger(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, name="Harborstone Checking")
        for i, amount in enumerate(("-42.50", "-18", "1200")):
            await create_transaction(db_session, budget, account, amount, date(2026, 8, i + 1))
        await db_session.commit()

        r = await api_client.delete(f"/api/v1/accounts/{account.id}")
        assert r.status_code == 204
        assert await _accounts(api_client, budget) == []

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account", "delete")
        [restored] = await _accounts(api_client, budget)
        assert restored["id"] == str(account.id)
        assert restored["balance"] == 1139.5  # all three rows came back

        # Redo takes the ledger down again.
        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert await _accounts(api_client, budget) == []
        txns = (await api_client.get(f"/api/v1/accounts/{account.id}/transactions")).json()
        assert txns == []

    async def test_deleting_a_card_with_kept_debt_undoes_the_conversion_too(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Sapphire Visa", "account_type": "credit_card"},
        )
        card = r.json()
        card_row = await db_session.get(Account, uuid.UUID(card["id"]))
        await create_transaction(db_session, budget, card_row, "-260", date(2026, 8, 15))
        await db_session.commit()

        r = await api_client.delete(f"/api/v1/accounts/{card['id']}?liability=keep")
        assert r.status_code == 204
        [kept] = (await api_client.get(f"/api/v1/{budget.id}/liabilities")).json()
        assert kept["mode"] == "unmanaged"
        assert kept["current_balance"] == 260.0  # frozen from the ledger

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account", "delete")
        [managed] = (await api_client.get(f"/api/v1/{budget.id}/liabilities")).json()
        assert managed["mode"] == "managed"
        assert managed["linked_account_id"] == card["id"]
        assert managed["current_balance"] == 260.0  # from the restored ledger


class TestAccountTypeUndo:
    async def test_create_undoes_away_and_redoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/account-types",
            json={"label": "Escrow", "classification": "asset"},
        )
        assert r.status_code == 201, r.text
        created = r.json()

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account_type", "create")
        rows = (await api_client.get(f"/api/v1/{budget.id}/account-types")).json()
        assert created["id"] not in [t["id"] for t in rows]

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        rows = (await api_client.get(f"/api/v1/{budget.id}/account-types")).json()
        assert created["id"] in [t["id"] for t in rows]

    async def test_reclassifying_undoes_the_account_mirrors_too(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        custom = (
            await api_client.post(
                f"/api/v1/{budget.id}/account-types",
                json={"label": "Escrow", "classification": "asset"},
            )
        ).json()
        account = await create_account(db_session, budget, name="Escrow Holding")
        await db_session.commit()
        r = await api_client.patch(
            f"/api/v1/accounts/{account.id}", json={"account_type": custom["key"]}
        )
        assert r.status_code == 200, r.text

        r = await api_client.patch(
            f"/api/v1/{budget.id}/account-types/{custom['id']}",
            json={"classification": "liability"},
        )
        assert r.status_code == 200, r.text
        [mirrored] = await _accounts(api_client, budget)
        assert mirrored["classification"] == "liability"

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account_type", "update")
        [after] = await _accounts(api_client, budget)
        assert after["classification"] == "asset"

    async def test_delete_undo_reinserts_the_type(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        custom = (
            await api_client.post(
                f"/api/v1/{budget.id}/account-types",
                json={"label": "Escrow", "classification": "asset"},
            )
        ).json()
        r = await api_client.delete(f"/api/v1/{budget.id}/account-types/{custom['id']}")
        assert r.status_code == 204

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account_type", "delete")
        rows = (await api_client.get(f"/api/v1/{budget.id}/account-types")).json()
        restored = next(t for t in rows if t["id"] == custom["id"])
        assert restored["label"] == "Escrow"


class TestSimpleFINLinkUndo:
    async def test_linking_an_account_undoes_back(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget)
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/accounts/{account.id}/link-simplefin",
            json={"simplefin_account_id": "ACT-123", "simplefin_account_name": "CHK ...4821"},
        )
        assert r.status_code == 204, r.text

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("account", "update")
        [after] = await _accounts(api_client, budget)
        assert after["simplefin_account_id"] is None
