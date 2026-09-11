"""Export report: a raw parent-row dump of the ledger.

Pins the contract: parent rows only (split children collapse into their
parent), deleted rows absent, pending rows PRESENT (the export carries a
`cleared` column so consumers can filter), boundaries inclusive, newest first.
"""

import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal

from igab.services.report_service import ReportService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
    money,
)

TODAY = date.today()


async def _setup_with_mixed_rows(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    gas = await create_category(db_session, budget, group, "Gas")

    # In range: cleared expense on the start boundary
    cleared = await create_transaction(
        db_session, budget, checking, "-100.00", TODAY - timedelta(days=3), category=groceries
    )
    # In range: pending inflow — exported with cleared="pending"
    pending = await create_transaction(
        db_session, budget, checking, "50.00", TODAY - timedelta(days=2), cleared="pending"
    )
    # In range but deleted — never exported
    await create_transaction(
        db_session, budget, checking, "-20.00", TODAY - timedelta(days=2), is_deleted=True
    )
    # In range: split — only the parent row exports, at its full amount
    header = TransactionCreate(
        account_id=checking.id,
        date=TODAY - timedelta(days=1),
        amount=Decimal("-100.00"),
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=1),
            amount=Decimal("-60.00"),
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=1),
            amount=Decimal("-40.00"),
            category_id=gas.id,
        ),
    ]
    parent = await services.transactions.create_split(budget.id, header, splits)
    # Out of range: before the start date
    await create_transaction(db_session, budget, checking, "-5.00", TODAY - timedelta(days=10))

    return budget, cleared, pending, parent


async def test_csv_exports_parent_rows_newest_first(db_session):
    budget, cleared, pending, parent = await _setup_with_mixed_rows(db_session)
    reports = ReportService(db_session)

    content, content_type = await reports.export_transactions(
        budget.id, TODAY - timedelta(days=3), TODAY, "csv"
    )

    assert content_type == "text/csv"
    rows = list(csv.DictReader(io.StringIO(content)))
    assert [r["id"] for r in rows] == [str(parent.id), str(pending.id), str(cleared.id)]
    by_id = {r["id"]: r for r in rows}
    # Split parent exports its full amount; children are absent entirely
    assert Decimal(by_id[str(parent.id)]["amount"]) == Decimal("-100.00")
    assert Decimal(by_id[str(cleared.id)]["amount"]) == Decimal("-100.00")
    assert Decimal(by_id[str(pending.id)]["amount"]) == Decimal("50.00")
    assert by_id[str(pending.id)]["cleared"] == "pending"


async def test_json_exports_same_rows_with_iso_dates(db_session):
    budget, cleared, pending, parent = await _setup_with_mixed_rows(db_session)
    reports = ReportService(db_session)

    content, content_type = await reports.export_transactions(
        budget.id, TODAY - timedelta(days=3), TODAY, "json"
    )

    assert content_type == "application/json"
    data = json.loads(content)
    assert [r["id"] for r in data] == [str(parent.id), str(pending.id), str(cleared.id)]
    assert data[0]["date"] == (TODAY - timedelta(days=1)).isoformat()
    # Amounts serialize as exact decimal strings, not floats
    assert money(data[0]["amount"]) == Decimal("-100.00")
    assert data[1]["cleared"] == "pending"


async def test_empty_budget_exports_empty_payloads(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    reports = ReportService(db_session)

    csv_content, _ = await reports.export_transactions(budget.id, None, None, "csv")
    assert csv_content.strip() == "id,date,amount,memo,cleared,approved"

    json_content, _ = await reports.export_transactions(budget.id, None, None, "json")
    assert json.loads(json_content) == []


async def test_amounts_are_written_the_way_every_other_export_writes_them(db_session):
    """`str(Decimal)` wrote the column's stored scale, NUMERIC(12,4), so this
    file said "-100.0000" where the YNAB export, the budget export and
    `parse_csv_amount` — the exact inverse of `format_csv_amount` — all speak
    in two decimals. One money formatter, so a file this app writes is a file
    this app can read back.
    """
    budget, cleared, _pending, _parent = await _setup_with_mixed_rows(db_session)
    reports = ReportService(db_session)

    content, _ = await reports.export_transactions(
        budget.id, TODAY - timedelta(days=3), TODAY, "csv"
    )

    row = next(r for r in csv.DictReader(io.StringIO(content)) if r["id"] == str(cleared.id))
    assert row["amount"] == "-100.00"

    # The JSON export reads the same column, so it says the same thing.
    payload, _ = await reports.export_transactions(
        budget.id, TODAY - timedelta(days=3), TODAY, "json"
    )
    assert next(r for r in json.loads(payload) if r["id"] == str(cleared.id))["amount"] == "-100.00"


async def test_a_sub_cent_amount_exports_whole(db_session):
    """Amounts are stored to four places. The export rounded every one to
    cents, so a -12.345 row wrote -12.34 in both formats: the column stopped
    summing to the account and the file no longer read back as the ledger.
    Whole cents still write two places; a sub-cent amount writes itself."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    odd = await create_transaction(db_session, budget, checking, "-12.345", TODAY)
    reports = ReportService(db_session)

    content, _ = await reports.export_transactions(budget.id, TODAY, TODAY, "csv")
    payload, _ = await reports.export_transactions(budget.id, TODAY, TODAY, "json")

    row = next(r for r in csv.DictReader(io.StringIO(content)) if r["id"] == str(odd.id))
    assert row["amount"] == "-12.345"
    assert next(r for r in json.loads(payload) if r["id"] == str(odd.id))["amount"] == "-12.345"
