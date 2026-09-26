"""Loan-polish surface: manual-fallback balances, implied term, and the
concrete numbers the payoff copy leans on."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from igab.domain.payee_names import STARTING_BALANCE_PAYEE
from igab.repositories.account_repo import AccountRepository

from .factories import (
    create_account,
    create_budget,
    create_payee,
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


# ─── A register that contradicts the account's kind ──────────────────────────


async def test_a_positive_ledger_on_a_liability_reads_inverted_not_paid_off(api_client, db_session):
    """The clamp that turned a corrupted mortgage into a green Paid off pill.

    `max(0, -ledger)` treats the impossible state and the settled state
    identically. A liability account cannot hold money, so a positive ledger
    is not a paid-off loan — it is a register whose signs are inverted, and
    the page has to say so rather than congratulate the user.
    """
    budget = await create_budget(db_session, api_client.test_user)
    made = await api_client.post(
        f"/api/v1/{budget.id}/accounts",
        json={"name": "Harborstone Mortgage", "account_type": "mortgage", "on_budget": False},
    )
    assert made.status_code == 201, made.text
    account_id = made.json()["id"]
    account = await AccountRepository(db_session).get(uuid.UUID(account_id))
    assert account is not None

    # The inversion: a lender-frame feed taken verbatim leaves the register
    # holding the balance rather than owing it, while the bank goes on
    # reporting a debt. That disagreement is the evidence — a positive
    # register alone is an overpayment and floors at zero, as it always has.
    await create_transaction(db_session, budget, account, Decimal("248900.00"), TODAY)
    account.simplefin_balance = Decimal("-248900.00")
    await db_session.flush()

    listed = await api_client.get(f"/api/v1/{budget.id}/liabilities")
    companion = next(item for item in listed.json() if item["linked_account_id"] == account_id)
    assert companion["balance_source"] == "inverted"
    assert money(companion["current_balance"]) == Decimal("248900.00"), (
        "the magnitude, so the page can show what it found"
    )
    assert money(companion["current_balance"]) != Decimal("0"), "never Paid off"


async def test_an_overpaid_card_still_floors_at_zero(api_client, db_session):
    """The false positive the bank-evidence rule exists to avoid. Overpaying
    a card by $50 is ordinary, the bank agrees you are in credit, and the
    answer is the long-standing floor — not an accusation."""
    budget = await create_budget(db_session, api_client.test_user)
    made = await api_client.post(
        f"/api/v1/{budget.id}/accounts",
        json={"name": "Sapphire Visa", "account_type": "credit_card", "on_budget": True},
    )
    account_id = made.json()["id"]
    account = await AccountRepository(db_session).get(uuid.UUID(account_id))
    assert account is not None
    await create_transaction(db_session, budget, account, Decimal("50.00"), TODAY)
    account.simplefin_balance = Decimal("50.00")
    await db_session.flush()

    listed = await api_client.get(f"/api/v1/{budget.id}/liabilities")
    companion = next(item for item in listed.json() if item["linked_account_id"] == account_id)
    assert companion["balance_source"] == "ledger"
    assert money(companion["current_balance"]) == Decimal("0")


# ─── The estimated interest a YNAB export cannot carry ───────────────────────
# A loan imported from YNAB reads one month of interest low: YNAB derives a
# current-month charge from the loan terms and only turns it into a register
# row at reconcile time. The figure is not in the export and the export has
# nowhere to carry the rate either, so the user supplies the terms.


async def _loan_with_terms(
    api_client,
    db_session,
    *,
    rate: str | None,
    balance: str = "24000.00",
    opened: date | None = None,
    opening_payee: str | None = None,
):
    budget = await create_budget(db_session, api_client.test_user)
    made = await api_client.post(
        f"/api/v1/{budget.id}/accounts",
        json={"name": "Harborstone Auto Loan", "account_type": "loan", "on_budget": False},
    )
    account_id = made.json()["id"]
    account = await AccountRepository(db_session).get(uuid.UUID(account_id))
    assert account is not None
    # Dated well before this month by default: an origination row under any
    # name but Starting Balance is a plain outflow too, and a loan opened in
    # the same month as a payment would be read as that month's interest.
    payee = await create_payee(db_session, budget, opening_payee) if opening_payee else None
    await create_transaction(
        db_session,
        budget,
        account,
        Decimal(f"-{balance}"),
        opened or _month_start(TODAY, 6),
        payee=payee,
    )

    listed = await api_client.get(f"/api/v1/{budget.id}/liabilities")
    companion = next(item for item in listed.json() if item["linked_account_id"] == account_id)
    if rate is not None:
        patched = await api_client.patch(
            f"/api/v1/{budget.id}/liabilities/{companion['id']}",
            json={"interest_rate": rate},
        )
        assert patched.status_code == 200, patched.text
    return budget, account, companion


async def test_an_imported_loan_claims_no_estimate_until_terms_are_filled_in(
    api_client, db_session
):
    """The imported case: the rate column is null because the export
    structurally cannot fill it, so nothing is claimed. Null is the honest
    answer, and it is exactly why the user has to be asked."""
    budget, _account, companion = await _loan_with_terms(api_client, db_session, rate=None)
    row = await _get_liability(api_client, budget.id, companion["id"])
    assert row["interest_rate"] is None
    assert row["estimated_interest_this_month"] is None
    assert money(row["balance_with_estimate"]) == money(row["current_balance"])


async def test_estimated_interest_is_shown_once_the_terms_are_known(api_client, db_session):
    """6% a year on 24,000 is 120.00 a month — and it is added to the
    balance separately, never folded into the posted figure."""
    budget, _account, companion = await _loan_with_terms(api_client, db_session, rate="6")
    row = await _get_liability(api_client, budget.id, companion["id"])
    assert money(row["current_balance"]) == Decimal("24000.00")
    assert money(row["estimated_interest_this_month"]) == Decimal("120.00")
    assert money(row["balance_with_estimate"]) == Decimal("24120.00")


async def test_estimated_interest_is_suppressed_by_a_posted_interest_row(api_client, db_session):
    """Ordering matters. Reconciling in the source application materialises
    the charge as a real row; adding the estimate on top of it would count
    the same money twice."""
    budget, account, companion = await _loan_with_terms(api_client, db_session, rate="6")
    checking = await create_account(db_session, budget, "Everyday Checking")
    # The real shape of the month after a reconcile: the payment posted, and
    # reconciling materialised the interest charge as a real row beside it.
    # A plain outflow on a tracked debt IS an interest charge, but only in a
    # month a payment also arrived — which is what keeps the origination row
    # from being read as one.
    await create_transfer(db_session, budget, checking, account, "500.00", TODAY)
    await create_transaction(db_session, budget, account, Decimal("-120.00"), TODAY)

    row = await _get_liability(api_client, budget.id, companion["id"])
    assert row["estimated_interest_this_month"] is None, "the month already has one"
    assert money(row["current_balance"]) == Decimal("23620.00")
    assert money(row["balance_with_estimate"]) == money(row["current_balance"])


async def test_a_payment_alone_does_not_suppress_the_estimate(api_client, db_session):
    """The reported gap is open for exactly this window: the payment has
    posted, the account has not been reconciled, so the charge is still only
    an estimate and the balance reads one month of interest low without it."""
    budget, account, companion = await _loan_with_terms(api_client, db_session, rate="6")
    checking = await create_account(db_session, budget, "Everyday Checking")
    await create_transfer(db_session, budget, checking, account, "500.00", TODAY)

    row = await _get_liability(api_client, budget.id, companion["id"])
    assert money(row["current_balance"]) == Decimal("23500.00")
    assert money(row["estimated_interest_this_month"]) == Decimal("117.50")
    assert money(row["balance_with_estimate"]) == Decimal("23617.50")


async def test_a_starting_balance_beside_a_payment_is_not_the_months_interest(
    api_client, db_session
):
    """A first sync anchors a tracked loan the day before its oldest row —
    often in the month a payment arrived. Read as a plain outflow, the whole
    24,000 opening was that month's interest charge, and it suppressed the
    estimate as though the month had been reconciled. A Starting Balance row
    is where the ledger begins (`DEBT_INTEREST_ROW`), so the month reads as a
    payment alone: the same 117.50 as the test above."""
    budget, account, companion = await _loan_with_terms(
        api_client,
        db_session,
        rate="6",
        opened=_month_start(TODAY),
        opening_payee=STARTING_BALANCE_PAYEE,
    )
    checking = await create_account(db_session, budget, "Everyday Checking")
    await create_transfer(db_session, budget, checking, account, "500.00", TODAY)

    row = await _get_liability(api_client, budget.id, companion["id"])
    assert money(row["current_balance"]) == Decimal("23500.00")
    assert money(row["estimated_interest_this_month"]) == Decimal("117.50")
