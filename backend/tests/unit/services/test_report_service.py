"""
Tests for ReportService — verifies that each report method produces the correct
aggregations, financial calculations, and data structures that the frontend charts
render. All DB interaction is mocked via AsyncMock session.execute() side_effect.
"""

import uuid
from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from igab.domain.dates import add_months
from igab.services.report_service import ReportService
from tests.report_clock import report_today

# ─── Helpers ──────────────────────────────────────────────────────────────────


def D(s: str) -> Decimal:
    return Decimal(s)


def row(**kwargs):
    """SQLAlchemy-style row: supports both attribute access and positional indexing."""
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


def ledger_row(category_id, day: date, amount, name="Groceries", group="Everyday", cls="spending"):
    """One bucket of `plan_ledger`'s rows query: what `plan_effect` reads
    (class, savings envelope, sign) beside the summed amount. The class is
    decided in SQL, so a mock states it — which is why the rules themselves
    are tested against a real database (`test_report_envelope_rules.py`)."""
    return row(
        category_id=category_id,
        month=day.replace(day=1),
        cls=cls,
        savings_envelope=False,
        inflow=amount > 0,
        amount=amount,
        category_name=name,
        group_name=group,
        sinking=False,
    )


def mock_result(rows: list) -> MagicMock:
    """Result that responds to .all()."""
    r = MagicMock()
    r.all.return_value = rows
    return r


def scalar_result(value) -> MagicMock:
    """Result that responds to .scalar()."""
    r = MagicMock()
    r.scalar.return_value = value
    return r


