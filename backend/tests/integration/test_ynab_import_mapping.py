"""YNAB import preview + account-type mapping: the cutover-critical step that
keeps tracking/loan accounts from landing on-budget and polluting TBA."""

import io
import uuid
import zipfile
from datetime import date
from decimal import Decimal

from .factories import create_budget, make_services

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


async def test_preview_lists_accounts_with_type_suggestions(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.post(
        f"/api/v1/{budget.id}/import/ynab/preview",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
    )
    assert resp.status_code == 200
    preview = resp.json()
    assert preview["transaction_count"] == 4

    by_name = {a["name"]: a for a in preview["accounts"]}
    assert set(by_name) == {"Checking", "Home Mortgage", "Vanguard Brokerage"}
    assert by_name["Checking"]["suggested_type"] == "checking"
    assert by_name["Checking"]["suggested_on_budget"] is True
    assert by_name["Home Mortgage"]["suggested_type"] == "loan"
    assert by_name["Home Mortgage"]["suggested_on_budget"] is False
    assert by_name["Vanguard Brokerage"]["suggested_type"] == "tracking"
    assert by_name["Vanguard Brokerage"]["suggested_on_budget"] is False


async def test_preview_does_not_import_anything(api_client, db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)

    await api_client.post(
        f"/api/v1/{budget.id}/import/ynab/preview",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
    )
    assert await services.account_repo.get_all(budget.id) == []


async def test_import_applies_account_type_mapping(api_client, db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)

    mapping = (
        '{"Home Mortgage": {"account_type": "loan", "on_budget": false},'
        ' "Vanguard Brokerage": {"account_type": "tracking", "on_budget": false},'
        ' "Checking": {"account_type": "checking", "on_budget": true}}'
    )
    resp = await api_client.post(
        f"/api/v1/{budget.id}/import/ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"account_types": mapping},
    )
    assert resp.status_code == 200
    assert resp.json()["transactions"] == 4

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    assert accounts["Home Mortgage"].account_type == "loan"
    assert accounts["Home Mortgage"].on_budget is False
    assert accounts["Vanguard Brokerage"].account_type == "tracking"
    assert accounts["Vanguard Brokerage"].on_budget is False
    assert accounts["Checking"].on_budget is True

    # The point of the exercise: off-budget balances stay out of TBA. With
    # nothing assigned, TBA = income (2000); the -60 spend shows as category
    # overspend. Were the mortgage on-budget, TBA would be about -248,000.
    month = await services.budgets.get_budget_summary(budget.id, date(2026, 7, 1))
    assert month.to_be_assigned == Decimal("2000.00")
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal("1940.00")


async def test_import_rejects_malformed_mapping(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.post(
        f"/api/v1/{budget.id}/import/ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"account_types": '{"Checking": {"account_type": "yacht"}}'},
    )
    assert resp.status_code == 400
    assert "account_types" in resp.json()["detail"]

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
        '{"Home Mortgage": {"account_type": "loan", "on_budget": false},'
        ' "Vanguard Brokerage": {"account_type": "tracking", "on_budget": false}}'
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
    assert accounts["Vanguard Brokerage"].account_type == "tracking"
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
    budget = await create_budget(db_session, api_client.test_user)

    mapping = (
        '{"Home Mortgage": {"account_type": "loan", "on_budget": false, "skip": true},'
        ' "Vanguard Brokerage": {"account_type": "tracking", "on_budget": false},'
        ' "Checking": {"account_type": "checking", "on_budget": true}}'
    )
    resp = await api_client.post(
        f"/api/v1/{budget.id}/import/ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"account_types": mapping},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transactions"] == 3
    assert body["accounts"] == 2
    assert body["accounts_skipped"] == 1
    assert body["transactions_excluded"] == 1
    assert body["skipped"] == 0

    accounts = {a.name for a in await services.account_repo.get_all(budget.id)}
    assert accounts == {"Checking", "Vanguard Brokerage"}
    # The skipped mortgage held the -250,000 opening balance; nothing of it
    # may leak into the budget's numbers.
    month = await services.budgets.get_budget_summary(budget.id, date(2026, 7, 1))
    assert month.to_be_assigned == Decimal("2000.00")


async def test_budget_creation_flow_respects_skip(api_client, db_session):
    """Same escape hatch on the create-budget-from-export endpoint the
    BudgetSelectorPage actually uses."""
    from igab.repositories.account_repo import AccountRepository

    mapping = '{"Vanguard Brokerage": {"account_type": "tracking", "on_budget": false, "skip": true}}'
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
