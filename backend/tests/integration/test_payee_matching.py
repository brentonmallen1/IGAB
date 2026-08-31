"""Payee regex match patterns: incoming raw payee names (manual entry, sync,
CSV import) that hit a payee's match_pattern resolve to that payee instead of
spawning a new one. Precedence is exact name > regex pattern > fuzzy."""

from datetime import date
from decimal import Decimal

from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_user,
    make_services,
)

TODAY = date(2026, 8, 1)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    return services, budget, checking


def _txn_data(account, raw_name: str) -> TransactionCreate:
    return TransactionCreate(
        account_id=account.id,
        date=TODAY,
        amount=Decimal("-12.34"),
        payee_name=raw_name,
    )


async def test_pattern_catches_randomized_bank_name(db_session):
    services, budget, checking = await _setup(db_session)
    payroll = await create_payee(
        db_session, budget, "Paycheck", match_pattern=r"^ACH DEPOSIT PAYROLL\b"
    )

    txn = await services.transactions.create(
        budget.id, _txn_data(checking, "ACH DEPOSIT PAYROLL 8842-XK71")
    )

    assert txn.payee_id == payroll.id
    payees = await services.payee_repo.get_all(budget.id)
    assert len(payees) == 1, "no new payee should be created on a pattern hit"


async def test_pattern_is_case_insensitive(db_session):
    services, budget, checking = await _setup(db_session)
    payee = await create_payee(db_session, budget, "Amazon", match_pattern=r"^AMZN Mktp")

    txn = await services.transactions.create(budget.id, _txn_data(checking, "amzn mktp US*1A2B3C"))

    assert txn.payee_id == payee.id


async def test_exact_name_beats_another_payees_pattern(db_session):
    services, budget, checking = await _setup(db_session)
    catchall = await create_payee(db_session, budget, "Amazon", match_pattern=r"AMAZON")
    exact = await create_payee(db_session, budget, "Amazon Fresh")

    txn = await services.transactions.create(budget.id, _txn_data(checking, "Amazon Fresh"))

    assert txn.payee_id == exact.id
    assert txn.payee_id != catchall.id


async def test_pattern_beats_fuzzy_match(db_session):
    services, budget, checking = await _setup(db_session)
    # Fuzzy would happily map "TARGET 00123" onto the existing "Target 00123 Store"
    fuzzy_candidate = await create_payee(db_session, budget, "Target 00123 Store")
    pattern_payee = await create_payee(db_session, budget, "Target", match_pattern=r"^TARGET\b")

    txn = await services.transactions.create(budget.id, _txn_data(checking, "TARGET 00123"))

    assert txn.payee_id == pattern_payee.id
    assert txn.payee_id != fuzzy_candidate.id


async def test_most_specific_pattern_wins(db_session):
    services, budget, checking = await _setup(db_session)
    broad = await create_payee(db_session, budget, "Uber", match_pattern=r"^UBER")
    specific = await create_payee(db_session, budget, "Uber Eats", match_pattern=r"^UBER\s*EATS")

    txn = await services.transactions.create(budget.id, _txn_data(checking, "UBER EATS PENDING"))

    assert txn.payee_id == specific.id
    assert txn.payee_id != broad.id


async def test_pattern_scoped_to_budget(db_session):
    services, budget, checking = await _setup(db_session)
    user2 = await create_user(db_session)
    other_budget = await create_budget(db_session, user2)
    await create_payee(db_session, other_budget, "Their Payroll", match_pattern=r"^ACH DEPOSIT")

    txn = await services.transactions.create(
        budget.id, _txn_data(checking, "ACH DEPOSIT PAYROLL 5511")
    )

    created = await services.payee_repo.get(txn.payee_id)
    assert created.budget_id == budget.id, "another budget's pattern must not capture the name"
    assert created.name == "ACH DEPOSIT PAYROLL 5511"


async def test_invalid_stored_pattern_skipped(db_session):
    services, budget, checking = await _setup(db_session)
    # Invalid patterns are rejected at the API layer; a stale/corrupt one in the
    # DB must not break resolution.
    await create_payee(db_session, budget, "Broken", match_pattern=r"([unclosed")
    good = await create_payee(db_session, budget, "Venmo", match_pattern=r"^VENMO\b")

    txn = await services.transactions.create(budget.id, _txn_data(checking, "VENMO PAYMENT 991"))

    assert txn.payee_id == good.id


async def test_import_batch_resolves_via_pattern(db_session):
    services, budget, _ = await _setup(db_session)
    payroll = await create_payee(
        db_session, budget, "Paycheck", match_pattern=r"^ACH DEPOSIT PAYROLL\b"
    )

    payee_map = await services.payee_repo.find_or_create_batch(
        budget.id,
        ["ACH DEPOSIT PAYROLL 111", "ACH DEPOSIT PAYROLL 222", "Coffee Shop"],
    )

    assert payee_map["ACH DEPOSIT PAYROLL 111"] == payroll.id
    assert payee_map["ACH DEPOSIT PAYROLL 222"] == payroll.id
    assert payee_map["Coffee Shop"] != payroll.id
    payees = await services.payee_repo.get_all(budget.id)
    assert len(payees) == 2, "only Coffee Shop should be newly created"


async def test_patch_sets_and_clears_pattern(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    payee = await create_payee(db_session, budget, "Paycheck")

    resp = await api_client.patch(
        f"/api/v1/payees/{payee.id}", json={"match_pattern": r"^ACH DEPOSIT\b"}
    )
    assert resp.status_code == 200
    assert resp.json()["match_pattern"] == r"^ACH DEPOSIT\b"

    resp = await api_client.patch(f"/api/v1/payees/{payee.id}", json={"match_pattern": None})
    assert resp.status_code == 200
    assert resp.json()["match_pattern"] is None


async def test_patch_normalizes_and_clears_mapping_samples(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    payee = await create_payee(db_session, budget, "Paycheck")

    # Trimmed, unique ignoring case, and a comma inside a name stays inside it.
    resp = await api_client.patch(
        f"/api/v1/payees/{payee.id}",
        json={
            "mapping_samples": [
                " NORTHWIND PAYROLL ",
                "northwind payroll",
                "",
                "NORTHWIND … DOE, JANE",
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["mapping_samples"] == ["NORTHWIND PAYROLL", "NORTHWIND … DOE, JANE"]

    resp = await api_client.patch(f"/api/v1/payees/{payee.id}", json={"mapping_samples": None})
    assert resp.status_code == 200
    assert resp.json()["mapping_samples"] == []


async def test_patch_rejects_invalid_regex(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    payee = await create_payee(db_session, budget, "Paycheck")

    resp = await api_client.patch(f"/api/v1/payees/{payee.id}", json={"match_pattern": "([bad"})
    assert resp.status_code == 422
    assert "regular expression" in resp.text

    refreshed = await make_services(db_session).payee_repo.get(payee.id)
    assert refreshed.match_pattern is None


async def test_patch_blank_pattern_normalizes_to_null(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    payee = await create_payee(db_session, budget, "Paycheck", match_pattern=r"^OLD\b")

    resp = await api_client.patch(f"/api/v1/payees/{payee.id}", json={"match_pattern": "   "})
    assert resp.status_code == 200
    assert resp.json()["match_pattern"] is None