def earliest_result(value: date | None) -> MagicMock:
    """What `TransactionRepository.earliest_date` reads: when history starts.
    The complete-month reports ask for it first, to clamp their window."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def make_session(*results) -> AsyncMock:
    """
    Session whose execute() calls return results in order.
    Pass mock_result() or scalar_result() objects.
    """
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


BUDGET = uuid.uuid4()
CAT_A = uuid.uuid4()
CAT_B = uuid.uuid4()
CAT_C = uuid.uuid4()
GRP_1 = uuid.uuid4()
GRP_2 = uuid.uuid4()
ACCT_1 = uuid.uuid4()
ACCT_2 = uuid.uuid4()
PAYEE_1 = uuid.uuid4()
PAYEE_2 = uuid.uuid4()

JAN = date(2026, 1, 1)
FEB = date(2026, 2, 1)
MAR = date(2026, 3, 1)
APR = date(2026, 4, 1)


# ─── spending_by_category ─────────────────────────────────────────────────────


class TestSpendingByCategory:
    async def test_basic_aggregation(self):
        rows = [
            row(id=CAT_A, name="Groceries", group_name="Food", cls="spending", amount=D("-60.00")),
            row(id=CAT_A, name="Groceries", group_name="Food", cls="spending", amount=D("-40.00")),
            row(id=CAT_B, name="Gas", group_name="Transport", cls="spending", amount=D("-25.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        cats, total = await svc.spending_by_category(BUDGET, JAN, APR)

        assert total == D("125.00")
        assert cats[0]["name"] == "Groceries"
        assert cats[0]["total"] == D("100.0")
        assert cats[0]["pct"] == pytest.approx(80.0, rel=1e-3)
        assert cats[1]["name"] == "Gas"
        assert cats[1]["total"] == D("25.0")
        assert cats[1]["pct"] == pytest.approx(20.0, rel=1e-3)

    async def test_empty_returns_zeros(self):
        svc = ReportService(make_session(mock_result([])))
        cats, total = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats == []
        assert total == D("0")

    async def test_single_category_pct_is_100(self):
        rows = [
            row(id=CAT_A, name="Rent", group_name="Housing", cls="spending", amount=D("-1200.00"))
        ]
        svc = ReportService(make_session(mock_result(rows)))
        cats, total = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats[0]["pct"] == pytest.approx(100.0)

    async def test_amounts_are_absolute(self):
        """Stored as negative; returned totals must be positive."""
        rows = [row(id=CAT_A, name="X", group_name="G", cls="spending", amount=D("-500.00"))]
        svc = ReportService(make_session(mock_result(rows)))
        cats, total = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats[0]["total"] > 0
        assert total > 0

    async def test_sorted_descending_by_total(self):
        rows = [
            row(id=CAT_A, name="Small", group_name="G", cls="spending", amount=D("-10.00")),
            row(id=CAT_B, name="Large", group_name="G", cls="spending", amount=D("-200.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        cats, _ = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats[0]["name"] == "Large"
        assert cats[1]["name"] == "Small"


# ─── income_vs_expense ────────────────────────────────────────────────────────


class TestIncomeVsExpense:
    """The service now groups by activity class in SQL, so the mocked rows are
    (month, cls, total) rather than raw (date, amount).

    Nothing here holds money in a kept-here envelope, so the held part is
    pinned to zero rather than mocked query by query; it is a budget walk with
    its own integration suite (tests/integration/test_savings_held.py)."""

    @pytest.fixture(autouse=True)
    def _nothing_held(self):
        async def zeros(session, budget_id, months, today):
            return [Decimal("0")] * len(months)

        with patch("igab.services.report_service.held_by_month", zeros):
            yield

    @staticmethod
    def _rows(*triples):
        return [row(month=m, cls=c, total=t) for m, c, t in triples]

    @staticmethod
    def _svc(rows) -> ReportService:
        # The window asks where the history starts first (`budget_window`).
        return ReportService(make_session(earliest_result(None), mock_result(rows)))

    async def test_buckets_by_month(self):
        today = date.today()
        first = today.replace(day=1)
        last_month = add_months(first, -1)

        svc = self._svc(
            self._rows(
                (last_month, "income", D("3000.00")),
                (last_month, "spending", D("-500.00")),
                (first, "income", D("3000.00")),
                (first, "spending", D("-800.00")),
            )
        )
        result = await svc.income_vs_expense(BUDGET, months=2)

        # Two complete months, then the running one.
        assert len(result) == 3
        prev = next(r for r in result if r["month"] == last_month)
        curr = next(r for r in result if r["month"] == first)

        assert prev["income"] == D("3000.00")
        assert prev["expenses"] == D("500.00")
        assert curr["income"] == D("3000.00")
        assert curr["expenses"] == D("800.00")

    async def test_n_months_are_n_complete_months_and_the_running_one(self):
        """D5: "2 months" drew one complete month and the running one; now it
        is two complete months, and the running month is flagged apart."""
        first = date.today().replace(day=1)
        result = await self._svc([]).income_vs_expense(BUDGET, months=2)
        assert [r["month"] for r in result] == [add_months(first, -2), add_months(first, -1), first]
        assert [r["partial_month"] for r in result] == [False, False, True]

    async def test_savings_is_broken_out_of_expenses(self):
        """The point of the change: money moved into savings is not spending."""
        first = date.today().replace(day=1)
        svc = self._svc(
            self._rows(
                (first, "income", D("3000.00")),
                (first, "spending", D("-800.00")),
                (first, "savings", D("-1000.00")),
                (first, "debt_principal", D("-200.00")),
            )
        )
        result = await svc.income_vs_expense(BUDGET, months=1)
        assert result[-1]["expenses"] == D("800.00")
        assert result[-1]["savings"] == D("1000.00")
        assert result[-1]["debt_principal"] == D("200.00")

    async def test_the_parts_reconcile(self):
        """net must stay income minus everything that left the accounts, or a
        stacked chart drifts away from its own total. Money-moved: with
        nothing held, saved and moved are the same figure."""
        first = date.today().replace(day=1)
        svc = self._svc(
            self._rows(
                (first, "income", D("3000.00")),
                (first, "spending", D("-800.00")),
                (first, "savings", D("-1000.00")),
                (first, "debt_principal", D("-200.00")),
            )
        )
        r = (await svc.income_vs_expense(BUDGET, months=1))[-1]
        assert r["net"] == r["income"] - r["expenses"] - r["savings_moved"] - r["debt_principal"]
        assert r["savings"] == r["savings_moved"] == D("1000.00")
        assert r["savings_held"] == D("0")
        assert r["net"] == D("1000.00")

    async def test_internal_transfers_are_ignored(self):
        first = date.today().replace(day=1)
        svc = self._svc(
            self._rows(
                (first, "income", D("1000.00")),
                (first, "transfer_internal", D("-400.00")),
            )
        )
        r = (await svc.income_vs_expense(BUDGET, months=1))[-1]
        assert r["expenses"] == D("0")
        assert r["net"] == D("1000.00")

    async def test_empty_fills_all_months_with_zeros(self):
        result = await self._svc([]).income_vs_expense(BUDGET, months=3)
        assert len(result) == 4
        for r in result:
            assert r["income"] == D("0")
            assert r["expenses"] == D("0")
            assert r["savings"] == D("0")
            assert r["net"] == D("0")

    async def test_expenses_are_absolute_values(self):
        first = date.today().replace(day=1)
        svc = self._svc(self._rows((first, "spending", D("-300.00"))))
        result = await svc.income_vs_expense(BUDGET, months=1)
        assert result[-1]["expenses"] == D("300.00")


# ─── dashboard_metrics ────────────────────────────────────────────────────────

# TestDashboardMetrics moved to tests/integration/test_dashboard_metrics.py.
# These mocked `session.execute` with a fixed sequence of result sets, which
# cannot exercise dashboard_metrics now that its figures come from the
# activity-class CASE: the classification happens in SQL, so a mock hands
# back whatever the test fabricated and proves only that polars can add.
# The card is money math, so it gets a real database.


class TestBudgetVsActual:
    def _assignment(self, cat_id, month, assigned, cat_name="Groceries", group_name="Food"):
        return row(
            category_id=cat_id,
            month=month,
            assigned=assigned,
            category_name=cat_name,
            group_name=group_name,
            sinking=False,
        )

    def _spend(self, cat_id, amount, name="Groceries", group="Everyday"):
        # The names travel with the spend rows now: a category spent from but
        # never assigned to in the window used to be served as "Unknown".
        return ledger_row(cat_id, JAN, amount, name, group)

    async def test_basic_variance(self):
        assigns = [self._assignment(CAT_A, JAN, D("500.00"))]
        spends = [self._spend(CAT_A, D("-420.00"))]

        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)

        cat = result["categories"][0]
        assert cat["assigned"] == D("500.00")
        assert cat["spent"] == D("420.00")
        assert cat["variance"] == D("80.00")
        assert cat["variance_pct"] == pytest.approx(16.0)

    async def test_overspend_shows_negative_variance(self):
        assigns = [self._assignment(CAT_A, JAN, D("200.00"))]
        spends = [self._spend(CAT_A, D("-350.00"))]

        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)

        cat = result["categories"][0]
        assert cat["variance"] < 0
        assert cat["variance"] == D("-150.00")

    async def test_total_sums(self):
        assigns = [
            self._assignment(CAT_A, JAN, D("500.00"), "A"),
            self._assignment(CAT_B, JAN, D("300.00"), "B"),
        ]
        spends = [
            self._spend(CAT_A, D("-400.00")),
            self._spend(CAT_B, D("-250.00")),
        ]
        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)

        assert result["total_assigned"] == D("800.00")
        assert result["total_spent"] == D("650.00")
        assert result["total_variance"] == D("150.00")

    async def test_the_headline_variance_is_the_rows_not_the_raw_totals(self):
        """300 drained out of A with nothing spent, B 150 over its 200. Raw
        `total_assigned - total_spent` is -450; the rows read on plan and
        150 over, and the headline has to say what the rows say."""
        assigns = [
            self._assignment(CAT_A, JAN, D("-300.00"), "A"),
            self._assignment(CAT_B, JAN, D("200.00"), "B"),
        ]
        spends = [self._spend(CAT_B, D("-350.00"), name="B")]
        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)

        # The drained envelope planned nothing and spent nothing, so it is not
        # a row — "$0 / $0" is not a finding — and the totals are the rows'.
        assert [c["category_name"] for c in result["categories"]] == ["B"]
        assert result["total_variance"] == D("-150.00")
        assert result["total_variance"] == sum(c["variance"] for c in result["categories"])

    async def test_empty_returns_zeros(self):
        svc = ReportService(make_session(mock_result([]), mock_result([])))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)
        assert result == {
            "categories": [],
            "total_assigned": D("0"),
            "total_moved_in": D("0"),
            "total_plan": D("0"),
            "total_spent": D("0"),
            "total_variance": D("0"),
        }

    async def test_variance_pct_is_none_when_no_assignment(self):
        """Category with spending but no assignment has no variance_pct.

        A percentage of nothing has no value. It was served as 0.0, which is
        also what "spent its plan to the cent" serves, so the chart printed
        "0.0%" for spending nobody planned. `variance` carries the real answer
        (-100 here).
        """
        assigns = []
        spends = [self._spend(CAT_A, D("-100.00"), name="Cascade Point Dues")]
        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)
        cat = result["categories"][0]
        assert cat["variance_pct"] is None
        assert cat["variance"] == D("-100.00")
        assert cat["assigned"] == D("0")
        # And it is named, not "Unknown" with a blank group.
        assert cat["category_name"] == "Cascade Point Dues"
        assert cat["category_group_name"] == "Everyday"


# ─── cumulative_variance ──────────────────────────────────────────────────────


class TestCumulativeVariance:
    @staticmethod
    def _svc(assigns, spends) -> ReportService:
        return ReportService(
            make_session(earliest_result(None), mock_result(assigns), mock_result(spends))
        )

    async def test_cumulative_carries_forward(self):
        # Use real current dates to avoid patching the date class (which breaks isinstance).
        first = date.today().replace(day=1)
        m1 = add_months(first, -2)
        m2 = add_months(first, -1)

        assigns = [
            row(
                category_id=CAT_A,
                month=m,
                assigned=D("500.00"),
                category_name="Groceries",
                group_name="Food",
                sinking=False,
            )
            for m in (m1, m2)
        ]
        spends = [
            ledger_row(CAT_A, m1.replace(day=15), D("-400.00")),
            ledger_row(CAT_A, m2.replace(day=10), D("-600.00")),
        ]
        result = await self._svc(assigns, spends).cumulative_variance(BUDGET, months=2)

        assert len(result) == 3
        r0 = next(r for r in result if r["month"] == m1)
        r1 = next(r for r in result if r["month"] == m2)
        assert r0["monthly_variance"] == D("100.00")
        assert r0["cumulative_variance"] == D("100.00")
        assert r1["monthly_variance"] == D("-100.00")
        assert r1["cumulative_variance"] == D("0.00")

    async def test_the_running_month_is_drawn_but_not_in_the_drift(self):
        """Its whole assignment lands on the 1st while its spending arrives
        over the month: counted, the drift leapt "under budget" every 1st."""
        first = date.today().replace(day=1)
        last = add_months(first, -1)
        assigns = [
            row(
                category_id=CAT_A,
                month=m,
                assigned=D(amount),
                category_name="Groceries",
                group_name="Food",
                sinking=False,
            )
            for m, amount in ((last, "400.00"), (first, "900.00"))
        ]
        spends = [ledger_row(CAT_A, first, D("-100.00"))]
        result = await self._svc(assigns, spends).cumulative_variance(BUDGET, months=1)

        done, running = result
        assert (done["partial_month"], running["partial_month"]) == (False, True)
        assert done["cumulative_variance"] == D("400.00")
        # Its own figures so far are served; its drift is not.
        assert running["budget_assigned"] == D("900.00")
        assert running["actual_spent"] == D("100.00")
        assert running["monthly_variance"] == D("800.00")
        assert running["cumulative_variance"] is None

    async def test_months_with_no_data_count_as_zero(self):
        first = date.today().replace(day=1)
        m1 = add_months(first, -2)
        m2 = add_months(first, -1)

        assigns = [
            row(
                category_id=CAT_A,
                month=m1,
                assigned=D("400.00"),
                category_name="Groceries",
                group_name="Food",
                sinking=False,
            )
        ]
        result = await self._svc(assigns, []).cumulative_variance(BUDGET, months=2)

        r1 = next(r for r in result if r["month"] == m1)
        r2 = next(r for r in result if r["month"] == m2)
        assert r1["monthly_variance"] == D("400.00")
        assert r2["monthly_variance"] == D("0.00")
        assert r2["cumulative_variance"] == D("400.00")


# ─── spending_grouped ─────────────────────────────────────────────────────────


class TestSpendingGrouped:
    async def test_basic_grouping(self):
        rows = [
            row(
                id=CAT_A,
                name="Groceries",
                group_id=GRP_1,
                group_name="Food",
                amount=D("-100.00"),
                cls="spending",
            ),
            row(
                id=CAT_A,
                name="Groceries",
                group_id=GRP_1,
                group_name="Food",
                amount=D("-50.00"),
                cls="spending",
            ),
            row(
                id=CAT_B,
                name="Gas",
                group_id=GRP_2,
                group_name="Transport",
                amount=D("-75.00"),
                cls="spending",
            ),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        items, total, _ = await svc.spending_grouped(BUDGET, JAN, APR)

        assert total == D("225.0")
        grocery = next(i for i in items if i["name"] == "Groceries")
        gas = next(i for i in items if i["name"] == "Gas")
        assert grocery["total"] == D("150.0")
        assert grocery["parent_name"] == "Food"
        assert gas["total"] == D("75.0")

    async def test_percentages(self):
        rows = [
            row(
                id=CAT_A,
                name="X",
                group_id=GRP_1,
                group_name="G1",
                amount=D("-300.00"),
                cls="spending",
            ),
            row(
                id=CAT_B,
                name="Y",
                group_id=GRP_1,
                group_name="G1",
                amount=D("-100.00"),
                cls="spending",
            ),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        items, total, _ = await svc.spending_grouped(BUDGET, JAN, APR)

        x = next(i for i in items if i["name"] == "X")
        y = next(i for i in items if i["name"] == "Y")
        assert x["pct"] == pytest.approx(75.0)
        assert y["pct"] == pytest.approx(25.0)

    async def test_empty(self):
        svc = ReportService(make_session(mock_result([])))
        items, total, _ = await svc.spending_grouped(BUDGET, JAN, APR)
        assert items == []
        assert total == D("0")


# ─── day_patterns ─────────────────────────────────────────────────────────────


def spend_row(**kwargs):
    """A `ReportService._spending_query` row: every reader of the one spending
    definition gets the same columns, so a fixture states them all. Each row
    is its own purchase unless a `txn_id` says otherwise."""
    kwargs.setdefault("cls", "spending")
    kwargs.setdefault("id", uuid.uuid4())
    kwargs.setdefault("name", "Shopping")
    kwargs.setdefault("group_id", GRP_1)
    kwargs.setdefault("group_name", "Everyday")
    kwargs.setdefault("payee_id", PAYEE_1)
    kwargs.setdefault("payee_name", "Amazon")
    kwargs.setdefault("txn_id", uuid.uuid4())
    return row(**kwargs)


def day_session(rows, earliest=None):
    """The rows, then when the budget's history starts."""
    return make_session(mock_result(rows), earliest_result(earliest))


