"""An income category has no envelope money — and the month endpoint says so.

A category in a system (Income) group is where income is *filed*. Nothing can
be assigned to it and nothing drains it, so the carryover arithmetic produced
a lifetime total of every dollar ever received (1.6M on one imported budget)
and the grid drew it as "Available" under a hero named Ready to Assign. The
server now blanks the two figures on such rows, keeps the month's income as
`activity`, and refuses to put money into or take it out of one.
"""

from datetime import date
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
)

JUL = date(2026, 7, 1)
AUG = date(2026, 8, 1)


async def _budget(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income, "Inflow")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    # Two months of income, one month of budgeting.
    await create_transaction(
        db_session, budget, checking, "3000.00", date(2026, 7, 2), category=inflow
    )
    await create_transaction(
        db_session, budget, checking, "3100.00", date(2026, 8, 3), category=inflow
    )
    await create_budget_assignment(db_session, budget, rent, AUG, "1200.00")
    await create_transaction(
        db_session, budget, checking, "-1200.00", date(2026, 8, 5), category=rent
    )
    return budget, inflow, rent


async def _month(api_client, budget, month):
    resp = await api_client.get(f"/api/v1/{budget.id}/months/{month.isoformat()}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_an_income_row_has_no_assigned_or_available_but_keeps_its_income(
    api_client, db_session
):
    budget, inflow, rent = await _budget(db_session, api_client.test_user)
    body = await _month(api_client, budget, AUG)
    rows = {r["category_id"]: r for r in body["category_balances"]}

    income = rows[str(inflow.id)]
    assert income["assigned"] is None
    assert income["available"] is None
    assert Decimal(income["activity"]) == Decimal("3100.00")
    assert income["target_status"] is None

    envelope = rows[str(rent.id)]
    assert Decimal(envelope["assigned"]) == Decimal("1200.00")
    assert Decimal(envelope["available"]) == Decimal("0.00")


async def test_the_months_totals_are_envelope_totals(api_client, db_session):
    """Income is not part of "assigned" or "activity" for the month — it is
    what Ready to Assign is made of."""
    budget, _, _ = await _budget(db_session, api_client.test_user)
    body = await _month(api_client, budget, AUG)
    assert Decimal(body["total_assigned"]) == Decimal("1200.00")
    assert Decimal(body["total_activity"]) == Decimal("-1200.00")
    # 6100 in, 1200 assigned (and spent): the hero is untouched by the change.
    assert Decimal(body["to_be_assigned"]) == Decimal("4900.00")


async def test_assigning_to_an_income_category_is_refused(api_client, db_session):
    budget, inflow, _ = await _budget(db_session, api_client.test_user)
    before = await _month(api_client, budget, AUG)
    resp = await api_client.patch(
        f"/api/v1/categories/{inflow.id}/assignment",
        json={"amount": "100.00"},
        params={"month": AUG.isoformat(), "budget_id": str(budget.id)},
    )
    assert resp.status_code == 400
    assert "Income categories" in resp.json()["detail"]
    after = await _month(api_client, budget, AUG)
    assert after["to_be_assigned"] == before["to_be_assigned"]


async def test_moving_money_into_or_out_of_an_income_category_is_refused(api_client, db_session):
    budget, inflow, rent = await _budget(db_session, api_client.test_user)
    before = await _month(api_client, budget, AUG)
    for src, dst in ((None, inflow), (inflow, rent)):
        resp = await api_client.post(
            f"/api/v1/{budget.id}/budget/move-money",
            json={
                "from_category_id": str(src.id) if src else None,
                "to_category_id": str(dst.id) if dst else None,
                "amount": "50.00",
                "month": AUG.isoformat(),
            },
        )
        assert resp.status_code == 400, resp.text
        assert "Income categories" in resp.json()["detail"]
    after = await _month(api_client, budget, AUG)
    assert after["to_be_assigned"] == before["to_be_assigned"]
    assert after["category_balances"] == before["category_balances"]
