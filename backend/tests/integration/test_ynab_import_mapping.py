"""YNAB import preview + account-type mapping: the cutover-critical step that
keeps investment/loan accounts from landing on-budget and polluting TBA."""

import io
import uuid
import zipfile
from datetime import date
from decimal import Decimal

from .factories import make_services

REGISTER = """Account,Date,Payee,Category Group,Category,Memo,Outflow,Inflow,Cleared
Checking,07/01/2026,Employer,Inflow,Ready to Assign,,,"2,000.00",Cleared
Checking,07/02/2026,Corner Market,Everyday,Groceries,,60.00,,Cleared
Home Mortgage,07/03/2026,Opening Balance,,,,"250,000.00",,Cleared
Vanguard Brokerage,07/05/2026,Opening Balance,,,,,"10,000.00",Cleared
"""


def _ynab_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("My Budget - Register.csv", REGISTER)
    return buf.getvalue()


async def test_preview_lists_accounts_with_type_suggestions(api_client):
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab/preview",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
    )
    assert resp.status_code == 200
    preview = resp.json()
    assert preview["transaction_count"] == 4

    by_name = {a["name"]: a for a in preview["accounts"]}
    assert set(by_name) == {"Checking", "Home Mortgage", "Vanguard Brokerage"}
    assert by_name["Checking"]["suggested_type"] == "checking"
    assert by_name["Checking"]["suggested_on_budget"] is True
    assert by_name["Home Mortgage"]["suggested_type"] == "mortgage"
    assert by_name["Home Mortgage"]["suggested_on_budget"] is False
    assert by_name["Vanguard Brokerage"]["suggested_type"] == "investment"
    assert by_name["Vanguard Brokerage"]["suggested_on_budget"] is False


async def test_preview_does_not_import_anything(api_client, db_session):
    from sqlalchemy import select

    from igab.db.models import Account, Budget

    await api_client.post(
        "/api/v1/budgets/import-ynab/preview",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
    )
    assert (await db_session.execute(select(Budget))).scalars().all() == []
    assert (await db_session.execute(select(Account))).scalars().all() == []


async def test_import_applies_account_type_mapping(api_client, db_session):
    services = make_services(db_session)

    mapping = (
        '{"Home Mortgage": {"account_type": "mortgage", "on_budget": false},'
        ' "Vanguard Brokerage": {"account_type": "investment", "on_budget": false},'
        ' "Checking": {"account_type": "checking", "on_budget": true}}'
    )
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": "Mapped", "account_types": mapping},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["import_result"]["transactions"] == 4
    budget_id = uuid.UUID(body["budget"]["id"])

    accounts = {a.name: a for a in await services.account_repo.get_all(budget_id)}
    assert accounts["Home Mortgage"].account_type == "mortgage"
    assert accounts["Home Mortgage"].on_budget is False
    assert accounts["Vanguard Brokerage"].account_type == "investment"
    assert accounts["Vanguard Brokerage"].on_budget is False
    assert accounts["Checking"].on_budget is True

    # Classification mirrors must be set on IMPORTED accounts too — the old
    # importer left them NULL, which made off-budget accounts invisible in
    # the sidebar's Assets/Liabilities sections.
    assert accounts["Home Mortgage"].classification == "liability"
    assert accounts["Vanguard Brokerage"].classification == "asset"
    assert accounts["Checking"].classification == "asset"
    assert all(a.account_type_id is not None for a in accounts.values())

    # The point of the exercise: off-budget balances stay out of TBA. With
    # nothing assigned, TBA = income (2000); the -60 spend shows as category
    # overspend. Were the mortgage on-budget, TBA would be about -248,000.
    month = await services.budgets.get_budget_summary(budget_id, date(2026, 7, 1))
    assert month.to_be_assigned == Decimal("2000.00")
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal("1940.00")


async def test_import_rejects_malformed_mapping(api_client):
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": "Bad shape", "account_types": '{"Checking": {"account_type": "checking"}}'},
    )
    assert resp.status_code == 400
    assert "account_types" in resp.json()["detail"]


async def test_import_rejects_unknown_account_type(api_client, db_session):
    from sqlalchemy import select

    from igab.db.models import Budget

    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={
            "name": "Yacht club",
            "account_types": '{"Checking": {"account_type": "yacht", "on_budget": true}}',
        },
    )
    assert resp.status_code == 400
    assert "yacht" in resp.json()["detail"]
    leftover = await db_session.execute(select(Budget).where(Budget.name == "Yacht club"))
    assert leftover.scalar_one_or_none() is None