class TestDayPatterns:
    async def test_seven_days_always_returned(self):
        svc = ReportService(day_session([]))
        days = (await svc.day_patterns(BUDGET, JAN, APR))["days"]
        assert len(days) == 7
        assert {r["day_of_week"] for r in days} == set(range(7))

    async def test_day_names_correct(self):
        svc = ReportService(day_session([]))
        days = (await svc.day_patterns(BUDGET, JAN, APR))["days"]
        by_idx = {r["day_of_week"]: r["day_name"] for r in days}
        assert by_idx[0] == "Monday"
        assert by_idx[6] == "Sunday"

    async def test_aggregation_by_weekday(self):
        # 2026-01-05 is a Monday, 2026-01-06 is Tuesday
        rows = [
            spend_row(date=date(2026, 1, 5), amount=D("-100.00")),
            spend_row(date=date(2026, 1, 5), amount=D("-50.00")),
            spend_row(date=date(2026, 1, 6), amount=D("-200.00")),
        ]
        svc = ReportService(day_session(rows))
        days = (await svc.day_patterns(BUDGET, JAN, APR))["days"]

        monday = next(r for r in days if r["day_name"] == "Monday")
        tuesday = next(r for r in days if r["day_name"] == "Tuesday")
        assert monday["total"] == D("150.0")
        assert monday["count"] == 2
        assert tuesday["total"] == D("200.0")

    async def test_the_average_is_per_calendar_monday_quiet_ones_included(self):
        """Two Mondays in the window, one with 300 spent: a typical Monday is
        150. The average per transaction said 150 too, by coincidence — with
        three purchases that Monday it would have said 100."""
        rows = [
            spend_row(date=date(2026, 1, 5), amount=D("-100.00")),
            spend_row(date=date(2026, 1, 5), amount=D("-120.00")),
            spend_row(date=date(2026, 1, 5), amount=D("-80.00")),
        ]
        svc = ReportService(day_session(rows))
        days = (await svc.day_patterns(BUDGET, date(2026, 1, 5), date(2026, 1, 18)))["days"]
        monday = next(r for r in days if r["day_name"] == "Monday")
        assert monday["weekdays"] == 2
        assert monday["avg_per_day"] == D("150.00")
        assert monday["count"] == 3

    async def test_days_before_the_history_are_not_quiet_days(self):
        """A range reaching back before the first transaction divides by the
        Mondays since it, not by Mondays nobody recorded."""
        rows = [spend_row(date=date(2026, 1, 12), amount=D("-90.00"))]
        svc = ReportService(day_session(rows, earliest=date(2026, 1, 12)))
        result = await svc.day_patterns(BUDGET, date(2026, 1, 1), date(2026, 1, 25))
        monday = next(r for r in result["days"] if r["day_name"] == "Monday")
        assert result["window_start"] == date(2026, 1, 12)
        assert monday["weekdays"] == 2
        assert monday["avg_per_day"] == D("45.00")

    async def test_a_split_is_one_purchase(self):
        """Two legs of one trip share a `txn_id`: one purchase on the chart."""
        trip = uuid.uuid4()
        rows = [
            spend_row(date=date(2026, 1, 5), amount=D("-60.00"), txn_id=trip),
            spend_row(date=date(2026, 1, 5), amount=D("-40.00"), txn_id=trip),
        ]
        days = (await ReportService(day_session(rows)).day_patterns(BUDGET, JAN, APR))["days"]
        assert days[0]["count"] == 1
        assert days[0]["total"] == D("100.00")

    async def test_a_refund_lowers_its_day(self):
        rows = [
            spend_row(date=date(2026, 1, 5), amount=D("-100.00")),
            spend_row(date=date(2026, 1, 5), amount=D("30.00")),
        ]
        days = (await ReportService(day_session(rows)).day_patterns(BUDGET, JAN, APR))["days"]
        assert days[0]["total"] == D("70.00")

    async def test_empty_days_return_zero_not_missing(self):
        rows = [spend_row(date=date(2026, 1, 5), amount=D("-100.00"))]  # Monday only
        svc = ReportService(day_session(rows))
        days = (await svc.day_patterns(BUDGET, JAN, APR))["days"]
        sunday = next(r for r in days if r["day_name"] == "Sunday")
        assert sunday["total"] == D("0")
        assert sunday["count"] == 0

    async def test_a_savings_row_is_partitioned_out_of_the_chart(self):
        """The class filter used to be a WHERE clause, so these rows never
        arrived. They arrive now, and must not be charted as spending."""
        cat = uuid.uuid4()
        rows = [
            spend_row(date=date(2026, 1, 5), amount=D("-100.00")),
            spend_row(date=date(2026, 1, 5), amount=D("-900.00"), cls="savings", id=cat),
        ]
        svc = ReportService(day_session(rows))
        days = (await svc.day_patterns(BUDGET, JAN, APR))["days"]
        monday = next(r for r in days if r["day_name"] == "Monday")
        assert monday["total"] == D("100.0")
        assert monday["count"] == 1

    async def test_the_note_only_fires_for_a_category_selection(self):
        cat = uuid.uuid4()
        rows = [spend_row(date=date(2026, 1, 5), amount=D("-900.00"), cls="savings", id=cat)]

        unscoped = await ReportService(day_session(rows)).day_patterns(BUDGET, JAN, APR)
        assert unscoped["class_excluded"] is None

        scoped = await ReportService(day_session(rows)).day_patterns(
            BUDGET, JAN, APR, category_ids=[cat]
        )
        assert scoped["class_excluded"] == [
            {
                "activity_class": "savings",
                "label": "Savings",
                "categories": 1,
                "total": D("900.00"),
            }
        ]


