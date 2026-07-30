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
    assert Decimal(data[0]["amount"]) == Decimal("-100.00")
    assert data[1]["cleared"] == "pending"


async def test_empty_budget_exports_empty_payloads(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    reports = ReportService(db_session)

    csv_content, _ = await reports.export_transactions(budget.id, None, None, "csv")
    assert csv_content.strip() == "id,date,amount,memo,cleared,approved"

    json_content, _ = await reports.export_transactions(budget.id, None, None, "json")
    assert json.loads(json_content) == []
