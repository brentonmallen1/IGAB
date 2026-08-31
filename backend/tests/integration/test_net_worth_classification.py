"""Net worth spans every account, bucketed by classification.

The friend-reported bug this pins: off-budget assets (brokerage) and
off-budget loans were excluded from net worth entirely, and a managed
liability on an off-budget account appeared in neither the account sum nor
the unmanaged bucket.
"""

from datetime import date, timedelta
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_liability_snapshot,
    create_transaction,
)

TODAY = date.today()


async def _setup(db_session, owner):
    budget = await create_budget(db_session, owner)
    checking = await create_account(db_session, budget, "Checking")
    visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    loan = await create_account(
        db_session, budget, "Mortgage", account_type="loan", on_budget=False
    )

    old = TODAY - timedelta(days=45)
    await create_transaction(db_session, budget, checking, "2500.00", old)
    await create_transaction(db_session, budget, visa, "-420.00", old)
    await create_transaction(db_session, budget, brokerage, "12000.00", old)
    await create_transaction(db_session, budget, loan, "-250000.00", old)

    # Managed liability on the off-budget loan: counted ONCE, via the ledger
    await create_liability(
        db_session, budget, "Mortgage", liability_type="mortgage", linked_account_id=loan.id
    )
    # Unmanaged debt joins the liability side through the manual bucket
    unmanaged = await create_liability(
        db_session,
        budget,
        "Dental Plan",
        liability_type="medical",
        manual_balance=Decimal("855.00"),
    )
    await create_liability_snapshot(db_session, unmanaged, old, Decimal("855.00"))
    return budget


async def test_net_worth_includes_every_account(api_client, db_session):
    budget = await _setup(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 3})
    assert resp.status_code == 200
    body = resp.json()
    latest = body["points"][-1]

    assert Decimal(latest["total_assets"]) == Decimal("14500.00")  # 2500 + 12000
    # 420 (visa) + 250000 (mortgage ledger) + 855 (unmanaged) — the managed
    # mortgage is NOT double counted through the unmanaged bucket
    assert Decimal(latest["total_liabilities"]) == Decimal("251275.00")
    assert Decimal(latest["net_worth"]) == Decimal("-236775.00")
    assert Decimal(body["unmanaged_liability_total"]) == Decimal("855.00")

    # The identity holds on every point, and snapshots carry classification
    for point in body["points"]:
        assert Decimal(point["net_worth"]) == Decimal(point["total_assets"]) - Decimal(
            point["total_liabilities"]
        )
    by_name = {s["account_name"]: s for s in latest["accounts"]}
    assert by_name["Brokerage"]["classification"] == "asset"
    assert by_name["Mortgage"]["classification"] == "liability"


async def test_dashboard_net_worth_agrees_with_history(api_client, db_session):
    budget = await _setup(db_session, api_client.test_user)

    history = (
        await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 3})
    ).json()
    dashboard = (await api_client.get(f"/api/v1/{budget.id}/reports/dashboard")).json()

    assert Decimal(dashboard["net_worth"]) == Decimal(history["points"][-1]["net_worth"])


async def test_composition_includes_off_budget_series(api_client, db_session):
    budget = await _setup(db_session, api_client.test_user)

    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/account-composition", params={"months": 3}
    )
    assert resp.status_code == 200
    latest = resp.json()["points"][-1]["balances"]
    assert Decimal(latest["investment"]) == Decimal("12000.00")
    assert Decimal(latest["loan"]) == Decimal("-250000.00")
    assert Decimal(latest["checking"]) == Decimal("2500.00")
    assert Decimal(latest["credit_card"]) == Decimal("-420.00")


async def test_overdrawn_checking_reduces_assets(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings", account_type="savings")
    await create_transaction(db_session, budget, checking, "-300.00", TODAY - timedelta(days=5))
    await create_transaction(db_session, budget, savings, "1000.00", TODAY - timedelta(days=5))

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth", params={"months": 1})
    latest = resp.json()["points"][-1]
    assert Decimal(latest["total_assets"]) == Decimal("700.00")
    assert Decimal(latest["total_liabilities"]) == Decimal("0")
    assert Decimal(latest["net_worth"]) == Decimal("700.00")
