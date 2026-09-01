"""The card timeline endpoint: a reserve's whole history, served.

The figures are the same walk the month endpoint serves — the last timeline
month must equal the served `CardStatus`, or the panel and its own drill-down
would tell different stories about one card.
"""

from datetime import date, timedelta
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_card_payment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
RECENT = TODAY - timedelta(days=10)
LONG_AGO = TODAY - timedelta(days=800)


async def _card_world(db_session, user):
    services = make_services(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    card = await create_account(
        db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
    )
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    return services, budget, checking, card, cat


async def test_the_timeline_ends_where_the_month_endpoint_stands(api_client, db_session):
    services, budget, checking, card, cat = await _card_world(db_session, api_client.test_user)
    month = RECENT.replace(day=1)
    await services.budgets.set_assignment(budget.id, cat.id, month, Decimal("200.00"))
    await create_transaction(db_session, budget, card, "-200.00", RECENT, category=cat)
    await create_card_payment(services, budget, checking, card, "500.00", RECENT)
    await db_session.commit()

    summary = await api_client.get(f"/api/v1/{budget.id}/months/{TODAY.isoformat()}")
    served = next(c for c in summary.json()["cards"] if c["name"] == "Sapphire Visa")

    resp = await api_client.get(
        f"/api/v1/{budget.id}/cards/{card.id}/timeline/{TODAY.isoformat()}"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Sapphire Visa"
    last = body["months"][-1]
    assert Decimal(last["set_aside"]) == Decimal(served["set_aside"])
    assert Decimal(last["balance"]) == Decimal(served["balance"])
    assert Decimal(last["uncovered"]) == Decimal(served["uncovered"])
    assert Decimal(last["short_reserved"]) == Decimal(served["short_reserved"])


async def test_the_breach_names_the_month_and_the_leg(api_client, db_session):
    """Pre-budget debt, one funded month, a full-statement payment: the
    reserve crosses below zero in the payment's month and the payments leg
    leads the ranking."""
    services, budget, checking, card, cat = await _card_world(db_session, api_client.test_user)
    month = RECENT.replace(day=1)
    await create_transaction(db_session, budget, card, "-2000.00", LONG_AGO)
    await services.budgets.set_assignment(budget.id, cat.id, month, Decimal("200.00"))
    await create_transaction(db_session, budget, card, "-200.00", RECENT, category=cat)
    await create_card_payment(services, budget, checking, card, "500.00", RECENT)
    await db_session.commit()

    resp = await api_client.get(
        f"/api/v1/{budget.id}/cards/{card.id}/timeline/{TODAY.isoformat()}"
    )
    body = resp.json()
    breach = body["breach"]
    assert breach is not None
    assert breach["month"] == month.isoformat()
    assert Decimal(breach["set_aside_after"]) == Decimal("-300.00")
    assert breach["legs"][0]["leg"] == "payments"
    # Every month carries its own position, against its own balance: the
    # LONG_AGO charge month reads fully uncovered with a zero reserve.
    first = body["months"][0]
    assert first["month"] == LONG_AGO.replace(day=1).isoformat()
    assert Decimal(first["uncovered"]) == Decimal("2000.00")


async def test_a_cash_account_is_not_a_card(api_client, db_session):
    services, budget, checking, _card, _cat = await _card_world(db_session, api_client.test_user)
    await db_session.commit()
    resp = await api_client.get(
        f"/api/v1/{budget.id}/cards/{checking.id}/timeline/{TODAY.isoformat()}"
    )
    assert resp.status_code == 404
