"""The two register URLs list the same rows in the same order.

`GET /accounts/{id}/transactions` used to be its own listing: a copy of
`build_where`'s clause and the ladder's ORDER BY, and the copy had drifted —
it read `payee_ids` by truthiness, so a scope naming no payees listed every
row. It is now a view of `GET /{budget_id}/transactions` with `account_ids`,
which the register itself reads. API keys may still call the old URL, so this
holds the two to one answer for every filter the register sends
(`transactionFilterParams` in frontend/src/api/transactions.ts).
"""

from datetime import date, timedelta

import pytest

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
)

TODAY = date.today()


@pytest.fixture
async def ledger(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    market = await create_payee(db_session, budget, "Cascade Market")
    cafe = await create_payee(db_session, budget, "Nordwind Cafe")

    async def row(days_ago, amount, **kw):
        await create_transaction(
            db_session, budget, checking, amount, TODAY - timedelta(days=days_ago), **kw
        )

    await row(1, "-12.34", category=groceries, payee=market, cleared="uncleared")
    await row(2, "-45.00", category=dining, payee=cafe, memo="team lunch")
    await row(3, "1200.00", category=groceries, payee=market, cleared="reconciled")
    await row(4, "-8.50", payee=cafe, approved=False)
    await row(5, "-60.00", category=dining, cleared="pending")
    await row(6, "-30.00", category=groceries, approved=False, cleared="reconciled")
    await create_transfer(db_session, budget, checking, savings, "-200.00", TODAY)
    # A row on the other account: the scope must keep it out of both.
    await create_transaction(
        db_session, budget, savings, "-5.00", TODAY, category=groceries, payee=market
    )
    await db_session.flush()
    return budget, checking, {"groceries": groceries, "market": market}


#: Every filter the register sends, by name. Each entry builds its params from
#: the fixture's ids so the names can be listed before any row exists.
FILTERS = {
    "none": lambda ids: {},
    "search": lambda ids: {"search": "lunch"},
    "amount search": lambda ids: {"search": "12.3"},
    "cleared": lambda ids: {"cleared": "reconciled"},
    "exclude_cleared": lambda ids: {"exclude_cleared": "reconciled"},
    "unreconciled": lambda ids: {"unreconciled": True},
    "uncategorized": lambda ids: {"uncategorized": True},
    "unapproved": lambda ids: {"unapproved": True},
    "either, or-mode": lambda ids: {"uncategorized": True, "unapproved": True, "is_or_mode": True},
    "both, and-mode": lambda ids: {"uncategorized": True, "unapproved": True},
    "category": lambda ids: {"category_ids": str(ids["groceries"].id)},
    "payee": lambda ids: {"payee_ids": str(ids["market"].id)},
    "amount range": lambda ids: {"amount_min": 10, "amount_max": 100},
    "no attachment": lambda ids: {"has_attachment": False},
    "dates": lambda ids: {
        "start_date": (TODAY - timedelta(days=4)).isoformat(),
        "end_date": (TODAY - timedelta(days=2)).isoformat(),
    },
    "inflow": lambda ids: {"direction": "inflow"},
    "outflow": lambda ids: {"direction": "outflow"},
    "transfers": lambda ids: {"is_transfer": True},
    "not transfers": lambda ids: {"is_transfer": False},
    "unpaired transfers": lambda ids: {"unpaired_transfers": True},
    "a page": lambda ids: {"limit": 3, "offset": 2},
}


@pytest.mark.parametrize("name", list(FILTERS))
async def test_both_urls_list_the_same_rows_in_the_same_order(api_client, ledger, name):
    budget, checking, ids = ledger
    params = {"limit": 100, **FILTERS[name](ids)}

    by_account = await api_client.get(f"/api/v1/accounts/{checking.id}/transactions", params=params)
    by_budget = await api_client.get(
        f"/api/v1/{budget.id}/transactions",
        params={**params, "account_ids": str(checking.id), "order": "register"},
    )
    assert by_account.status_code == by_budget.status_code == 200
    assert [t["id"] for t in by_account.json()] == [
        t["id"] for t in by_budget.json()["transactions"]
    ]


async def test_a_payee_scope_naming_nobody_lists_nothing(api_client, ledger):
    """The drift the convergence removed: `payee_ids=","` parses to an empty
    scope, and the account listing read it by truthiness as no scope at all."""
    _, checking, _ = ledger
    resp = await api_client.get(
        f"/api/v1/accounts/{checking.id}/transactions", params={"payee_ids": ","}
    )
    assert resp.status_code == 200
    assert resp.json() == []
