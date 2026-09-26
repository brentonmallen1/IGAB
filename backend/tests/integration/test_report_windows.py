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
  90-day burn, so the subset read higher than the whole. It is now neither: it
  is the last three complete months (D6), which a rolling window can never be.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.dates import add_months, complete_month_window
from igab.guide.detection import GuideDetection
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.emergency_coverage import EmergencyCoverageService
from igab.services.essentials import essentials_summary, reported_essentials
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


class TestVolatilityServesItsReading:
    async def test_the_route_says_which_reading_its_figures_are(self, db_session, api_client):
        """`amortized` echoes the request, and the figures follow it. It was
        optional with a False default, so a path that forgot it reported
        amortized figures as the raw reading, and no test sent amortize=true."""
        budget, checking, groceries = await _world(db_session, api_client.test_user)
        # Six complete months; 600 in the first and the fourth.
        for n in (6, 3):
            await create_transaction(
                db_session, budget, checking, "-600.00", _month(n), category=groceries
            )
        await db_session.commit()

        url = f"/api/v1/{budget.id}/reports/volatility"
        raw = await api_client.get(url, params={"months": 6})
        spread = await api_client.get(url, params={"months": 6, "amortize": "true"})
        assert raw.status_code == spread.status_code == 200, (raw.text, spread.text)

        assert raw.json()["amortized"] is False
        (r,) = raw.json()["categories"]
        assert (D(r["min_val"]), D(r["max_val"])) == (D("0"), D("600"))

        assert spread.json()["amortized"] is True
        (s,) = spread.json()["categories"]
        assert D(s["min_val"]) == D(s["max_val"]) == D("200")


class TestEssentialsIsTheLastThreeCompleteMonths:
    """D6: what a lean month costs is the last three COMPLETE months.

    It was the last ninety days ÷ 3 through today. A monthly bill moves a
    rolling ninety days by a whole payment the day it enters and again the day
    it leaves, so a household whose complete months sat within a few hundred
    of each other read a figure that swung by over a thousand across a year —
    the mortgage alone jumped it by a quarter of itself overnight — and the
    emergency-fund target moved six times as far with it.

    Fixed dates, read for explicit reader days: every reader takes `today`.
    """

    async def _mortgage(self, db_session, *, june: str = "-1200.00"):
        """A 1,200 mortgage tagged Essential, paid on the 15th of every month
        from January through June 2026 (June's amount is `june`)."""
        budget, checking, _ = await _world(db_session)
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = await tags.get_system_tag(budget.id, "essential")
        group = await create_category_group(db_session, budget, "Housing")
        mortgage = await create_category(db_session, budget, group, "Mortgage")
        await tags.set_category_tags(mortgage.id, [essential.id])
        for month in range(1, 7):
            amount = june if month == 6 else "-1200.00"
            await create_transaction(
                db_session, budget, checking, amount, date(2026, month, 15), category=mortgage
            )
        await db_session.flush()
        return budget

    @pytest.mark.parametrize(
        "today",
        # The 1st, the day before the bill, the day after it, the last day.
        [date(2026, 6, 1), date(2026, 6, 14), date(2026, 6, 16), date(2026, 6, 30)],
        ids=str,
    )
    async def test_a_monthly_bill_counts_three_times_whatever_the_day(self, db_session, today):
        budget = await self._mortgage(db_session)
        figures, _ = await reported_essentials(db_session, budget.id, today)
        assert figures.as_paid == D("1200.00")
        assert (figures.window_start, figures.window_end) == (date(2026, 3, 1), date(2026, 5, 31))

    async def test_the_first_of_a_month_moves_it_a_whole_month(self, db_session):
        # June's payment rose to 1,500: invisible all June, a third of the
        # figure from 1 July.
        budget = await self._mortgage(db_session, june="-1500.00")
        june_30, _ = await reported_essentials(db_session, budget.id, date(2026, 6, 30))
        july_1, _ = await reported_essentials(db_session, budget.id, date(2026, 7, 1))
        assert june_30.as_paid == D("1200.00")
        assert july_1.as_paid == D("1300.00")
        assert (july_1.window_start, july_1.window_end) == (date(2026, 4, 1), date(2026, 6, 30))

    async def test_every_reader_quotes_the_one_figure(self, db_session):
        """The Guide's target, the Overview card, the Essentials report and
        the Emergency Fund headline — and the fund chart's newest point, which
        is now the headline by construction."""
        budget = await self._mortgage(db_session, june="-1500.00")
        today = date(2026, 7, 20)
        expected = D("1300.00")

        guide = await GuideDetection(db_session).essential_expenses(budget.id, today=today)
        card = await ReportService(db_session).dashboard_metrics(
            budget.id, date(2026, 7, 1), today, today
        )
        report = await essentials_summary(db_session, budget.id, 12, today)
        coverage = await EmergencyCoverageService(db_session).coverage(budget.id, 6, today)

        assert guide.value == expected
        assert card["essentials"].monthly == expected
        assert report["essentials"].monthly == expected
        assert coverage["essentials"].monthly == expected
        # No fund is chosen, so the chart draws no line; its figure is still
        # the headline's rule, point by point (`test_emergency_coverage.py`).

    async def test_the_guide_reads_the_readers_day(self, db_session):
        """`essential_expenses` read the server's clock beside an Overview card
        that read the reader's: on a month's last evening west of UTC the
        target counted a month the card did not."""
        budget = await self._mortgage(db_session, june="-1500.00")
        detection = GuideDetection(db_session)
        reader_june = await detection.essential_expenses(budget.id, today=date(2026, 6, 30))
        reader_july = await detection.essential_expenses(budget.id, today=date(2026, 7, 1))
        assert reader_june.value == D("1200.00")
        assert reader_july.value == D("1300.00")
