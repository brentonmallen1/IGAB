"""Loan-polish surface: manual-fallback balances, implied term, and the
concrete numbers the payoff copy leans on."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.account_repo import AccountRepository

from .factories import (
    create_account,
    create_budget,
    create_transaction,
    create_transfer,
    money,
)

TODAY = date.today()


def _month_start(d: date, months_back: int = 0) -> date:
    total = d.year * 12 + (d.month - 1) - months_back
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


async def _get_liability(api_client, budget_id, liability_id):
    resp = await api_client.get(f"/api/v1/{budget_id}/liabilities")
    assert resp.status_code == 200
    return next(item for item in resp.json() if item["id"] == str(liability_id))


async def test_a_fresh_loan_account_says_empty_rather_than_paid_off(api_client, db_session):
    """A companion created with its account has no ledger and no remembered
    balance, and used to report `ledger` / $0 — which the page renders as
    "Paid off". A student loan account created ten seconds ago is not settled;
    it is unanswered, and `empty` is how the server says so.
    """
    budget = await create_budget(db_session, api_client.test_user)
    # Through the API: the route is what gives a liability account its
    # companion, which is the situation being described.
    made = await api_client.post(
        f"/api/v1/{budget.id}/accounts",
        json={"name": "Student Loan", "account_type": "loan", "on_budget": False},
    )
    assert made.status_code == 201, made.text
    account_id = made.json()["id"]

    listed = await api_client.get(f"/api/v1/{budget.id}/liabilities")
    assert listed.status_code == 200
    companion = next(item for item in listed.json() if item["linked_account_id"] == account_id)

    assert companion["balance_source"] == "empty"
    assert money(companion["current_balance"]) == Decimal("0")
    # Nothing was filled in, so nothing is claimed about the contract either.
    assert companion["terms_complete"] is False

    # The register answers it: one opening balance and the source is the ledger.
    account = await AccountRepository(db_session).get(uuid.UUID(account_id))
    assert account is not None
    await create_transaction(db_session, budget, account, Decimal("-24000.00"), TODAY)
    after = await _get_liability(api_client, budget.id, companion["id"])
    assert after["balance_source"] == "ledger"
    assert money(after["current_balance"]) == Decimal("24000.00")


async def test_a_rate_alone_is_enough_to_record(api_client, db_session):
    """The terms are optional in the model and were required by the create
    schema — the one path that disagreed. A debt whose balance you know and
    whose rate you do not is a real thing to want to record."""
    budget = await create_budget(db_session, api_client.test_user)

    created = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "Family Loan",
            "liability_type": "other",
            "manual_balance": "1200.00",
        },
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["interest_rate"] is None
    assert body["terms_complete"] is False
    assert money(body["current_balance"]) == Decimal("1200.00")


async def test_manual_fallback_until_register_has_transactions(api_client, db_session):
    """An unmanaged mortgage linked to an EMPTY account must not report $0
    owed ('Paid off') — the pre-link manual balance stands in until the
    register gets its first transaction."""
    budget = await create_budget(db_session, api_client.test_user)
    loan = await create_account(
        db_session, budget, "Mortgage", account_type="loan", on_budget=False
    )

    created = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "Mortgage",
            "liability_type": "mortgage",
            "interest_rate": "6.5",
            "minimum_payment": "1896.20",
            "manual_balance": "180000.00",
        },
    )
    assert created.status_code == 201
    liability_id = created.json()["id"]
    assert created.json()["balance_source"] == "manual"

    linked = await api_client.patch(
        f"/api/v1/{budget.id}/liabilities/{liability_id}",
        json={"linked_account_id": str(loan.id)},
    )
    assert linked.status_code == 200
    body = linked.json()
    assert body["mode"] == "managed"
    assert body["balance_source"] == "manual_fallback"
    assert money(body["current_balance"]) == Decimal("180000.00")
    # No "Paid off" lie: the baseline schedule runs on the fallback balance
    assert body["baseline_never_pays_off"] is False

    # First real transaction flips the balance to the ledger
    await create_transaction(db_session, budget, loan, "-175000.00", TODAY - timedelta(days=3))
    body = await _get_liability(api_client, budget.id, liability_id)
    assert body["balance_source"] == "ledger"
    assert money(body["current_balance"]) == Decimal("175000.00")


async def test_implied_term_for_realistic_mortgage(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "House",
            "liability_type": "mortgage",
            "interest_rate": "6.5",
            "minimum_payment": "1896.20",  # ~the 30-year P&I for 300k at 6.5%
            "manual_balance": "280000.00",
            "origination_date": "2020-01-01",
            "original_principal": "300000.00",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["implied_never_pays_off"] is False
    assert body["implied_term_months"] is not None
    assert 350 <= body["implied_term_months"] <= 372
    # This month's interest at the current balance: 280000 × 6.5% / 12
    assert money(body["monthly_interest_now"]) == Decimal("1516.67")


async def test_pi_mismatch_flags_implied_never_pays_off(api_client, db_session):
    """The escrow trap: a principal-only 'minimum' below monthly interest
    could never have amortized the original loan — flagged explicitly."""
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "House",
            "liability_type": "mortgage",
            "interest_rate": "6.5",
            "minimum_payment": "1000.00",  # below the ~1625 first-month interest
            "manual_balance": "280000.00",
            "origination_date": "2020-01-01",
            "original_principal": "300000.00",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["implied_never_pays_off"] is True
    assert body["implied_term_months"] is None
    assert body["baseline_never_pays_off"] is True


async def test_promo_fields_round_trip_with_projection(api_client, db_session):
    """A 0%-until-deadline furniture deal: fields persist and the response
    carries a promo projection with a deferred-interest estimate."""
    budget = await create_budget(db_session, api_client.test_user)
    promo_end = _month_start(TODAY, -8)  # first of the month ~8 months out

    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "Furniture",
            "liability_type": "other",
            "interest_rate": "29.99",
            "minimum_payment": "95.00",
            "manual_balance": "1900.00",
            "promo_end_date": promo_end.isoformat(),
            "promo_deferred_interest": True,
            "term_months": 24,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["promo_end_date"] == promo_end.isoformat()
    assert body["promo_deferred_interest"] is True
    assert body["term_months"] == 24

    projection = body["promo_projection"]
    assert projection is not None
    assert projection["months_until_promo_end"] >= 7
    remaining = Decimal(projection["balance_at_promo_end_minimum"])
    assert Decimal("0") < remaining < Decimal("1900.00")
    assert projection["clears_before_promo"] is False
    assert Decimal(projection["deferred_interest_estimate"]) > Decimal("0")
    # 0% during the promo keeps the minimum well above interest → pays off
    assert body["baseline_never_pays_off"] is False


async def test_no_promo_projection_without_promo_date(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "Plain",
            "liability_type": "personal",
            "interest_rate": "6.0",
            "minimum_payment": "100.00",
            "manual_balance": "1000.00",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["promo_projection"] is None
    assert resp.json()["promo_end_date"] is None


async def test_typical_recent_payment_from_ledger(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    loan = await create_account(
        db_session, budget, "Car Loan", account_type="loan", on_budget=False
    )
    await create_transaction(db_session, budget, loan, "-7000.00", _month_start(TODAY, 4))
    await create_transfer(
        db_session, budget, checking, loan, "275.00", _month_start(TODAY, 2) + timedelta(days=9)
    )
    await create_transfer(
        db_session, budget, checking, loan, "275.00", _month_start(TODAY, 1) + timedelta(days=9)
    )

    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "Car",
            "liability_type": "auto",
            "interest_rate": "6.0",
            "minimum_payment": "275.00",
            "linked_account_id": str(loan.id),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_live_projection"] is True
    assert money(body["typical_recent_payment"]) == Decimal("275.00")
    # 6450 owed × 6% / 12
    assert money(body["monthly_interest_now"]) == Decimal("32.25")
    assert body["balance_source"] == "ledger"
