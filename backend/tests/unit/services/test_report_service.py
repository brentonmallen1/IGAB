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

from igab.services.report_service import ReportService, _subtract_months

# ─── Helpers ──────────────────────────────────────────────────────────────────

def D(s: str) -> Decimal:
    return Decimal(s)


def row(**kwargs):
    """SQLAlchemy-style row: supports both attribute access and positional indexing."""
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


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
            row(id=CAT_A, name="Groceries", group_name="Food", amount=D("-60.00")),
            row(id=CAT_A, name="Groceries", group_name="Food", amount=D("-40.00")),
            row(id=CAT_B, name="Gas",       group_name="Transport", amount=D("-25.00")),
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
        rows = [row(id=CAT_A, name="Rent", group_name="Housing", amount=D("-1200.00"))]
        svc = ReportService(make_session(mock_result(rows)))
        cats, total = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats[0]["pct"] == pytest.approx(100.0)

    async def test_amounts_are_absolute(self):
        """Stored as negative; returned totals must be positive."""
        rows = [row(id=CAT_A, name="X", group_name="G", amount=D("-500.00"))]
        svc = ReportService(make_session(mock_result(rows)))
        cats, total = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats[0]["total"] > 0
        assert total > 0

    async def test_sorted_descending_by_total(self):
        rows = [
            row(id=CAT_A, name="Small", group_name="G", amount=D("-10.00")),
            row(id=CAT_B, name="Large", group_name="G", amount=D("-200.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        cats, _ = await svc.spending_by_category(BUDGET, JAN, APR)
        assert cats[0]["name"] == "Large"
        assert cats[1]["name"] == "Small"


# ─── income_vs_expense ────────────────────────────────────────────────────────

class TestIncomeVsExpense:
    """The service now groups by activity class in SQL, so the mocked rows are
    (month, cls, total) rather than raw (date, amount)."""

    @staticmethod
    def _rows(*triples):
        return [row(month=m, cls=c, total=t) for m, c, t in triples]

    async def test_buckets_by_month(self):
        today = date.today()
        first = today.replace(day=1)
        last_month = _subtract_months(first, 1)

        svc = ReportService(
            make_session(
                mock_result(
                    self._rows(
                        (last_month, "income", D("3000.00")),
                        (last_month, "spending", D("-500.00")),
                        (first, "income", D("3000.00")),
                        (first, "spending", D("-800.00")),
                    )
                )
            )
        )
        result = await svc.income_vs_expense(BUDGET, months=2)

        assert len(result) == 2
        prev = next(r for r in result if r["month"] == last_month)
        curr = next(r for r in result if r["month"] == first)

        assert prev["income"] == D("3000.00")
        assert prev["expenses"] == D("500.00")
        assert curr["income"] == D("3000.00")
        assert curr["expenses"] == D("800.00")

    async def test_savings_is_broken_out_of_expenses(self):
        """The point of the change: money moved into savings is not spending."""
        first = date.today().replace(day=1)
        svc = ReportService(
            make_session(
                mock_result(
                    self._rows(
                        (first, "income", D("3000.00")),
                        (first, "spending", D("-800.00")),
                        (first, "savings", D("-1000.00")),
                        (first, "debt_principal", D("-200.00")),
                    )
                )
            )
        )
        result = await svc.income_vs_expense(BUDGET, months=1)
        assert result[0]["expenses"] == D("800.00")
        assert result[0]["savings"] == D("1000.00")
        assert result[0]["debt_principal"] == D("200.00")

    async def test_the_parts_reconcile(self):
        """net must stay income minus everything that left, or a stacked chart
        drifts away from its own total."""
        first = date.today().replace(day=1)
        svc = ReportService(
            make_session(
                mock_result(
                    self._rows(
                        (first, "income", D("3000.00")),
                        (first, "spending", D("-800.00")),
                        (first, "savings", D("-1000.00")),
                        (first, "debt_principal", D("-200.00")),
                    )
                )
            )
        )
        r = (await svc.income_vs_expense(BUDGET, months=1))[0]
        assert r["net"] == r["income"] - r["expenses"] - r["savings"] - r["debt_principal"]
        assert r["net"] == D("1000.00")

    async def test_internal_transfers_are_ignored(self):
        first = date.today().replace(day=1)
        svc = ReportService(
            make_session(
                mock_result(
                    self._rows(
                        (first, "income", D("1000.00")),
                        (first, "transfer_internal", D("-400.00")),
                    )
                )
            )
        )
        r = (await svc.income_vs_expense(BUDGET, months=1))[0]
        assert r["expenses"] == D("0")
        assert r["net"] == D("1000.00")

    async def test_empty_fills_all_months_with_zeros(self):
        svc = ReportService(make_session(mock_result([])))
        result = await svc.income_vs_expense(BUDGET, months=3)
        assert len(result) == 3
        for r in result:
            assert r["income"] == D("0")
            assert r["expenses"] == D("0")
            assert r["savings"] == D("0")
            assert r["net"] == D("0")

    async def test_expenses_are_absolute_values(self):
        first = date.today().replace(day=1)
        svc = ReportService(
            make_session(mock_result(self._rows((first, "spending", D("-300.00")))))
        )
        result = await svc.income_vs_expense(BUDGET, months=1)
        assert result[0]["expenses"] == D("300.00")


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
            category_id=cat_id, month=month, assigned=assigned,
            category_name=cat_name, group_name=group_name,
        )

    def _spend(self, cat_id, amount):
        return row(category_id=cat_id, amount=amount)

    async def test_basic_variance(self):
        assigns = [self._assignment(CAT_A, JAN, D("500.00"))]
        spends  = [self._spend(CAT_A, D("-420.00"))]

        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)

        cat = result["categories"][0]
        assert cat["assigned"] == D("500.00")
        assert cat["spent"] == D("420.00")
        assert cat["variance"] == D("80.00")
        assert cat["variance_pct"] == pytest.approx(16.0)

    async def test_overspend_shows_negative_variance(self):
        assigns = [self._assignment(CAT_A, JAN, D("200.00"))]
        spends  = [self._spend(CAT_A, D("-350.00"))]

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

    async def test_empty_returns_zeros(self):
        svc = ReportService(make_session(mock_result([]), mock_result([])))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)
        assert result == {"categories": [], "total_assigned": D("0"), "total_spent": D("0")}

    async def test_variance_pct_zero_when_no_assignment(self):
        """Category with spending but no assignment gets 0% variance_pct."""
        assigns = []
        spends  = [self._spend(CAT_A, D("-100.00"))]
        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.budget_vs_actual(BUDGET, JAN, JAN)
        assert result["categories"][0]["variance_pct"] == 0.0