async def test_budget_creation_flow_preview_and_mapped_import(api_client, db_session):
    """The BudgetSelectorPage flow: preview (no budget yet) → import with
    mapping creates the budget with correctly-typed accounts."""
    from igab.repositories.account_repo import AccountRepository

    resp = await api_client.post(
        "/api/v1/budgets/import-ynab/preview",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
    )
    assert resp.status_code == 200
    assert {a["name"] for a in resp.json()["accounts"]} == {
        "Checking",
        "Home Mortgage",
        "Vanguard Brokerage",
    }

    mapping = (
        '{"Home Mortgage": {"account_type": "mortgage", "on_budget": false},'
        ' "Vanguard Brokerage": {"account_type": "investment", "on_budget": false}}'
    )
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": "From YNAB", "account_types": mapping},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["import_result"]["transactions"] == 4

    account_repo = AccountRepository(db_session)
    accounts = {
        a.name: a for a in await account_repo.get_all(uuid.UUID(body["budget"]["id"]))
    }
    assert accounts["Home Mortgage"].on_budget is False
    assert accounts["Vanguard Brokerage"].account_type == "investment"
    # Unmapped account falls back to on-budget checking
    assert accounts["Checking"].account_type == "checking"
    assert accounts["Checking"].on_budget is True


async def test_budget_creation_rejects_bad_mapping_without_creating_budget(
    api_client, db_session
):
    from sqlalchemy import select

    from igab.db.models import Budget

    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": "Broken", "account_types": "not json"},
    )
    assert resp.status_code == 400

    leftover = await db_session.execute(select(Budget).where(Budget.name == "Broken"))
    assert leftover.scalar_one_or_none() is None, (
        "a rejected import must not leave an empty budget behind"
    )


async def test_import_skips_accounts_marked_skip(api_client, db_session):
    """The archived-account escape hatch: a mapping entry with skip=true keeps
    the account and every one of its rows out of the import entirely."""
    services = make_services(db_session)

    mapping = (
        '{"Home Mortgage": {"account_type": "mortgage", "on_budget": false, "skip": true},'
        ' "Vanguard Brokerage": {"account_type": "investment", "on_budget": false},'
        ' "Checking": {"account_type": "checking", "on_budget": true}}'
    )
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": "Skips archived", "account_types": mapping},
    )
    assert resp.status_code == 201
    body = resp.json()["import_result"]
    assert body["transactions"] == 3
    assert body["accounts"] == 2
    assert body["accounts_skipped"] == 1
    assert body["transactions_excluded"] == 1
    assert body["skipped"] == 0

    budget_id = uuid.UUID(resp.json()["budget"]["id"])
    accounts = {a.name for a in await services.account_repo.get_all(budget_id)}
    assert accounts == {"Checking", "Vanguard Brokerage"}
    # The skipped mortgage held the -250,000 opening balance; nothing of it
    # may leak into the budget's numbers.
    month = await services.budgets.get_budget_summary(budget_id, date(2026, 7, 1))
    assert month.to_be_assigned == Decimal("2000.00")


async def test_budget_creation_flow_respects_skip(api_client, db_session):
    """Same escape hatch on the create-budget-from-export endpoint the
    BudgetSelectorPage actually uses."""
    from igab.repositories.account_repo import AccountRepository

    mapping = '{"Vanguard Brokerage": {"account_type": "investment", "on_budget": false, "skip": true}}'
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": "From YNAB no brokerage", "account_types": mapping},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["import_result"]["accounts_skipped"] == 1
    assert body["import_result"]["transactions_excluded"] == 1

    account_repo = AccountRepository(db_session)
    accounts = {a.name for a in await account_repo.get_all(uuid.UUID(body["budget"]["id"]))}
    assert accounts == {"Checking", "Home Mortgage"}


class TestImportAlwaysMakesANewBudget:
    """Importing an export on top of an existing budget is not offered, and
    must not become offerable.

    The import-id dedupe is keyed on account UUIDs the import itself creates,
    so a second pass over the same export cannot recognise the first pass's
    rows: every transaction would import again and every balance would double.
    The route creating its own budget is what makes that unreachable.
    """

    async def test_the_only_import_route_creates_a_budget(self, api_client):
        before = (await api_client.get("/api/v1/budgets")).json()
        resp = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("export.zip", _ynab_zip(), "application/zip")},
            data={"name": "Imported"},
        )
        assert resp.status_code == 201
        after = (await api_client.get("/api/v1/budgets")).json()
        assert len(after) == len(before) + 1
        assert resp.json()["budget"]["id"] not in {b["id"] for b in before}

    async def test_reusing_a_budget_name_is_refused(self, api_client):
        first = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("export.zip", _ynab_zip(), "application/zip")},
            data={"name": "Imported"},
        )
        assert first.status_code == 201
        again = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("export.zip", _ynab_zip(), "application/zip")},
            data={"name": "Imported"},
        )
        assert again.status_code == 409
        assert "already exists" in again.json()["detail"]
