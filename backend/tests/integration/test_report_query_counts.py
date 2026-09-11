"""Reports must not ask per month, or fetch the register to draw a summary.

Category history called `get_category_balance` inside a loop — two queries a
month — so a twelve-month chart issued two dozen round-trips for two lookups'
worth of data, and asking for 24 months doubled it. Net worth history
re-filtered and re-grouped the WHOLE register once per point, then fetched
every parent row to draw twelve points; the Overview pulled every posted row
into Python to draw eleven numbers. Each cost grew with the window or the
register for no new data.

Counted with `statement_counts.py`, the same counter the accounts listing
uses: statements for a per-month query, rows returned for a register fetched
whole.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.db.models import ImportAnchor
from igab.domain.dates import add_months

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    make_services,
)
from .statement_counts import count_request

TODAY = date.today()
THIS = TODAY.replace(day=1)


async def _count_selects(api_client, db_session, path: str, params: dict) -> int:
    return (await count_request(api_client, db_session, path, params)).selects


async def _envelope(db_session, budget) -> uuid.UUID:
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    # Eighteen months of history, so a short window and a long one differ in
    # months asked for and not in rows available.
    for i in range(18):
        month = add_months(THIS, -i)
        await create_budget_assignment(db_session, budget, groceries, month, "200.00")
        await create_transaction(
            db_session, budget, checking, "-150.00", month + timedelta(days=3), category=groceries
        )
    await db_session.flush()
    return groceries.id


class TestCategoryHistoryDoesNotAskPerMonth:
    async def test_query_count_is_flat_as_the_window_grows(self, api_client, db_session):
        """Three months and fifteen must cost the same number of SELECTs.

        The absolute number is not the contract — auth and budget-access
        lookups are in it and may legitimately change. That it does not GROW
        with the month count is.
        """
        budget = await create_budget(db_session, api_client.test_user)
        category_id = await _envelope(db_session, budget)
        path = f"/api/v1/{budget.id}/reports/category-history"

        short = await _count_selects(
            api_client, db_session, path, {"category_id": str(category_id), "months": 3}
        )
        long = await _count_selects(
            api_client, db_session, path, {"category_id": str(category_id), "months": 15}
        )

        assert long == short, (
            f"{short} SELECTs for 3 months, {long} for 15 — the report is asking per month again"
        )

    async def test_the_batched_history_is_the_budget_pages_own_figure(self, db_session, api_client):
        """Batching must not change any answer, only the statement count.

        Both assemblies of one figure, compared across an OVERSPENT month —
        the zero floor between months is what a running total gets wrong, and
        it is the difference a second implementation would show first.
        """
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        months = [add_months(THIS, -i) for i in range(3, -1, -1)]
        # Month two spends 300 against 200 assigned plus 50 carried in, so it
        # ends at -50 — and month three is handed ZERO, not -50.
        plan = [("200.00", "-150.00"), ("200.00", "-300.00"), ("200.00", "-50.00"), ("0", "0")]
        for month, (assigned, spent) in zip(months, plan, strict=True):
            await create_budget_assignment(db_session, budget, groceries, month, assigned)
            if spent != "0":
                await create_transaction(
                    db_session,
                    budget,
                    checking,
                    spent,
                    month + timedelta(days=3),
                    category=groceries,
                )
        await db_session.flush()

        budgets = make_services(db_session).budgets
        batched = await budgets.category_history(groceries.id, months)
        one_by_one = [await budgets.get_category_balance(groceries.id, m) for m in months]

        assert [(b.month, b.assigned, b.activity, b.available) for b in batched] == [
            (b.month, b.assigned, b.activity, b.available) for b in one_by_one
        ]
        # And the figures themselves, on paper: 200 − 150 = 50 carried in,
        # then 250 − 300 = −50, which the next month does NOT inherit —
        # 0 + 200 − 50 = 150, held to the month after.
        assert [b.available for b in batched] == [
            Decimal(v) for v in ("50.00", "-50.00", "150.00", "150.00")
        ]

    async def test_an_anchored_budget_walks_from_the_anchor(self, db_session, api_client):
        """YNAB-imported budgets start the walk from the import anchor, and the
        differential above builds an unanchored budget — `opening` is None on
        both sides, so losing the seed in the batched path passed. Here the
        category is anchored at 120 two months before its first activity.
        """
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        anchor_month = add_months(THIS, -3)
        db_session.add(
            ImportAnchor(
                budget_id=budget.id,
                month=anchor_month,
                kind="available",
                category_id=groceries.id,
                amount=Decimal("120.00"),
            )
        )
        after = [add_months(THIS, -2), add_months(THIS, -1)]
        for month, assigned, spent in zip(
            after, ("100.00", "50.00"), ("-80.00", "-30.00"), strict=True
        ):
            await create_budget_assignment(db_session, budget, groceries, month, assigned)
            await create_transaction(
                db_session, budget, checking, spent, month + timedelta(days=3), category=groceries
            )
        await db_session.flush()

        months = [add_months(THIS, -4), anchor_month, *after]
        budgets = make_services(db_session).budgets
        batched = await budgets.category_history(groceries.id, months)
        one_by_one = [await budgets.get_category_balance(groceries.id, m) for m in months]

        assert [(b.month, b.available) for b in batched] == [
            (b.month, b.available) for b in one_by_one
        ]
        # The anchor month reads the anchor; then 120 + 100 − 80 = 140, and
        # 140 + 50 − 30 = 160. Walked from zero these would read 20 and 40.
        assert [b.available for b in batched[1:]] == [
            Decimal(v) for v in ("120.00", "140.00", "160.00")
        ]


class TestNetWorthHistoryDoesNotRescanPerMonth:
    """Its per-month cost was a polars re-scan, which a statement count cannot
    see; the rows-fetched ratchet below can. This one keeps the batching from
    being undone with a query per month instead."""

    async def test_query_count_is_flat_as_the_window_grows(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        await _envelope(db_session, budget)
        path = f"/api/v1/{budget.id}/reports/net-worth"

        short = await _count_selects(api_client, db_session, path, {"months": 3})
        long = await _count_selects(api_client, db_session, path, {"months": 15})

        assert long == short, (
            f"{short} SELECTs for 3 months, {long} for 15 — the report is asking per month again"
        )


class TestTheRegisterIsNotFetchedWhole:
    """Neither the Overview's narrowing nor net worth's single statement had
    a test that failed if the old whole-register fetch came back: it is one
    wide SELECT, so the statement count never moved. The rows it returns do —
    history outside every window the page draws must not change them."""

    @pytest.mark.parametrize(
        ("report", "params"), [("dashboard", {}), ("net-worth", {"months": 3})]
    )
    async def test_rows_fetched_do_not_grow_with_old_history(
        self, api_client, db_session, report, params
    ):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        # Two years back: outside the window, its comparison period and the
        # 90-day burn, on the account and envelope already read. One row is
        # there from the start — the balance before the first cutoff is one
        # group of the balance sheet, however many rows make it up.
        long_ago = add_months(THIS, -24)
        await create_transaction(db_session, budget, checking, "900.00", long_ago)
        for i in range(10):
            await create_transaction(
                db_session, budget, checking, "-5.00", TODAY - timedelta(days=i), category=groceries
            )
        await db_session.flush()
        path = f"/api/v1/{budget.id}/reports/{report}"
        await count_request(api_client, db_session, path, params)  # warm any one-time lookups

        before = await count_request(api_client, db_session, path, params)
        for i in range(200):
            await create_transaction(
                db_session,
                budget,
                checking,
                "-1.00",
                long_ago + timedelta(days=i % 28),
                category=groceries,
            )
        await db_session.flush()
        after = await count_request(api_client, db_session, path, params)

        assert after.selects == before.selects
        assert after.rows_fetched == before.rows_fetched, (
            f"{before.rows_fetched} rows before 200 old ones were added, "
            f"{after.rows_fetched} after — {report} is fetching the register again"
        )