# ─── cumulative_variance ──────────────────────────────────────────────────────

class TestCumulativeVariance:
    async def test_cumulative_carries_forward(self):
        # Use real current dates to avoid patching the date class (which breaks isinstance).
        today = date.today()
        first = today.replace(day=1)
        m1 = _subtract_months(first, 1)  # last month
        m2 = first  # current month

        assigns = [
            row(month=m1, assigned=D("500.00")),
            row(month=m2, assigned=D("500.00")),
        ]
        spends = [
            row(date=m1.replace(day=15), amount=D("-400.00")),
            row(date=m2.replace(day=10), amount=D("-600.00")),
        ]
        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.cumulative_variance(BUDGET, months=2)

        assert len(result) == 2
        r0 = next(r for r in result if r["month"] == m1)
        r1 = next(r for r in result if r["month"] == m2)
        assert r0["monthly_variance"] == D("100.00")
        assert r0["cumulative_variance"] == D("100.00")
        assert r1["monthly_variance"] == D("-100.00")
        assert r1["cumulative_variance"] == D("0.00")

    async def test_months_with_no_data_count_as_zero(self):
        today = date.today()
        first = today.replace(day=1)
        m1 = _subtract_months(first, 1)
        m2 = first

        assigns = [row(month=m1, assigned=D("400.00"))]
        spends = []
        svc = ReportService(make_session(mock_result(assigns), mock_result(spends)))
        result = await svc.cumulative_variance(BUDGET, months=2)

        r1 = next(r for r in result if r["month"] == m1)
        r2 = next(r for r in result if r["month"] == m2)
        assert r1["monthly_variance"] == D("400.00")
        assert r2["monthly_variance"] == D("0.00")
        assert r2["cumulative_variance"] == D("400.00")