# ─── payee_analysis ───────────────────────────────────────────────────────────


class TestPayeeAnalysis:
    def _txn(self, txn_date, amount, payee_id=None, payee_name="Amazon", cat_name="Shopping"):
        return spend_row(
            date=txn_date,
            amount=amount,
            payee_id=payee_id or PAYEE_1,
            payee_name=payee_name,
            id=CAT_A,
            name=cat_name,
        )

    async def _analysis(self, rows, start=JAN, end=APR, **kwargs):
        return await ReportService(make_session(mock_result(rows))).payee_analysis(
            BUDGET, start, end, **kwargs
        )

    async def test_is_recurring_three_or_more_months(self):
        rows = [
            self._txn(date(2026, 1, 15), D("-50.00")),
            self._txn(date(2026, 2, 15), D("-50.00")),
            self._txn(date(2026, 3, 15), D("-50.00")),
        ]
        report = await self._analysis(rows)
        assert report["recurring_min_months"] == 3
        assert report["payees"][0]["is_recurring"] is True

    async def test_not_recurring_two_months(self):
        rows = [
            self._txn(date(2026, 1, 15), D("-50.00")),
            self._txn(date(2026, 2, 15), D("-50.00")),
        ]
        report = await self._analysis(rows)
        assert report["payees"][0]["is_recurring"] is False

    async def test_over_a_year_three_months_is_not_a_habit(self):
        """Recurring is relative to the window: over twelve months it takes
        six. A fixed three called a payee seen in three scattered months of a
        year recurring."""
        rows = [
            self._txn(date(2026, 1, 15), D("-50.00")),
            self._txn(date(2026, 5, 15), D("-50.00")),
            self._txn(date(2026, 9, 15), D("-50.00")),
        ]
        report = await self._analysis(rows, JAN, date(2026, 12, 31))
        assert report["recurring_min_months"] == 6
        assert report["payees"][0]["is_recurring"] is False

    async def test_a_short_window_calls_nothing_recurring_and_says_so(self):
        rows = [self._txn(date(2026, 1, 15), D("-50.00"))]
        report = await self._analysis(rows, JAN, date(2026, 2, 28))
        assert report["recurring_min_months"] is None
        assert report["payees"][0]["is_recurring"] is False

    async def test_monthly_trend(self):
        rows = [
            self._txn(date(2026, 1, 10), D("-100.00")),
            self._txn(date(2026, 1, 20), D("-50.00")),
            self._txn(date(2026, 2, 5), D("-75.00")),
        ]
        report = await self._analysis(rows)
        trend = {t["month"]: t["total"] for t in report["payees"][0]["monthly_trend"]}
        assert trend[date(2026, 1, 1)] == D("150.0")
        assert trend[date(2026, 2, 1)] == D("75.0")

    async def test_total_and_count(self):
        rows = [
            self._txn(date(2026, 1, 1), D("-100.00")),
            self._txn(date(2026, 1, 2), D("-200.00")),
        ]
        report = await self._analysis(rows)
        assert report["payees"][0]["total"] == D("300.0")
        assert report["payees"][0]["count"] == 2
        assert report["total"] == D("300.0")

    async def test_a_refund_lowers_its_payee(self):
        rows = [
            self._txn(date(2026, 1, 1), D("-100.00")),
            self._txn(date(2026, 1, 9), D("40.00")),
        ]
        report = await self._analysis(rows)
        assert report["payees"][0]["total"] == D("60.00")
        assert report["total"] == D("60.00")

    async def test_top_categories(self):
        rows = [
            self._txn(date(2026, 1, 1), D("-100.00"), cat_name="Groceries"),
            self._txn(date(2026, 1, 2), D("-300.00"), cat_name="Electronics"),
        ]
        report = await self._analysis(rows)
        top = {c["category_name"]: c["total"] for c in report["payees"][0]["top_categories"]}
        assert top["Electronics"] == D("300.0")
        assert top["Groceries"] == D("100.0")

    async def test_empty_returns_empty(self):
        report = await self._analysis([])
        assert report["payees"] == []
        assert report["total"] == D("0")
        assert report["payee_count"] == 0

    async def test_the_total_and_count_span_every_payee_not_the_ranked_ones(self):
        # The cap is what this report IS — a ranking, not a page — so both
        # figures beside it have to describe the period. They were computed
        # from the capped frame, so "Total Spent" was the visible subtotal and
        # every `pct` was a share of it.
        third = uuid.uuid4()
        rows = [
            self._txn(date(2026, 1, 1), D("-400.00"), PAYEE_1, "Harborstone Realty"),
            self._txn(date(2026, 1, 2), D("-300.00"), PAYEE_2, "Cascade Grocers"),
            self._txn(date(2026, 1, 3), D("-100.00"), third, "Alder Street Cafe"),
        ]
        report = await self._analysis(rows, limit=2)
        payees = report["payees"]
        assert [p["payee_name"] for p in payees] == ["Harborstone Realty", "Cascade Grocers"]
        assert report["total"] == D("800.0")
        assert report["payee_count"] == 3
        # 400 / 800, not 400 / 700.
        assert round(payees[0]["pct"], 1) == 50.0


