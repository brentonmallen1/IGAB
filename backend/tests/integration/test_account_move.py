"""Moving a transaction to another account: PATCH account_id.

The register could always show which account a row was in and never let you
change it. A receipt scanned against the wrong account, an import that landed
a row in the companion card, a hand-entry with the sticky account still set to
yesterday's — every one of them could only be fixed by deleting the row and
retyping it, which threw away its receipt, its AI provenance and its category.

The rules live in `domain.account_move` (refused moves) and
`domain.reconciliation` (a statement's account is locked). What is proved here
is the wiring, and the three things that must travel with the row: a split's
lines, a transfer partner's payee, and an undoable change record.

Amounts are invented; the accounts are the shared fictional vocabulary.
"""

import uuid
from datetime import date

from igab.repositories.payee_repo import PayeeRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)
from .invariants import assert_financial_invariants

TODAY = date(2026, 8, 20)


async def _budget_with_two_accounts(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await db_session.commit()
    return budget, checking, card, groceries


async def _move(api_client, budget, txn_id, account_id):
    return await api_client.patch(
        f"/api/v1/transactions/{txn_id}",
        json={"account_id": str(account_id)},
        params={"budget_id": str(budget.id)},
    )


async def _row(api_client, budget, txn_id):
    r = await api_client.get(f"/api/v1/transactions/{txn_id}")
    assert r.status_code == 200, r.text
    return r.json()


class TestMovingAnOrdinaryRow:
    async def test_the_row_changes_account_and_keeps_everything_else(self, db_session, api_client):
        """The user's report: a receipt scan landed on the card instead of
        checking. The fix must keep the category and the memo — that is the
        whole reason this is an edit and not a delete-and-retype."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(
            db_session,
            budget,
            card,
            "-41.80",
            TODAY,
            category=groceries,
            memo="scanned receipt",
            created_via="ai_receipt",
        )
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, checking.id)
        assert resp.status_code == 200, resp.text

        moved = await _row(api_client, budget, txn.id)
        assert moved["account_id"] == str(checking.id)
        assert moved["category_id"] == str(groceries.id)
        assert moved["memo"] == "scanned receipt"
        assert moved["created_via"] == "ai_receipt"
        await assert_financial_invariants(db_session, budget.id)

    async def test_the_money_leaves_one_register_and_arrives_in_the_other(
        self, db_session, api_client
    ):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(db_session, budget, card, "-41.80", TODAY)
        await db_session.commit()

        await _move(api_client, budget, txn.id, checking.id)

        card_rows = (await api_client.get(f"/api/v1/accounts/{card.id}/transactions")).json()
        checking_rows = (
            await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")
        ).json()
        assert [r["id"] for r in card_rows] == []
        assert [r["id"] for r in checking_rows] == [str(txn.id)]

    async def test_an_unchanged_account_is_not_a_move(self, db_session, api_client):
        """The editor PATCHes every field it shows. A row that stayed put must
        not be judged as a move — otherwise every memo edit on a bank-fed row
        would be refused."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(
            db_session, budget, card, "-41.80", TODAY, sync_id="feed-1", sync_source="simplefin"
        )
        await db_session.commit()

        resp = await api_client.patch(
            f"/api/v1/transactions/{txn.id}",
            json={"account_id": str(card.id), "memo": "still the same account"},
            params={"budget_id": str(budget.id)},
        )
        assert resp.status_code == 200, resp.text
        assert (await _row(api_client, budget, txn.id))["memo"] == "still the same account"


