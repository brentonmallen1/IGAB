"""Phase 5 spec: exact CSV amount parsing (never through float), NaN/scale
validation at the API boundary, and the SQL-backed duplicate scan."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.money import parse_csv_amount

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()


class TestCsvAmountParsing:
    def test_exact_decimal_no_float_artifacts(self):
        assert parse_csv_amount("0.10") == Decimal("0.10")
        assert parse_csv_amount("1234.56") == Decimal("1234.56")

    def test_currency_symbols_and_thousands(self):
        assert parse_csv_amount("$1,234.56") == Decimal("1234.56")
        assert parse_csv_amount("€1.234,56") == Decimal("1234.56")
        assert parse_csv_amount("12,345") == Decimal("12345")

    def test_parentheses_and_signs(self):
        assert parse_csv_amount("(50.00)") == Decimal("-50.00")
        assert parse_csv_amount("-50.00") == Decimal("-50.00")
        assert parse_csv_amount("+50.00") == Decimal("50.00")

    def test_eu_decimal_comma_with_dot_thousands(self):
        # Both separators present: the rightmost one is the decimal point
        assert parse_csv_amount("1.234,56") == Decimal("1234.56")
        assert parse_csv_amount("1,234.56") == Decimal("1234.56")

    def test_ambiguous_single_comma_rejected_not_corrupted(self):
        """'12,34' could be 12.34 (EU) or a typo — never guess to 1234."""
        with pytest.raises(ValueError, match="ambiguous"):
            parse_csv_amount("12,34")

    def test_garbage_rejected(self):
        for bad in ("", "abc", "1.2.3.4", "NaN", "Infinity"):
            with pytest.raises(ValueError):
                parse_csv_amount(bad)


async def test_csv_import_endpoint_exact_amounts(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    services = make_services(db_session)

    csv = (
        "Date,Payee,Amount,Memo\n"
        "2026-07-01,Coffee,-0.10,\n"
        "2026-07-02,Store,\"$1,234.56\",\n"
        "2026-07-03,Refund,(25.00),\n"
        "2026-07-04,Broken,12,34\n"  # unquoted comma splits columns; amount '12'
    )
    resp = await api_client.post(
        f"/api/v1/{budget.id}/import/csv",
        params={"account_id": str(account.id)},
        files={"file": ("txns.csv", csv.encode(), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 4

    balance = await services.account_repo.get_balance(account.id)
    assert balance == Decimal("-0.10") + Decimal("1234.56") - Decimal("25.00") + Decimal("12")


async def test_api_rejects_nan_infinity_and_subcent_amounts(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")

    def txn_body(amount):
        return {
            "account_id": str(account.id),
            "date": "2026-07-10",
            "amount": amount,
            "cleared": "cleared",
        }

    for bad in ("NaN", "Infinity", "-Infinity", "10.00001", "99999999999999999"):
        resp = await api_client.post(f"/api/v1/{budget.id}/transactions", json=txn_body(bad))
        assert resp.status_code == 422, f"amount {bad!r} must be rejected, got {resp.status_code}"

    # Sanity: a normal amount still works
    resp = await api_client.post(f"/api/v1/{budget.id}/transactions", json=txn_body("-10.00"))
    assert resp.status_code == 201


async def test_assignment_rejects_nan(api_client, db_session):
    from .factories import create_category, create_category_group

    user = api_client.test_user
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    category = await create_category(db_session, budget, group, "Groceries")

    resp = await api_client.patch(
        f"/api/v1/categories/{category.id}/assignment",
        params={"budget_id": str(budget.id), "month": "2026-07-01"},
        json={"amount": "NaN"},
    )
    assert resp.status_code == 422


async def test_duplicate_scan_sql_pairs(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    payee = await create_payee(db_session, budget, "Coffee Shop")

    a = await create_transaction(
        db_session, budget, account, "-4.50", TODAY - timedelta(days=1), payee=payee
    )
    b = await create_transaction(db_session, budget, account, "-4.50", TODAY, payee=payee)
    # Same amount but far outside the window: not a candidate
    await create_transaction(
        db_session, budget, account, "-4.50", TODAY - timedelta(days=30), payee=payee
    )
    # Different amount: not a candidate
    await create_transaction(db_session, budget, account, "-9.00", TODAY, payee=payee)

    created = await services.matching.scan_for_duplicates(account.id)
    assert created == 1

    matches = await services.match_repo.get_pending_for_account(account.id)
    assert len(matches) == 1
    pair = {matches[0].synced_transaction_id, matches[0].manual_transaction_id}
    assert pair == {a.id, b.id}

    # Idempotent: re-scan creates nothing new
    again = await services.matching.scan_for_duplicates(account.id)
    assert again == 0


async def test_find_similar_deterministic_under_crowding(db_session):
    """Seven same-amount rows crowd the ±3-day window; a LIMIT 5 without an
    ORDER BY would return an arbitrary subset. Nearest-first with a unique
    tiebreak must return the same five rows, nearest first, every time."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    center = TODAY - timedelta(days=10)

    by_delta = {}
    for delta in (0, 1, -1, 2, -2, 3, -3):
        by_delta[delta] = await create_transaction(
            db_session, budget, account, "-9.99", center + timedelta(days=delta)
        )

    first = await services.transaction_repo.find_similar_transactions(
        account.id, Decimal("-9.99"), center
    )
    second = await services.transaction_repo.find_similar_transactions(
        account.id, Decimal("-9.99"), center
    )

    assert [t.id for t in first] == [t.id for t in second], "same query, same answer"
    expected = [by_delta[d].id for d in (0, 1, -1, 2, -2)]
    assert [t.id for t in first] == expected, (
        "nearest date first, future side wins ties; the ±3 rows fall to the LIMIT"
    )