# ─── burn_rate ────────────────────────────────────────────────────────────────


class TestBurnRate:
    # The newest point's windows end YESTERDAY (`burn_as_of`): today almost
    # never has synced rows, so a window ending today read one quiet day low.
    # Test dates anchor there — `as_of` below — and each case runs mid-month,
    # on the day before a month ends, and on a 1st, whose yesterday is the
    # last day of the month before.
    #
    # The service clock is pinned. These read the real `date.today()`, and a
    # window reaching into the future could otherwise pass on some days of
    # the month and ship.

    @pytest.fixture(
        params=[date(2026, 9, 10), date(2026, 9, 29), date(2026, 2, 27), date(2026, 10, 1)],
        ids=str,
    )
    def today(self, request):
        with report_today(request.param) as today:
            yield today

    async def _newest(self, rows, **kwargs) -> dict:
        svc = ReportService(make_session(earliest_result(None), mock_result(rows)))
        return (await svc.burn_rate(BUDGET, months=1, **kwargs))[-1]

    @staticmethod
    def _spend(day: date, amount: str, cls: str = "spending"):
        """One (date, class, signed total) row, as the grouped query returns it."""
        return row(date=day, cls=cls, amount=D(amount))

    async def test_rolling_30_sums_the_30_days_to_yesterday(self, today):
        as_of = today - timedelta(days=1)
        rows = [
            self._spend(as_of - timedelta(days=25), "-200.00"),
            self._spend(as_of - timedelta(days=3), "-300.00"),
        ]
        assert (await self._newest(rows))["rolling_30"] == D("500.00")

    async def test_the_30_day_window_is_yesterday_and_the_29_days_before(self, today):
        """Day 30 counting yesterday as day 1 is in; day 31 is the prior
        window's."""
        as_of = today - timedelta(days=1)
        rows = [
            self._spend(as_of - timedelta(days=30), "-700.00"),
            self._spend(as_of - timedelta(days=29), "-200.00"),
            self._spend(as_of, "-300.00"),
        ]
        newest = await self._newest(rows)
        assert newest["rolling_30"] == D("500.00")
        assert newest["prior_60"] == D("350.00")

    async def test_today_is_not_in_the_newest_burn(self, today):
        """A row dated today — the day the bank has not finished posting —
        counts tomorrow, and a row dated tomorrow is not money burned."""
        rows = [
            self._spend(today - timedelta(days=2), "-300.00"),
            self._spend(today, "-400.00"),
            self._spend(today + timedelta(days=1), "-900.00"),
        ]
        newest = await self._newest(rows)
        assert newest["rolling_30"] == D("300.00")
        assert newest["prior_60"] == D("0.00")

    async def test_prior_60_is_the_sixty_days_before_the_thirty_halved(self, today):
        # 1,200 in days 31–90 is 600 per thirty; the 300 inside the last
        # thirty is not part of it, as it was of the old ninety-day average.
        as_of = today - timedelta(days=1)
        rows = [
            self._spend(as_of - timedelta(days=85), "-600.00"),
            self._spend(as_of - timedelta(days=50), "-600.00"),
            self._spend(as_of - timedelta(days=10), "-300.00"),
        ]
        cur = await self._newest(rows)
        assert cur["prior_60"] == D("600.00")
        assert cur["rolling_30"] == D("300.00")

    async def test_the_prior_window_ends_on_day_90(self, today):
        as_of = today - timedelta(days=1)
        rows = [
            self._spend(as_of - timedelta(days=90), "-300.00"),
            self._spend(as_of - timedelta(days=89), "-900.00"),
        ]
        assert (await self._newest(rows))["prior_60"] == D("450.00")

    async def test_the_readers_today_overrides_the_server_clock(self, today):
        """`client_today` a day ahead: the server's today is the reader's
        yesterday, so its row is in the reader's newest burn."""
        ahead = today + timedelta(days=1)
        rows = [self._spend(today, "-250.00")]
        newest = await self._newest(rows, today=ahead)
        assert newest["rolling_30"] == D("250.00")
        assert newest["date"] == ahead.replace(day=1)

    async def test_a_complete_months_point_ends_on_its_last_day(self, today):
        """Every point but the running month's is the thirty days to that
        month's last day: "12 months" is twelve complete months of points."""
        last_month_end = today.replace(day=1) - timedelta(days=1)
        rows = [self._spend(last_month_end, "-120.00")]
        svc = ReportService(make_session(earliest_result(None), mock_result(rows)))
        points = await svc.burn_rate(BUDGET, months=1)
        assert len(points) == 2
        assert points[0]["date"] == last_month_end.replace(day=1)
        assert points[0]["rolling_30"] == D("120.00")


