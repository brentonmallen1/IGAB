"""A PATCH says whether it wrote anything (`changed`).

The "Payee Not Sent" report: a card payment recorded from the wrong account,
fixed by picking "Transfer : Harborstone Checking" in the editor's payee box.
The editor built the body from its account control instead, so the request
named the account the payment already pointed at. The server planned
`none`, wrote nothing and answered 200 — correct for the request it got —
and the dialog closed as if the edit had been kept. Twice; the payment was
deleted and re-entered, losing its undo history.

The editor bug is fixed in the editor. What is pinned here is the server's
half: a 200 that changed nothing must say so, so no editor can again present
a dropped edit as a kept one.
"""

from datetime import date

from .factories import create_account, create_budget, create_transaction

TODAY = date(2026, 10, 22)


async def _card_payment(api_client, db_session):
    """Sapphire Visa paid $400 from Cascade Point HYSA by mistake."""
    from igab.repositories.payee_repo import PayeeRepository

    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    hysa = await create_account(db_session, budget, "Cascade Point HYSA")
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    payees = PayeeRepository(db_session)
    to_card = await payees.find_or_create_transfer(budget.id, card.id, card.name)
    to_hysa = await payees.find_or_create_transfer(budget.id, hysa.id, hysa.name)
    out_leg = await create_transaction(db_session, budget, hysa, "-400.00", TODAY, payee=to_card)
    in_leg = await create_transaction(
        db_session, budget, card, "400.00", TODAY, payee=to_hysa, transfer_id=out_leg.id
    )
    out_leg.transfer_id = in_leg.id
    await db_session.commit()
    return budget, checking, hysa, card, in_leg


async def _patch(api_client, budget, txn_id, body):
    r = await api_client.patch(
        f"/api/v1/transactions/{txn_id}", params={"budget_id": str(budget.id)}, json=body
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_the_old_request_says_it_changed_nothing(api_client, db_session):
    """Exactly what the broken editor sent: the card leg, still pointing at the
    HYSA. A 200 — and now it admits it wrote nothing."""
    budget, _, hysa, _, in_leg = await _card_payment(api_client, db_session)
    body = await _patch(
        api_client,
        budget,
        in_leg.id,
        {
            "account_id": str(in_leg.account_id),
            "amount": "400.00",
            "date": TODAY.isoformat(),
            "approved": True,
            "transfer_account_id": str(hysa.id),
        },
    )
    assert body["changed"] is False
    assert body["counterpart_account_id"] == str(hysa.id)


async def test_retargeting_the_payment_says_it_changed(api_client, db_session):
    """The fixed editor sends the account the payee box named. The other leg
    moves to Harborstone Checking, and the answer says something was written."""
    budget, checking, _, _, in_leg = await _card_payment(api_client, db_session)
    body = await _patch(api_client, budget, in_leg.id, {"transfer_account_id": str(checking.id)})
    assert body["changed"] is True
    assert body["counterpart_account_id"] == str(checking.id)


async def test_an_ordinary_edit_says_it_changed(api_client, db_session):
    budget, _, _, _, in_leg = await _card_payment(api_client, db_session)
    body = await _patch(api_client, budget, in_leg.id, {"memo": "October payment"})
    assert body["changed"] is True


async def test_resending_the_same_memo_says_it_changed_nothing(api_client, db_session):
    budget, _, _, _, in_leg = await _card_payment(api_client, db_session)
    await _patch(api_client, budget, in_leg.id, {"memo": "October payment"})
    body = await _patch(api_client, budget, in_leg.id, {"memo": "October payment"})
    assert body["changed"] is False
