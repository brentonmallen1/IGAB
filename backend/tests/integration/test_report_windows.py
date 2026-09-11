"""The windows the reports read, said once in `domain.dates`.

Four defects from one cause — each report spelled its window by hand:

- Seasonality queried the complete months but drew its axis through the
  current month, so the newest column was always blank and the oldest month's
  cells had no column yet set the colour scale.
- Volatility zero-filled months before the budget had any history, so a young
  budget's steadiest category read as its most volatile; "All time", which
  counts the current month, always asked for one month too many.
- Volatility's drill-down computed its own window and drifted from the one the
  statistics read.
- Essentials used `today - 90` with inclusive bounds — 91 days — beside a
  90-day burn, so the subset read higher than the whole.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months, complete_month_window
from igab.guide.detection import GuideDetection
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

D = Decimal
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


def _month(n: int) -> date:
    """A date inside the month `n` months back — the 5th, always past."""
    return add_months(THIS_MONTH, -n).replace(day=5)


async def _world(db_session, user=None):
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    return budget, checking, groceries


class TestVolatilityStartsWithTheHistory:
    async def test_a_young_budgets_steady_category_reads_steady(self, db_session):
        # History began two months ago: two complete months at 400 each, and
        # the current month (partial, never counted).
        budget, checking, groceries = await _world(db_session)
        for n in (2, 1, 0):
            when = _month(n) if n else TODAY
            await create_transaction(
                db_session, budget, checking, "-400.00", when, category=groceries
            )

        data = await ReportService(db_session).category_volatility(budget.id, months=12)
        [row] = data["categories"]

        # Ten invented zero months read mean 66.67 and min 0: the
        # steadiest category in the budget reported as the most volatile.
        assert row["mean"] == D("400")
        assert row["min_val"] == D("400")
        assert row["std_dev"] == D("0")
        assert data["window_start"] == add_months(THIS_MONTH, -2)

    async def test_all_time_reads_every_complete_month_and_no_more(self, db_session):
        budget, checking, groceries = await _world(db_session)
        for n in (2, 1, 0):
            when = _month(n) if n else TODAY
            await create_transaction(
                db_session, budget, checking, "-400.00", when, category=groceries
            )
        reports = ReportService(db_session)

        # What the range picker offers as "All time" — it counts the current
        # month, which the complete-month window leaves out.
        all_time = (await reports.available_range(budget.id))["months_available"]
        assert all_time == 3
        data = await reports.category_volatility(budget.id, months=all_time)
        [row] = data["categories"]

        assert row["min_val"] == D("400")
        assert data["window_start"] == add_months(THIS_MONTH, -2)
        assert data["window_end"] == THIS_MONTH - timedelta(days=1)


class TestSeasonalityAxisIsItsQueryWindow:
    async def test_the_axis_is_the_complete_months_and_every_cell_has_a_column(self, db_session):
        budget, checking, groceries = await _world(db_session)
        for n in (5, 4, 3, 2, 1):
            await create_transaction(
                db_session, budget, checking, "-100.00", _month(n), category=groceries
            )
        # Month 4 is outside a three-month window; it used to have cells and
        # no column, and still set the colour scale.
        await create_transaction(
            db_session, budget, checking, "-800.00", _month(4), category=groceries
        )
        await create_transaction(db_session, budget, checking, "-50.00", TODAY, category=groceries)

        data = await ReportService(db_session).seasonality(budget.id, months=3)

        assert data["months"] == [add_months(THIS_MONTH, -n) for n in (3, 2, 1)]
        assert THIS_MONTH not in data["months"]
        assert {c["month"] for c in data["cells"]} == set(data["months"])

    async def test_a_young_budget_draws_no_leading_blank_columns(self, db_session):
        budget, checking, groceries = await _world(db_session)
        await create_transaction(
            db_session, budget, checking, "-100.00", _month(1), category=groceries
        )

        data = await ReportService(db_session).seasonality(budget.id, months=12)

        assert data["months"] == [add_months(THIS_MONTH, -1)]


class TestVolatilityServesItsWindow:
    async def test_the_route_carries_the_window_the_statistics_read(self, db_session, api_client):
        """The chart drilled into `monthsAgoStartISO(months - 1)` through
        today — the partial current month in, the oldest month out — under a
        comment calling it the backend's window. It drills with these now."""
        budget, checking, groceries = await _world(db_session, api_client.test_user)
        first = _month(8)
        await create_transaction(db_session, budget, checking, "-100.00", first, category=groceries)
        await create_transaction(
            db_session, budget, checking, "-100.00", _month(1), category=groceries
        )
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/reports/volatility", params={"months": 6})
        assert resp.status_code == 200, resp.text
        body = resp.json()

        start, end = complete_month_window(TODAY, 6, first)
        assert (body["window_start"], body["window_end"]) == (start.isoformat(), end.isoformat())
        assert body["window_end"] < THIS_MONTH.isoformat()


class TestEssentialsIsASubsetOfBurn:
    async def test_everything_essential_quotes_the_ninety_day_burn(self, db_session):
        """Tag every spending category Essential and the essentials figure is
        the burn rate, by definition. It read higher: `today - 90` with
        inclusive bounds is 91 days, so a charge exactly 90 days back counted
        toward Essentials and not toward the burn it is a subset of."""
        budget, checking, groceries = await _world(db_session)
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = next(
            t for t in await tags.list_for_budget(budget.id) if t.system_key == "essential"
        )
        await tags.set_category_tags(groceries.id, [essential.id])

        # Inside both windows, the boundary day, and one day outside both.
        await create_transaction(
            db_session, budget, checking, "-300.00", TODAY - timedelta(days=10), category=groceries
        )
        await create_transaction(
            db_session, budget, checking, "-300.00", TODAY - timedelta(days=89), category=groceries
        )
        await create_transaction(
            db_session, budget, checking, "-300.00", TODAY - timedelta(days=90), category=groceries
        )

        reports = ReportService(db_session)
        metrics = await reports.dashboard_metrics(budget.id, THIS_MONTH, TODAY)
        guide = await GuideDetection(db_session).essential_expenses(budget.id)

        assert metrics["burn_rate_90"] == D("200.00")
        assert metrics["essentials_monthly"] == metrics["burn_rate_90"]
        assert guide.value == metrics["burn_rate_90"]