# ─── net_worth_history ────────────────────────────────────────────────────────
# The classification math moved to test_report_stats.py (TestBalanceSheet),
# and the balances it reads to tests/integration/test_net_worth_history.py:
# the rows come from one grouped SQL aggregate a mocked session cannot run.


# ─── category_volatility ──────────────────────────────────────────────────────


class TestCategoryVolatility:
    async def test_statistical_output(self):
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            def vrow(d, amt):
                return ledger_row(CAT_A, d, amt, "Groceries", "Food")

            # months=3 with today in March means the three COMPLETE months
            # Dec, Jan, Feb. March is the partial current month and is out —
            # counting it as complete invents a historical minimum on the 2nd
            # of every month.
            rows = [
                vrow(date(2025, 12, 15), D("-100.00")),
                vrow(date(2026, 1, 15), D("-200.00")),
                vrow(date(2026, 2, 15), D("-150.00")),
            ]
            svc = ReportService(make_session(earliest_result(None), mock_result(rows)))
            result = (await svc.category_volatility(BUDGET, months=3))["categories"]

        assert len(result) == 1
        r = result[0]
        assert r["category_name"] == "Groceries"
        assert r["mean"] == pytest.approx(D("150.0"), rel=D("0.01"))
        assert r["min_val"] == pytest.approx(D("100.0"), rel=D("0.01"))
        assert r["max_val"] == pytest.approx(D("200.0"), rel=D("0.01"))
        assert r["months_included"] == 3

    async def test_a_dormant_month_is_a_zero_not_a_missing_row(self):
        """The statistics used to group only the months that HAD rows, which
        made every one of them per-ACTIVE-month.

        A bill paid twice a year reported a mean of its full charge and a
        standard deviation of zero — "£600 a month, never varies" — when its
        monthly cost is a sixth of that and it is the most volatile thing in
        the budget. `min_val` could never be zero either, so a dormant category
        showed a floor it had never spent as little as.
        """
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 10)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            def vrow(d, amt):
                return ledger_row(CAT_A, d, amt, "Property Tax", "Long Term")

            # Two charges of 600 in a six-month window: Jan and Apr.
            rows = [vrow(date(2026, 1, 20), D("-600.00")), vrow(date(2026, 4, 20), D("-600.00"))]
            svc = ReportService(make_session(earliest_result(None), mock_result(rows)))
            result = (await svc.category_volatility(BUDGET, months=6))["categories"]

        r = result[0]
        # 1,200 over six months, not 600 over two.
        assert r["mean"] == pytest.approx(D("200.0"), rel=D("0.01"))
        # The four dormant months are real, so the floor is zero and the
        # spread is wide. It used to read min 600, max 600, std_dev 0.
        assert r["min_val"] == D("0")
        assert r["max_val"] == pytest.approx(D("600.0"), rel=D("0.01"))
        assert r["std_dev"] > D("200")
        # The one figure that genuinely wants the sparse count.
        assert r["months_included"] == 2

    async def test_amortize_reaches_the_statistics(self):
        """The toggle's whole path below the route. Nothing passed amortize=True
        here, so dropping the argument left every test green and the toggle
        quietly showing the raw reading."""
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 10)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            def vrow(d):
                return ledger_row(CAT_A, d, D("-600.00"), "Property Tax", "Long Term")

            # Jan–Jun, 600 in Jan and Apr: 200 a month once spread.
            rows = [vrow(date(2026, 1, 20)), vrow(date(2026, 4, 20))]
            svc = ReportService(make_session(earliest_result(None), mock_result(rows)))
            (r,) = (await svc.category_volatility(BUDGET, months=6, amortize=True))["categories"]

        assert r["min_val"] == r["max_val"] == D("200")
        assert r["months_included"] == 2

    async def test_empty_returns_empty(self):
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(make_session(earliest_result(None), mock_result([])))
            result = await svc.category_volatility(BUDGET, months=3)
        assert result["categories"] == []
        # The window is served even when empty: the drill-down needs it.
        assert (result["window_start"], result["window_end"]) == (
            date(2025, 12, 1),
            date(2026, 2, 28),
        )


