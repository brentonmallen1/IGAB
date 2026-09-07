"""Two figures the register and the report toolbar had no way to state.

**Pending total.** Pending rows are visible in the register and counted in
none of the account's balances — an auth hold is provisional, so the money
moves exactly once, at posting (`txn_filters.POSTED`). That is deliberate, and
it is why the total has to be reported separately: without it the register
shows rows that add up to nothing anywhere.

**Report range.** The month picker offered 6/12/24 and the plan-vs-reality
endpoint refused anything over 24. Reports now say how far back they can look,
so the picker offers only windows the budget can fill.
"""

from datetime import date, timedelta
from decimal import Decimal as D

from igab.domain.dates import months_spanned

from .factories import (
    add_budget_member,
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)


async def _budget(db_session, api_client):
    budget = await create_budget(db_session, await create_user(db_session))
    await add_budget_member(db_session, budget, api_client.test_user, role="owner")
    account = await create_account(db_session, budget, "Harborstone Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    category = await create_category(db_session, budget, group, "Groceries")
    return budget, account, category


async def _account(api_client, budget, account):
    r = await api_client.get(f"/api/v1/accounts/{account.id}", params={"budget_id": str(budget.id)})
    assert r.status_code == 200, r.text
    return r.json()


class TestPendingBalance:
    async def test_sums_the_pending_rows(self, db_session, api_client):
        budget, account, category = await _budget(db_session, api_client)
        for amount in ("-25.00", "-15.50"):
            await create_transaction(
                db_session,
                budget,
                account,
                amount,
                date.today(),
                category=category,
                cleared="pending",
            )
        await db_session.commit()

        body = await _account(api_client, budget, account)
        assert D(str(body["pending_balance"])) == D("-40.50")

    async def test_stays_out_of_the_balance_partition(self, db_session, api_client):
        """The figure exists precisely because it is in none of the other three.

        If pending ever started counting toward the working balance this would
        fail — and silently double-counting a provisional auth hold is the
        exact bug POSTED was introduced to prevent.
        """
        budget, account, category = await _budget(db_session, api_client)
        await create_transaction(
            db_session,
            budget,
            account,
            "-100.00",
            date.today(),
            category=category,
            cleared="cleared",
        )
        await create_transaction(
            db_session,
            budget,
            account,
            "-30.00",
            date.today(),
            category=category,
            cleared="pending",
        )
        await db_session.commit()

        body = await _account(api_client, budget, account)
        assert D(str(body["cleared_balance"])) == D("-100.00")
        assert D(str(body["balance"])) == D("-100.00")
        assert D(str(body["uncleared_balance"])) == D("0")
        assert D(str(body["pending_balance"])) == D("-30.00")

    async def test_is_zero_with_nothing_pending(self, db_session, api_client):
        budget, account, category = await _budget(db_session, api_client)
        await create_transaction(
            db_session, budget, account, "-10.00", date.today(), category=category
        )
        await db_session.commit()
        assert D(str((await _account(api_client, budget, account))["pending_balance"])) == D("0")

    async def test_the_listing_agrees_with_the_detail(self, db_session, api_client):
        """Two endpoints, one figure — the listing computes it with a grouped
        aggregate and the detail with a single-account one."""
        budget, account, category = await _budget(db_session, api_client)
        await create_transaction(
            db_session,
            budget,
            account,
            "-42.00",
            date.today(),
            category=category,
            cleared="pending",
        )
        await db_session.commit()

        listing = await api_client.get(f"/api/v1/{budget.id}/accounts")
        assert listing.status_code == 200, listing.text
        row = next(a for a in listing.json() if a["id"] == str(account.id))
        detail = await _account(api_client, budget, account)
        assert row["pending_balance"] == detail["pending_balance"]
        assert D(str(row["pending_balance"])) == D("-42.00")


class TestReportRange:
    async def test_reports_how_far_back_the_budget_goes(self, db_session, api_client):
        budget, account, category = await _budget(db_session, api_client)
        oldest = date.today() - timedelta(days=400)
        await create_transaction(db_session, budget, account, "-5.00", oldest, category=category)
        await create_transaction(
            db_session, budget, account, "-5.00", date.today(), category=category
        )
        await db_session.commit()

        r = await api_client.get(f"/api/v1/{budget.id}/reports/range")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["earliest_month"] == oldest.replace(day=1).isoformat()
        assert body["months_available"] == months_spanned(oldest, date.today())

    async def test_an_empty_budget_has_no_range(self, db_session, api_client):
        """None, and zero months — not "one month" from a floor."""
        budget, _, _ = await _budget(db_session, api_client)
        await db_session.commit()

        body = (await api_client.get(f"/api/v1/{budget.id}/reports/range")).json()
        assert body["earliest_month"] is None
        assert body["months_available"] == 0

    async def test_counts_a_single_months_history_as_one(self, db_session, api_client):
        budget, account, category = await _budget(db_session, api_client)
        await create_transaction(
            db_session, budget, account, "-5.00", date.today(), category=category
        )
        await db_session.commit()

        body = (await api_client.get(f"/api/v1/{budget.id}/reports/range")).json()
        assert body["months_available"] == 1

    async def test_plan_vs_reality_accepts_a_window_past_two_years(self, db_session, api_client):
        """Its ceiling was 24, which turned every longer pick into a 422 on one
        report out of nine. The 3-month floor is its own rule and stays."""
        budget, _, _ = await _budget(db_session, api_client)
        await db_session.commit()
        url = f"/api/v1/{budget.id}/reports/plan-vs-reality"

        assert (await api_client.get(url, params={"months": 36})).status_code == 200
        assert (await api_client.get(url, params={"months": 2})).status_code == 422

    async def test_every_report_shares_one_ceiling(self, db_session, api_client):
        """Three different bounds existed and only one of them was visible."""
        budget, _, category = await _budget(db_session, api_client)
        await db_session.commit()
        # Every report the range picker can drive. income-by-source and
        # category-history kept a private `le=60` when the shared alias moved
        # to 600, so giving them the picker would have 422'd any budget with
        # more than five years of history — the exact windows the picker
        # exists to offer.
        for path in (
            "net-worth",
            "burn-rate",
            "essentials",
            "account-composition",
            "subscriptions",
            "savings",
            "anomalies",
            "income-by-source",
            "category-history",
        ):
            # category-history is per-category; everything else takes months alone.
            extra = {"category_id": str(category.id)} if path == "category-history" else {}
            r = await api_client.get(
                f"/api/v1/{budget.id}/reports/{path}", params={"months": 120, **extra}
            )
            assert r.status_code == 200, f"{path}: {r.text}"
            over = await api_client.get(
                f"/api/v1/{budget.id}/reports/{path}", params={"months": 601, **extra}
            )
            assert over.status_code == 422, path