# ─── spending_grouped ─────────────────────────────────────────────────────────

class TestSpendingGrouped:
    async def test_basic_grouping(self):
        rows = [
            row(id=CAT_A, name="Groceries", group_id=GRP_1, group_name="Food", amount=D("-100.00"), cls="spending"),
            row(id=CAT_A, name="Groceries", group_id=GRP_1, group_name="Food", amount=D("-50.00"), cls="spending"),
            row(id=CAT_B, name="Gas", group_id=GRP_2, group_name="Transport", amount=D("-75.00"), cls="spending"),
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
            row(id=CAT_A, name="X", group_id=GRP_1, group_name="G1", amount=D("-300.00"), cls="spending"),
            row(id=CAT_B, name="Y", group_id=GRP_1, group_name="G1", amount=D("-100.00"), cls="spending"),
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

class TestDayPatterns:
    async def test_seven_days_always_returned(self):
        svc = ReportService(make_session(mock_result([])))
        result = await svc.day_patterns(BUDGET, JAN, APR)
        assert len(result) == 7
        assert {r["day_of_week"] for r in result} == set(range(7))

    async def test_day_names_correct(self):
        svc = ReportService(make_session(mock_result([])))
        result = await svc.day_patterns(BUDGET, JAN, APR)
        by_idx = {r["day_of_week"]: r["day_name"] for r in result}
        assert by_idx[0] == "Monday"
        assert by_idx[6] == "Sunday"

    async def test_aggregation_by_weekday(self):
        # 2026-01-05 is a Monday, 2026-01-06 is Tuesday
        rows = [
            row(date=date(2026, 1, 5), amount=D("-100.00")),
            row(date=date(2026, 1, 5), amount=D("-50.00")),
            row(date=date(2026, 1, 6), amount=D("-200.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.day_patterns(BUDGET, JAN, APR)

        monday = next(r for r in result if r["day_name"] == "Monday")
        tuesday = next(r for r in result if r["day_name"] == "Tuesday")
        assert monday["total"] == D("150.0")
        assert monday["count"] == 2
        assert tuesday["total"] == D("200.0")

    async def test_avg_transaction(self):
        rows = [
            row(date=date(2026, 1, 5), amount=D("-100.00")),
            row(date=date(2026, 1, 5), amount=D("-200.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.day_patterns(BUDGET, JAN, APR)
        monday = next(r for r in result if r["day_name"] == "Monday")
        assert monday["avg_transaction"] == pytest.approx(D("150.0"), rel=D("0.01"))

    async def test_empty_days_return_zero_not_missing(self):
        rows = [row(date=date(2026, 1, 5), amount=D("-100.00"))]  # Monday only
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.day_patterns(BUDGET, JAN, APR)
        sunday = next(r for r in result if r["day_name"] == "Sunday")
        assert sunday["total"] == D("0")
        assert sunday["count"] == 0


# ─── payee_analysis ───────────────────────────────────────────────────────────

class TestPayeeAnalysis:
    def _txn(self, txn_date, amount, payee_id=None, payee_name="Amazon", cat_name="Shopping"):
        return row(
            date=txn_date,
            amount=amount,
            payee_id=payee_id or PAYEE_1,
            payee_name=payee_name,
            category_id=CAT_A,
            category_name=cat_name,
        )

    async def test_is_recurring_three_or_more_months(self):
        rows = [
            self._txn(date(2026, 1, 15), D("-50.00")),
            self._txn(date(2026, 2, 15), D("-50.00")),
            self._txn(date(2026, 3, 15), D("-50.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        payees, _ = await svc.payee_analysis(BUDGET, JAN, APR)
        assert payees[0]["is_recurring"] is True

    async def test_not_recurring_two_months(self):
        rows = [
            self._txn(date(2026, 1, 15), D("-50.00")),
            self._txn(date(2026, 2, 15), D("-50.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        payees, _ = await svc.payee_analysis(BUDGET, JAN, APR)
        assert payees[0]["is_recurring"] is False

    async def test_monthly_trend(self):
        rows = [
            self._txn(date(2026, 1, 10), D("-100.00")),
            self._txn(date(2026, 1, 20), D("-50.00")),
            self._txn(date(2026, 2, 5),  D("-75.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        payees, _ = await svc.payee_analysis(BUDGET, JAN, APR)

        trend = {t["month"]: t["total"] for t in payees[0]["monthly_trend"]}
        assert trend[date(2026, 1, 1)] == D("150.0")
        assert trend[date(2026, 2, 1)] == D("75.0")

    async def test_total_and_count(self):
        rows = [
            self._txn(date(2026, 1, 1), D("-100.00")),
            self._txn(date(2026, 1, 2), D("-200.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        payees, grand_total = await svc.payee_analysis(BUDGET, JAN, APR)
        assert payees[0]["total"] == D("300.0")
        assert payees[0]["count"] == 2
        assert grand_total == D("300.0")

    async def test_top_categories(self):
        rows = [
            self._txn(date(2026, 1, 1), D("-100.00"), cat_name="Groceries"),
            self._txn(date(2026, 1, 2), D("-300.00"), cat_name="Electronics"),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        payees, _ = await svc.payee_analysis(BUDGET, JAN, APR)
        top = {c["category_name"]: c["total"] for c in payees[0]["top_categories"]}
        assert top["Electronics"] == D("300.0")
        assert top["Groceries"] == D("100.0")

    async def test_empty_returns_empty(self):
        svc = ReportService(make_session(mock_result([])))
        payees, total = await svc.payee_analysis(BUDGET, JAN, APR)
        assert payees == []
        assert total == D("0")


# ─── burn_rate ────────────────────────────────────────────────────────────────

class TestBurnRate:
    # The rolling windows end at the CURRENT MONTH'S last day, so anchor test
    # dates to month_end (dates relative to today drift out of the window as
    # the month progresses and made these tests calendar-flaky).
    @staticmethod
    def _month_end() -> date:
        first = date.today().replace(day=1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        return next_month - timedelta(days=1)

    async def test_rolling_30_sums_last_30_days(self):
        month_end = self._month_end()
        rows = [
            row(date=month_end - timedelta(days=25), amount=D("-200.00")),
            row(date=month_end - timedelta(days=3), amount=D("-300.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.burn_rate(BUDGET, months=1)

        cur = result[0]
        assert cur["rolling_30"] == D("500.0")

    async def test_rolling_90_is_divided_by_3(self):
        month_end = self._month_end()
        # 900 total inside the 90-day window → monthly equivalent = 300
        rows = [
            row(date=month_end - timedelta(days=85), amount=D("-300.00")),
            row(date=month_end - timedelta(days=50), amount=D("-300.00")),
            row(date=month_end - timedelta(days=10), amount=D("-300.00")),
        ]
        svc = ReportService(make_session(mock_result(rows)))
        result = await svc.burn_rate(BUDGET, months=1)

        cur = result[0]
        assert cur["rolling_90"] == pytest.approx(D("300.0"), rel=D("0.01"))


# ─── net_worth_history ────────────────────────────────────────────────────────

class TestNetWorthHistory:
    def _account(self, acct_id, acct_type, name="Account", classification="asset"):
        if acct_type in ("credit_card", "loan", "other_liability"):
            classification = "liability"
        return row(id=acct_id, name=name, account_type=acct_type, classification=classification)

    def _txn(self, txn_date, amount, acct_id):
        return row(date=txn_date, amount=amount, account_id=acct_id)

    async def test_checking_positive_balance_is_asset(self):
        accounts = [self._account(ACCT_1, "checking", "Checking")]
        txns = [self._txn(date(2026, 1, 1), D("5000.00"), ACCT_1)]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=1)

        assert result[0]["total_assets"] == D("5000.00")
        assert result[0]["total_liabilities"] == D("0")
        assert result[0]["net_worth"] == D("5000.00")

    async def test_credit_card_negative_balance_is_liability(self):
        accounts = [self._account(ACCT_1, "credit_card", "Visa")]
        # Credit card with -1500 balance (owed)
        txns = [self._txn(date(2026, 1, 1), D("-1500.00"), ACCT_1)]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=1)

        assert result[0]["total_liabilities"] == D("1500.00")
        assert result[0]["total_assets"] == D("0")
        assert result[0]["net_worth"] == D("-1500.00")

    async def test_mixed_assets_and_liabilities(self):
        accounts = [
            self._account(ACCT_1, "checking", "Checking"),
            self._account(ACCT_2, "credit_card", "Visa"),
        ]
        txns = [
            self._txn(date(2026, 1, 1), D("10000.00"), ACCT_1),
            self._txn(date(2026, 1, 1), D("-2000.00"), ACCT_2),
        ]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=1)

        assert result[0]["total_assets"] == D("10000.00")
        assert result[0]["total_liabilities"] == D("2000.00")
        assert result[0]["net_worth"] == D("8000.00")

    async def test_empty_budget_returns_zero_points(self):
        svc = ReportService(make_session(mock_result([]), mock_result([]), mock_result([])))
        result = await svc.net_worth_history(BUDGET, months=3)
        assert len(result) == 3
        assert all(p["net_worth"] == D("0") for p in result)

    async def test_off_budget_accounts_are_included(self):
        """The balance sheet spans every account — a brokerage and an
        off-budget mortgage must both move net worth."""
        brokerage = uuid.uuid4()
        mortgage = uuid.uuid4()
        accounts = [
            self._account(ACCT_1, "checking", "Checking"),
            self._account(brokerage, "investment", "Brokerage"),
            self._account(mortgage, "loan", "Mortgage"),
        ]
        txns = [
            self._txn(date(2026, 1, 1), D("1000.00"), ACCT_1),
            self._txn(date(2026, 1, 1), D("12000.00"), brokerage),
            self._txn(date(2026, 1, 1), D("-250000.00"), mortgage),
        ]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=1)

        assert result[0]["total_assets"] == D("13000.00")
        assert result[0]["total_liabilities"] == D("250000.00")
        assert result[0]["net_worth"] == D("-237000.00")

    async def test_overdrawn_checking_nets_assets_down(self):
        """The old type-bucketing counted a negative checking balance in
        NEITHER pile; classification math keeps the identity exact."""
        accounts = [
            self._account(ACCT_1, "checking", "Checking"),
            self._account(ACCT_2, "savings", "Savings"),
        ]
        txns = [
            self._txn(date(2026, 1, 1), D("-300.00"), ACCT_1),
            self._txn(date(2026, 1, 1), D("1000.00"), ACCT_2),
        ]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=1)

        assert result[0]["total_assets"] == D("700.00")
        assert result[0]["total_liabilities"] == D("0")
        assert result[0]["net_worth"] == D("700.00")

    async def test_overpaid_credit_card_nets_liabilities_down(self):
        accounts = [
            self._account(ACCT_1, "credit_card", "Visa"),
            self._account(ACCT_2, "loan", "Car"),
        ]
        txns = [
            self._txn(date(2026, 1, 1), D("50.00"), ACCT_1),  # credit on the card
            self._txn(date(2026, 1, 1), D("-1050.00"), ACCT_2),
        ]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=1)

        assert result[0]["total_assets"] == D("0")
        assert result[0]["total_liabilities"] == D("1000.00")
        assert result[0]["net_worth"] == D("-1000.00")

    async def test_cumulative_balance_at_month_end(self):
        """Balance at each month snapshot is cumulative (all txns up to that date)."""
        accounts = [self._account(ACCT_1, "checking")]
        txns = [
            self._txn(date(2026, 1, 1), D("1000.00"), ACCT_1),
            self._txn(date(2026, 2, 1), D("1000.00"), ACCT_1),
        ]

        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(
                make_session(mock_result(accounts), mock_result([]), mock_result(txns))
            )
            result = await svc.net_worth_history(BUDGET, months=2)

        jan_r = next(r for r in result if r["date"].month == 1)
        feb_r = next(r for r in result if r["date"].month == 2)
        assert jan_r["net_worth"] == D("1000.00")
        assert feb_r["net_worth"] == D("2000.00")


# ─── category_volatility ──────────────────────────────────────────────────────

class TestCategoryVolatility:
    async def test_statistical_output(self):
        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            def vrow(d, amt):
                return row(
                    date=d, amount=amt, category_id=CAT_A,
                    category_name="Groceries", group_name="Food",
                )

            rows = [
                vrow(date(2026, 1, 15), D("-100.00")),
                vrow(date(2026, 2, 15), D("-200.00")),
                vrow(date(2026, 3, 15), D("-150.00")),
            ]
            svc = ReportService(make_session(mock_result(rows)))
            result = await svc.category_volatility(BUDGET, months=3)

        assert len(result) == 1
        r = result[0]
        assert r["category_name"] == "Groceries"
        assert r["mean"] == pytest.approx(D("150.0"), rel=D("0.01"))
        assert r["min_val"] == pytest.approx(D("100.0"), rel=D("0.01"))
        assert r["max_val"] == pytest.approx(D("200.0"), rel=D("0.01"))
        assert r["months_included"] == 3

    async def test_empty_returns_empty(self):
        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 31)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(make_session(mock_result([])))
            result = await svc.category_volatility(BUDGET, months=3)
        assert result == []


# ─── seasonality ──────────────────────────────────────────────────────────────

class TestSeasonality:
    async def test_cells_and_categories(self):
        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            def srow(d, amt):
                return row(date=d, amount=amt, category_id=CAT_A, category_name="Groceries")

            rows = [srow(date(2026, 1, 10), D("-100.00")), srow(date(2026, 2, 10), D("-120.00"))]
            svc = ReportService(make_session(mock_result(rows)))
            result = await svc.seasonality(BUDGET, months=2)

        assert len(result["months"]) == 2
        assert any(c["id"] == str(CAT_A) for c in result["categories"])
        cells = result["cells"]
        jan_cell = next((c for c in cells if c["month"].month == 1), None)
        assert jan_cell is not None
        assert jan_cell["total"] == D("100.0")

    async def test_empty_returns_months_no_cells(self):
        with patch("igab.services.report_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            svc = ReportService(make_session(mock_result([])))
            result = await svc.seasonality(BUDGET, months=2)

        assert result["cells"] == []
        assert result["categories"] == []
        assert len(result["months"]) == 2


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


# ─── account_composition ──────────────────────────────────────────────────────

class TestAccountComposition:
    async def test_groups_by_account_type(self):
        # account_composition delegates to net_worth_history and reshapes
        history = [
            {
                "date": JAN,
                "total_assets": D("10000"),
                "total_liabilities": D("2000"),
                "net_worth": D("8000"),
                "accounts": [
                    {"account_type": "checking", "balance": D("6000"),
                     "account_id": str(ACCT_1), "account_name": "Bank"},
                    {"account_type": "savings", "balance": D("4000"),
                     "account_id": str(ACCT_2), "account_name": "Savings"},
                    {"account_type": "credit_card", "balance": D("-2000"),
                     "account_id": str(uuid.uuid4()), "account_name": "Visa"},
                    # Custom types must appear as their own series
                    {"account_type": "pension", "balance": D("9000"),
                     "account_id": str(uuid.uuid4()), "account_name": "Work Pension"},
                ],
            }
        ]
        svc = ReportService(AsyncMock())
        svc.net_worth_history = AsyncMock(return_value=history)

        result = await svc.account_composition(BUDGET, months=1)
        assert len(result) == 1
        balances = result[0]["balances"]
        assert balances["checking"] == D("6000")
        assert balances["savings"] == D("4000")
        assert balances["credit_card"] == D("-2000")
        assert balances["pension"] == D("9000")
        # Absent types stay absent — the series set is exactly what exists
        assert "loan" not in balances