class TestRefusedMoves:
    async def test_a_bank_fed_row_may_not_move(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(
            db_session, budget, card, "-41.80", TODAY, sync_id="feed-1", sync_source="simplefin"
        )
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, checking.id)
        assert resp.status_code == 400
        assert "bank feed" in resp.json()["detail"]

    async def test_a_reconciled_row_may_not_move(self, db_session, api_client):
        """The statement vouched for a balance in one account."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(
            db_session, budget, card, "-41.80", TODAY, cleared="reconciled"
        )
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, checking.id)
        assert resp.status_code == 400
        assert "reconciled" in resp.json()["detail"]

    async def test_a_categorized_row_may_not_move_to_a_tracking_account(
        self, db_session, api_client
    ):
        """The category rule judges where the edit LANDS. Nothing about the
        category changed here — the account moved out from under it."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        brokerage = await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        )
        txn = await create_transaction(
            db_session, budget, checking, "-41.80", TODAY, category=groceries
        )
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, brokerage.id)
        assert resp.status_code == 400
        assert "tracking account" in resp.json()["detail"]

    async def test_dropping_the_category_in_the_same_edit_lets_it_move(
        self, db_session, api_client
    ):
        """What the editor does: a tracking account cannot hold a category, so
        it clears the field and the save goes through in one request."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        brokerage = await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        )
        txn = await create_transaction(
            db_session, budget, checking, "-41.80", TODAY, category=groceries
        )
        await db_session.commit()

        resp = await api_client.patch(
            f"/api/v1/transactions/{txn.id}",
            json={"account_id": str(brokerage.id), "category_id": None},
            params={"budget_id": str(budget.id)},
        )
        assert resp.status_code == 200, resp.text
        moved = await _row(api_client, budget, txn.id)
        assert moved["account_id"] == str(brokerage.id)
        assert moved["category_id"] is None

    async def test_a_split_line_may_not_move_on_its_own(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        parent = await create_transaction(db_session, budget, card, "-100.00", TODAY, is_split=True)
        line = await create_transaction(
            db_session,
            budget,
            card,
            "-100.00",
            TODAY,
            category=groceries,
            parent_transaction_id=parent.id,
        )
        await db_session.commit()

        resp = await _move(api_client, budget, line.id, checking.id)
        assert resp.status_code == 400
        assert "parent" in resp.json()["detail"]

    async def test_a_closed_account_is_not_a_destination(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        card.is_closed = True
        txn = await create_transaction(db_session, budget, checking, "-41.80", TODAY)
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, card.id)
        assert resp.status_code == 400
        assert "closed" in resp.json()["detail"]

    async def test_another_budgets_account_is_not_a_destination(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        other_budget = await create_budget(db_session, api_client.test_user)
        stranger = await create_account(db_session, other_budget, "Someone Else's Checking")
        txn = await create_transaction(db_session, budget, checking, "-41.80", TODAY)
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, stranger.id)
        assert resp.status_code == 400

    async def test_a_null_account_is_refused_rather_than_read_as_clear_it(
        self, db_session, api_client
    ):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(db_session, budget, checking, "-41.80", TODAY)
        await db_session.commit()

        resp = await api_client.patch(
            f"/api/v1/transactions/{txn.id}",
            json={"account_id": None},
            params={"budget_id": str(budget.id)},
        )
        assert resp.status_code == 400


class TestWhatTravelsWithTheRow:
    async def test_a_splits_lines_move_with_their_parent(self, db_session, api_client):
        """Lines carry the parent's account: the balance is summed from parent
        rows and the category activity from lines, so lines left behind would
        put one movement in two accounts."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        parent = await create_transaction(db_session, budget, card, "-100.00", TODAY, is_split=True)
        line = await create_transaction(
            db_session,
            budget,
            card,
            "-100.00",
            TODAY,
            category=groceries,
            parent_transaction_id=parent.id,
        )
        await db_session.commit()

        resp = await _move(api_client, budget, parent.id, checking.id)
        assert resp.status_code == 200, resp.text

        lines = (await api_client.get(f"/api/v1/transactions/{parent.id}/splits")).json()
        assert [line_row["account_id"] for line_row in lines] == [str(checking.id)]
        assert str(line.id) in [line_row["id"] for line_row in lines]
        await assert_financial_invariants(db_session, budget.id)

    async def test_moving_one_leg_renames_the_other_legs_payee(self, db_session, api_client):
        """A transfer leg's payee IS the other account. Move the near leg and
        the far leg's payee has to follow, or the pair says the money went
        somewhere it did not."""
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        savings = await create_account(db_session, budget, "Cascade Point HYSA")
        payee_repo = PayeeRepository(db_session)
        to_savings = await payee_repo.find_or_create_transfer(budget.id, savings.id, savings.name)
        to_checking = await payee_repo.find_or_create_transfer(
            budget.id, checking.id, checking.name
        )
        out_leg = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        in_leg = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking, transfer_id=out_leg.id
        )
        out_leg.transfer_id = in_leg.id
        await db_session.commit()

        # The outflow was actually paid from the card, not checking.
        resp = await _move(api_client, budget, out_leg.id, card.id)
        assert resp.status_code == 200, resp.text

        far = await _row(api_client, budget, in_leg.id)
        payees = (await api_client.get(f"/api/v1/{budget.id}/payees")).json()
        by_id = {p["id"]: p for p in payees}
        assert by_id[far["payee_id"]]["transfer_account_id"] == str(card.id)
        # The near leg still names its own destination, which did not move.
        near = await _row(api_client, budget, out_leg.id)
        assert by_id[near["payee_id"]]["transfer_account_id"] == str(savings.id)
        await assert_financial_invariants(db_session, budget.id)

    async def test_a_leg_may_not_move_into_its_own_counterpart(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        savings = await create_account(db_session, budget, "Cascade Point HYSA")
        payee_repo = PayeeRepository(db_session)
        to_savings = await payee_repo.find_or_create_transfer(budget.id, savings.id, savings.name)
        to_checking = await payee_repo.find_or_create_transfer(
            budget.id, checking.id, checking.name
        )
        out_leg = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        in_leg = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking, transfer_id=out_leg.id
        )
        out_leg.transfer_id = in_leg.id
        await db_session.commit()

        resp = await _move(api_client, budget, out_leg.id, savings.id)
        assert resp.status_code == 400
        assert "both sides" in resp.json()["detail"]

    async def test_moving_and_retargeting_in_one_request_is_refused(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        savings = await create_account(db_session, budget, "Cascade Point HYSA")
        txn = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        await db_session.commit()

        resp = await api_client.patch(
            f"/api/v1/transactions/{txn.id}",
            json={"account_id": str(card.id), "transfer_account_id": str(savings.id)},
            params={"budget_id": str(budget.id)},
        )
        assert resp.status_code == 400
        assert "separate edits" in resp.json()["detail"]


class TestUndo:
    async def test_a_move_undoes_back_to_the_original_account(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(db_session, budget, card, "-41.80", TODAY)
        await db_session.commit()

        await _move(api_client, budget, txn.id, checking.id)
        undone = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert undone.status_code == 200, undone.text

        assert (await _row(api_client, budget, txn.id))["account_id"] == str(card.id)
        await assert_financial_invariants(db_session, budget.id)

    async def test_undoing_a_split_move_brings_the_lines_back_too(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        parent = await create_transaction(db_session, budget, card, "-100.00", TODAY, is_split=True)
        await create_transaction(
            db_session,
            budget,
            card,
            "-100.00",
            TODAY,
            category=groceries,
            parent_transaction_id=parent.id,
        )
        await db_session.commit()

        await _move(api_client, budget, parent.id, checking.id)
        assert (await api_client.post(f"/api/v1/{budget.id}/changes/undo")).status_code == 200

        lines = (await api_client.get(f"/api/v1/transactions/{parent.id}/splits")).json()
        assert {line["account_id"] for line in lines} == {str(card.id)}
        assert (await _row(api_client, budget, parent.id))["account_id"] == str(card.id)


class TestUnrelatedIds:
    async def test_a_missing_account_is_a_clean_refusal(self, db_session, api_client):
        budget, checking, card, groceries = await _budget_with_two_accounts(db_session, api_client)
        txn = await create_transaction(db_session, budget, checking, "-41.80", TODAY)
        await db_session.commit()

        resp = await _move(api_client, budget, txn.id, uuid.uuid4())
        assert resp.status_code == 400