# ─── seasonality ──────────────────────────────────────────────────────────────


class TestSeasonality:
    async def test_cells_and_categories(self):
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            def srow(d, amt):
                return spend_row(date=d, amount=amt, id=CAT_A, name="Groceries")

            # Two complete months before February: December and January.
            rows = [srow(date(2025, 12, 10), D("-120.00")), srow(date(2026, 1, 10), D("-100.00"))]
            svc = ReportService(make_session(earliest_result(None), mock_result(rows)))
            result = await svc.seasonality(BUDGET, months=2)

        # The axis is the query's window. It used to run through the current
        # month — Jan/Feb here — while the query read Dec/Jan, so February was
        # always a blank column and December's cells had none.
        assert result["months"] == [date(2025, 12, 1), date(2026, 1, 1)]
        assert {c["month"] for c in result["cells"]} <= set(result["months"])
        assert any(c["id"] == CAT_A for c in result["categories"])
        jan_cell = next(c for c in result["cells"] if c["month"] == date(2026, 1, 1))
        assert jan_cell["total"] == D("100.0")

    async def test_the_axis_starts_where_the_history_does(self):
        """A budget three weeks old on "12 months" has one complete month. The
        axis drew eleven blank columns before it, which reads as data loss."""
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 20)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(make_session(earliest_result(date(2026, 1, 28)), mock_result([])))
            result = await svc.seasonality(BUDGET, months=12)

        assert result["months"] == [date(2026, 1, 1)]

    async def test_empty_returns_months_no_cells(self):
        with patch("igab.services.report_day.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(make_session(earliest_result(None), mock_result([])))
            result = await svc.seasonality(BUDGET, months=2)

        assert result["cells"] == []
        assert result["categories"] == []
        assert result["months"] == [date(2025, 12, 1), date(2026, 1, 1)]


# ─── large_transactions ───────────────────────────────────────────────────────


class TestLargeTransactions:
    async def test_returns_correct_fields(self):
        txn_id = uuid.uuid4()
        rows = [
            row(
                id=txn_id,
                date=date(2026, 1, 15),
                amount=D("-500.00"),
                payee_name="Landlord",
                category_name="Rent",
                memo="January rent",
                is_split=False,
                activity_class="spending",
            )
        ]
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.large_transactions(BUDGET, JAN, APR)

        assert len(result) == 1
        t = result[0]
        assert t["id"] == str(txn_id)
        assert t["amount"] == D("-500.00")
        assert t["payee_name"] == "Landlord"
        assert t["category_name"] == "Rent"
        assert t["memo"] == "January rent"

    async def test_carries_the_activity_class(self):
        """A big transfer into savings belongs on a timeline of large
        transactions — it just must not be drawn as an expense."""
        rows = [
            row(
                id=uuid.uuid4(),
                date=date(2026, 1, 15),
                amount=D("-5000.00"),
                payee_name="Transfer : Brokerage",
                category_name="Investments",
                memo=None,
                is_split=False,
                activity_class="savings",
            )
        ]
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.large_transactions(BUDGET, JAN, APR)
        assert result[0]["activity_class"] == "savings"

    async def test_empty(self):
        svc = ReportService(make_session(mock_result([])))
        result = await svc.large_transactions(BUDGET, JAN, APR)
        assert result == []


# account_composition reads the account registry and live accounts itself;
# it is tested against a database in tests/integration/test_tracking_start.py.
