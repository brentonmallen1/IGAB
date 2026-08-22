"""Every report, over HTTP, against data built from the inputs that broke them.

The suite's blind spot was never a missing assertion on a happy path — it was
that no fixture contained a payee-less row, a NULL classification, a negative
inflow, an uncategorized transfer out of the budget, or a split with a
savings-tagged leg. Each report was correct on the data it was shown.

So this walks every report endpoint over one deliberately awkward budget and
demands a 200. It is a smoke test on purpose: the arithmetic belongs in the
per-report suites, and what belongs here is "no report falls over, and none of
them silently returns nothing when there is data".
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.repositories.tag_repo import TagRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
    create_transaction,
)
from .invariants import assert_financial_invariants

TODAY = date.today()
MONTH_START = TODAY.replace(day=1)
WINDOW = {"start_date": (TODAY - timedelta(days=60)).isoformat(), "end_date": TODAY.isoformat()}


async def _awkward_budget(db_session, owner):
    """One budget holding every input that has broken a report."""
    budget = await create_budget(db_session, owner)

    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    loan = await create_account(
        db_session, budget, "Car Loan", account_type="loan", on_budget=False
    )
    legacy = await create_account(
        db_session, budget, "Legacy Holdings", account_type="investment", on_budget=False
    )

    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    rta = await create_category(db_session, budget, inflow, "Ready to Assign")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    fund = await create_category(db_session, budget, everyday, "Car Replacement")

    repo = TagRepository(db_session)
    tags = {t.system_key: t for t in await repo.list_for_budget(budget.id)}
    tag = tags.get("savings") or await create_tag(
        db_session, budget, "savings", system_key="savings"
    )
    await repo.set_category_tags(fund.id, [tag.id])

    # A transfer payee exists, which is what turned the NULL-payee bug on.
    to_brokerage = await create_payee(
        db_session, budget, "Transfer : Brokerage", transfer_account_id=brokerage.id
    )

    # Income, and a reversal of it.
    await create_transaction(db_session, budget, checking, "5000.00", TODAY, category=rta)
    await create_transaction(db_session, budget, checking, "-500.00", TODAY, category=rta)
    # Payee-less, category-less ordinary rows.
    await create_transaction(db_session, budget, checking, "-40.00", TODAY)
    await create_transaction(db_session, budget, checking, "120.00", TODAY)
    # Ordinary spending, with a payee.
    shop = await create_payee(db_session, budget, "Corner Shop")
    await create_transaction(
        db_session, budget, checking, "-85.00", TODAY, category=groceries, payee=shop
    )
    # Uncategorized transfer out of the budget, linked.
    out = await create_transaction(db_session, budget, checking, "-1000.00", TODAY)
    into = await create_transaction(db_session, budget, brokerage, "1000.00", TODAY)
    out.transfer_id, into.transfer_id = into.id, out.id
    # Orphaned leg: transfer payee, no partner.
    await create_transaction(db_session, budget, checking, "-250.00", TODAY, payee=to_brokerage)
    # Categorized transfer to a tracked debt.
    await create_transaction(db_session, budget, checking, "-275.00", TODAY, category=groceries)
    loan_out = await create_transaction(db_session, budget, checking, "-300.00", TODAY)
    loan_in = await create_transaction(db_session, budget, loan, "300.00", TODAY)
    loan_out.transfer_id, loan_in.transfer_id = loan_in.id, loan_out.id
    # Activity inside tracked accounts, including the unclassified one. The
    # negative categorized one matters: a spending report scoped to a tracked
    # account has nothing to show without it.
    await create_transaction(db_session, budget, brokerage, "125.00", TODAY)
    await create_transaction(db_session, budget, brokerage, "-50.00", TODAY, category=groceries)
    await create_transaction(db_session, budget, loan, "-40.00", TODAY)
    await create_transaction(db_session, budget, legacy, "80.00", TODAY)
    # A split with a savings-tagged leg.
    parent = await create_transaction(
        db_session, budget, checking, "-300.00", TODAY, payee=shop, is_split=True
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-100.00",
        TODAY,
        category=groceries,
        parent_transaction_id=parent.id,
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-200.00",
        TODAY,
        category=fund,
        parent_transaction_id=parent.id,
    )
    await db_session.flush()
    return budget, checking, brokerage


#: (path, extra params). Window params are added for the ones that take them.
REPORTS: list[tuple[str, dict]] = [
    ("reports/dashboard", WINDOW),
    ("reports/spending", WINDOW),
    ("reports/spending-grouped", WINDOW),
    ("reports/income-expense", {"months": 3}),
    ("reports/net-worth", {"months": 3}),
    ("reports/account-composition", {"months": 3}),
    ("reports/burn-rate", {"months": 3}),
    ("reports/cash-flow", WINDOW),
    ("reports/budget-actual", WINDOW),
    ("reports/variance", {"months": 3}),
    ("reports/volatility", {"months": 3}),
    ("reports/seasonality", {"months": 3}),
    ("reports/payee-analysis", WINDOW),
    ("reports/day-patterns", WINDOW),
    ("reports/large-transactions", WINDOW),
    ("reports/liabilities", {}),
    ("reports/subscriptions", {"months": 3}),
    ("reports/savings", {"months": 3}),
    ("reports/savings-rate", {"months": 3}),
    ("reports/anomalies", {"months": 3}),
    ("reports/plan-vs-reality", {"months": 3}),
]


@pytest.mark.parametrize("path,params", REPORTS, ids=[r[0] for r in REPORTS])
async def test_every_report_survives(api_client, db_session, path, params):
    budget, _, _ = await _awkward_budget(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/{path}", params=params)

    assert resp.status_code == 200, resp.text


class TestScopedRequests:
    """An explicit account or view selection overrides the on-budget default,
    which is where the class filter used to cancel the user's choice."""

    @pytest.mark.parametrize(
        "path", ["reports/spending", "reports/spending-grouped", "reports/day-patterns"]
    )
    async def test_a_tracked_account_selection_returns_its_activity(
        self, api_client, db_session, path
    ):
        budget, _, brokerage = await _awkward_budget(db_session, api_client.test_user)

        resp = await api_client.get(
            f"/api/v1/{budget.id}/{path}",
            params={**WINDOW, "account_ids": str(brokerage.id)},
        )

        assert resp.status_code == 200
        body = resp.json()
        rows = body.get("categories") or body.get("groups") or body.get("days") or []
        assert rows, "selecting a tracked account must not return an empty report"

    async def test_spending_grouped_under_a_view(self, api_client, db_session):
        budget, _, _ = await _awkward_budget(db_session, api_client.test_user)
        view = (
            await api_client.post(
                f"/api/v1/{budget.id}/views", json={"name": "Lens", "groups": ["Need"]}
            )
        ).json()

        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-grouped",
            params={**WINDOW, "view_id": view["id"]},
        )

        assert resp.status_code == 200
        assert Decimal(resp.json()["total"]) > 0


class TestInvariantsHoldOnAwkwardData:
    async def test_the_partition_survives_every_shape(self, api_client, db_session):
        """The invariant that passed on all four classification bugs, now run
        against a fixture that actually contains their inputs."""
        budget, _, _ = await _awkward_budget(db_session, api_client.test_user)
        await assert_financial_invariants(db_session, budget.id)
