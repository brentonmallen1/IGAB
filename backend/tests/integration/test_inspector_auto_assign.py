"""The inspector's Auto-Assign buttons, as one write over many envelopes.

The buttons used to run one envelope at a time — a history read and a
get-or-create-update-reselect per category, about ten statements each — so
"Assigned Last Month" over a seventy-envelope budget issued 737 statements and
took over half a second. They now read every envelope's history in one pass
and write the month once (`BudgetService.set_assignments`). These tests pin
that the figures did not move in the process: every expected amount below is
worked out by hand from the fixture, never read back from the code.

Fixture, viewed from July 2026 (history window: January–June):

    Rent       assigned 1000 in Apr, May, Jun; spent 1000 in each
    Groceries  assigned 200 May, 300 Jun (and 999 last December, outside the
               window); spent 60 Mar, 150 May, 250 Jun, and 40 in July,
               which is this month and must not count
    Gifts      no history at all; 25 assigned in July

Amounts are invented and round.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from igab.db.models import BudgetAssignment

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
)
from .invariants import assert_financial_invariants

MONTH = date(2026, 7, 1)


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    rent = await create_category(db_session, budget, everyday, "Rent")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    gifts = await create_category(db_session, budget, everyday, "Gifts")

    for month in range(1, 8):
        await create_transaction(
            db_session, budget, checking, "3000.00", date(2026, month, 1), category=inflow
        )
    for month in (4, 5, 6):
        await create_budget_assignment(db_session, budget, rent, date(2026, month, 1), "1000")
        await create_transaction(
            db_session, budget, checking, "-1000.00", date(2026, month, 3), category=rent
        )
    await create_budget_assignment(db_session, budget, groceries, date(2025, 12, 1), "999")
    await create_budget_assignment(db_session, budget, groceries, date(2026, 5, 1), "200")
    await create_budget_assignment(db_session, budget, groceries, date(2026, 6, 1), "300")
    for day, amount in ((date(2026, 3, 9), "-60.00"), (date(2026, 5, 9), "-150.00")):
        await create_transaction(db_session, budget, checking, amount, day, category=groceries)
    await create_transaction(
        db_session, budget, checking, "-250.00", date(2026, 6, 9), category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-40.00", date(2026, 7, 9), category=groceries
    )
    await create_budget_assignment(db_session, budget, gifts, MONTH, "25")
    return budget, inflow, {"Rent": rent, "Groceries": groceries, "Gifts": gifts}


async def _july(db_session, budget) -> dict[str, D]:
    rows = (
        await db_session.execute(
            select(BudgetAssignment.category_id, BudgetAssignment.assigned).where(
                BudgetAssignment.budget_id == budget.id, BudgetAssignment.month == MONTH
            )
        )
    ).all()
    return {str(category_id): assigned for category_id, assigned in rows}


def _ids(cats) -> list:
    return [c.id for c in cats.values()]


async def _press(api_client, budget, action: str, category_ids):
    return await api_client.post(
        f"/api/v1/{budget.id}/categories/auto-assign",
        json={
            "month": MONTH.isoformat(),
            "action": action,
            "category_ids": [str(c) for c in category_ids],
        },
    )


#: (Rent, Groceries, Gifts) after each button, by hand from the fixture.
EXPECTED = {
    "last_month_assigned": ("1000", "300", "0"),
    "last_month_spent": ("1000", "250", "0"),
    # Rent: 3000 over its 3 months with data. Groceries: (200 + 300) over 3
    # months with data (Mar has spending, May and Jun both) — December's 999
    # is outside the window.
    "average_assigned": ("1000", "166.67", "0"),
    # Groceries: (60 + 150 + 250) / 3; July's 40 is this month, not history.
    "average_spent": ("1000", "153.33", "0"),
    "reset": ("0", "0", "0"),
}


@pytest.mark.parametrize("action", sorted(EXPECTED))
async def test_each_button_sets_every_envelope_to_its_own_figure(api_client, db_session, action):
    budget, _, cats = await _budget(db_session, api_client)

    resp = await _press(api_client, budget, action, _ids(cats))

    assert resp.status_code == 204, resp.text
    july = await _july(db_session, budget)
    got = tuple(july.get(str(cats[name].id), D("0")) for name in ("Rent", "Groceries", "Gifts"))
    assert got == tuple(D(x) for x in EXPECTED[action])
    await assert_financial_invariants(db_session, budget.id)


@pytest.mark.parametrize("action", sorted(EXPECTED))
async def test_one_undo_takes_the_whole_button_back(api_client, db_session, action):
    budget, _, cats = await _budget(db_session, api_client)
    before = await _july(db_session, budget)
    assert (await _press(api_client, budget, action, _ids(cats))).is_success

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/undo")

    assert resp.status_code == 200, resp.text
    after = await _july(db_session, budget)
    # A row the button created holds zero after the undo; it held nothing before.
    assert {k: v for k, v in after.items() if v != 0} == {k: v for k, v in before.items() if v}


async def test_the_history_the_buttons_show_is_the_history_they_apply(api_client, db_session):
    """The figure on each button comes from the batch history; the button
    then sets exactly that figure. Both read `get_category_histories`."""
    budget, _, cats = await _budget(db_session, api_client)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/categories/history/batch",
        params={"month": MONTH.isoformat()},
        json={"category_ids": [str(c.id) for c in cats.values()]},
    )
    assert resp.status_code == 200, resp.text
    served = {h["category_id"]: h for h in resp.json()}
    for i, name in enumerate(("Rent", "Groceries", "Gifts")):
        for action in ("last_month_assigned", "last_month_spent", "average_assigned"):
            assert D(str(served[str(cats[name].id)][action])) == D(EXPECTED[action][i])
    assert served[str(cats["Gifts"].id)]["months_included"] == 1


async def test_history_is_read_from_the_month_asked_not_today(api_client, db_session):
    """Viewed from June the window is December–May. The inspector sent no
    month at all, so a past month's buttons showed today's history while the
    POST — which does send the month — applied that month's."""
    budget, _, cats = await _budget(db_session, api_client)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/categories/history/batch",
        params={"month": "2026-06-01"},
        json={"category_ids": [str(cats["Groceries"].id)]},
    )
    assert resp.status_code == 200, resp.text
    (groceries,) = resp.json()
    # Last month is May. Months with data: Dec (999 assigned), Mar (60
    # spent), May — three.
    assert D(str(groceries["last_month_assigned"])) == D("200")
    assert D(str(groceries["last_month_spent"])) == D("150")
    assert D(str(groceries["average_assigned"])) == D("399.67")
    assert D(str(groceries["average_spent"])) == D("70")


async def test_an_income_category_refuses_the_whole_press(api_client, db_session):
    """Income holds no money, and naming it fails the request rather than
    silently skipping it — so the inspector must not send it (the month
    summary sent every listed category; it now sends the fundable ones)."""
    budget, inflow, cats = await _budget(db_session, api_client)
    before = await _july(db_session, budget)

    resp = await _press(api_client, budget, "last_month_assigned", [*_ids(cats), inflow.id])

    assert resp.status_code == 400
    assert "Income categories do not hold money" in resp.text
    assert await _july(db_session, budget) == before


async def test_a_foreign_category_refuses_the_whole_press(api_client, db_session):
    budget, _, cats = await _budget(db_session, api_client)
    _, _, theirs = await _budget(db_session, api_client)
    before = await _july(db_session, budget)

    resp = await _press(api_client, budget, "reset", [*_ids(cats), theirs["Rent"].id])

    assert resp.status_code == 400
    assert "does not belong to this budget" in resp.text
    assert await _july(db_session, budget) == before
