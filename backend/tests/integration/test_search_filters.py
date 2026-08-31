"""Direction and transfer filters on both transaction listings.

These back the register's `is:inflow` / `is:outflow` / `is:transfer` search
tokens: the per-account listing filters on the row's own sign, and both
listings filter transfers by transfer_id presence.
"""

from datetime import date, timedelta

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)

TODAY = date.today()


async def _setup(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")

    spend = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, category=groceries
    )
    income = await create_transaction(
        db_session, budget, checking, "200.00", TODAY - timedelta(days=1)
    )
    # transfer_id is a self-referencing FK: each side points at its counterpart
    transfer_out = await create_transaction(db_session, budget, checking, "-25.00", TODAY)
    transfer_in = await create_transaction(
        db_session, budget, savings, "25.00", TODAY, transfer_id=transfer_out.id
    )
    transfer_out.transfer_id = transfer_in.id
    await db_session.flush()
    return budget, checking, savings, spend, income, transfer_out, transfer_in


async def _fetch_account(api_client, account_id, **params):
    resp = await api_client.get(f"/api/v1/accounts/{account_id}/transactions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _fetch_budget(api_client, budget_id, **params):
    resp = await api_client.get(f"/api/v1/{budget_id}/transactions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["transactions"]


def _ids(rows):
    return {r["id"] for r in rows}


async def test_account_direction_outflow(api_client, db_session):
    _, checking, _, spend, _, transfer_out, _ = await _setup(api_client, db_session)
    rows = await _fetch_account(api_client, checking.id, direction="outflow")
    assert _ids(rows) == {str(spend.id), str(transfer_out.id)}


async def test_account_direction_inflow(api_client, db_session):
    _, checking, _, _, income, _, _ = await _setup(api_client, db_session)
    rows = await _fetch_account(api_client, checking.id, direction="inflow")
    assert _ids(rows) == {str(income.id)}


async def test_account_is_transfer(api_client, db_session):
    _, checking, _, spend, income, transfer_out, _ = await _setup(api_client, db_session)
    only_transfers = await _fetch_account(api_client, checking.id, is_transfer="true")
    assert _ids(only_transfers) == {str(transfer_out.id)}
    no_transfers = await _fetch_account(api_client, checking.id, is_transfer="false")
    assert _ids(no_transfers) == {str(spend.id), str(income.id)}


async def test_account_direction_and_transfer_combine(api_client, db_session):
    _, checking, _, spend, _, _, _ = await _setup(api_client, db_session)
    rows = await _fetch_account(api_client, checking.id, direction="outflow", is_transfer="false")
    assert _ids(rows) == {str(spend.id)}


async def test_budget_is_transfer(api_client, db_session):
    budget, _, _, spend, income, transfer_out, transfer_in = await _setup(api_client, db_session)
    only_transfers = await _fetch_budget(api_client, budget.id, is_transfer="true")
    assert _ids(only_transfers) == {str(transfer_out.id), str(transfer_in.id)}
    no_transfers = await _fetch_budget(api_client, budget.id, is_transfer="false")
    assert _ids(no_transfers) == {str(spend.id), str(income.id)}


async def test_budget_direction_and_transfer_combine(api_client, db_session):
    budget, _, _, _, _, _, transfer_in = await _setup(api_client, db_session)
    rows = await _fetch_budget(api_client, budget.id, direction="inflow", is_transfer="true")
    assert _ids(rows) == {str(transfer_in.id)}
