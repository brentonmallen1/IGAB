"""The "why is this classified this way?" endpoint.

Phase 2 silently changed what 169 of derkus's transactions count as. A
reclassification the user cannot audit is worse than one they can argue with,
so every row can say which rule decided it and why, in a sentence.
"""

from datetime import date

from igab.domain.activity_class import ActivityClass, ActivityReason

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)

TODAY = date.today()


async def _setup(db_session, owner):
    budget = await create_budget(db_session, owner)
    return budget, await create_account(db_session, budget, "Checking", on_budget=True)


async def test_explains_ordinary_spending(api_client, db_session):
    budget, checking = await _setup(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    txn = await create_transaction(db_session, budget, checking, "-60.00", TODAY, category=cat)

    resp = await api_client.get(f"/api/v1/transactions/{txn.id}/classification")
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_class"] == ActivityClass.SPENDING
    assert body["label"] == "Spending"
    assert body["reason"] == ActivityReason.DEFAULT_SPENDING
    assert body["explanation"]


async def test_explains_a_transfer_into_savings(api_client, db_session):
    """The case that changed. A user seeing this drop out of their spending
    report should be able to find out why without reading the source."""
    from igab.repositories.payee_repo import PayeeRepository

    budget, checking = await _setup(db_session, api_client.test_user)
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Savings")
    cat = await create_category(db_session, budget, group, "Investments")
    payee = await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, brokerage.id, brokerage.name
    )
    txn = await create_transaction(
        db_session, budget, checking, "-500.00", TODAY, category=cat, payee=payee
    )

    body = (await api_client.get(f"/api/v1/transactions/{txn.id}/classification")).json()
    assert body["activity_class"] == ActivityClass.SAVINGS
    assert body["label"] == "Savings"
    assert body["reason"] == ActivityReason.TRANSFER_TO_TRACKED_ASSET
    assert "tracked account" in body["explanation"]


async def test_unknown_transaction_is_404(api_client, db_session):
    import uuid

    resp = await api_client.get(f"/api/v1/transactions/{uuid.uuid4()}/classification")
    assert resp.status_code == 404


async def test_another_budget_cannot_be_read(api_client, db_session):
    from .factories import create_user

    other = await create_user(db_session)
    budget, checking = await _setup(db_session, other)
    txn = await create_transaction(db_session, budget, checking, "-10.00", TODAY)

    resp = await api_client.get(f"/api/v1/transactions/{txn.id}/classification")
    assert resp.status_code in (403, 404), "must not leak another budget's rows"


async def test_every_class_has_a_label():
    from igab.domain.activity_class import CLASS_LABEL

    for cls in ActivityClass:
        assert CLASS_LABEL.get(cls), f"{cls} has no label"
