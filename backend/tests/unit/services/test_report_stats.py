"""Volatility statistics: the zero-fill and the amortized reading.

Pure — no session, no database. Every expectation is written by hand; the
arithmetic is the thing under test, and the figures are round enough to check
on paper.
"""

from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from igab.services.report_stats import monthly_account_balances, volatility_stats


class Row:
    def __init__(self, d, amount, cid="c1", name="Property Tax", group="Long Term"):
        self.date = d
        self.amount = Decimal(amount)
        self.category_id = cid
        self.category_name = name
        self.group_name = group


def months(*pairs: tuple[int, int]) -> list[date]:
    return [date(y, m, 1) for y, m in pairs]


YEAR = months(*[(2026, m) for m in range(1, 13)])


class TestTheRawReading:
    def test_a_dormant_month_is_a_zero(self):
        # 600 in January and 600 in July, over a twelve-month window.
        rows = [Row(date(2026, 1, 20), "-600.00"), Row(date(2026, 7, 20), "-600.00")]
        (r,) = volatility_stats(rows, YEAR)

        assert r["mean"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["min_val"] == Decimal("0")
        assert r["max_val"] == pytest.approx(Decimal("600.0"), rel=Decimal("0.01"))
        # Ten dormant months and two of 600: a wide spread, honestly reported.
        assert r["std_dev"] > Decimal("200")
        assert r["months_included"] == 2

    def test_a_steady_category_reads_steady(self):
        rows = [Row(date(2026, m, 10), "-100.00", name="Groceries") for m in range(1, 13)]
        (r,) = volatility_stats(rows, YEAR)

        assert r["mean"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["std_dev"] == Decimal("0")
        assert r["months_included"] == 12

    def test_no_rows_is_no_rows(self):
        assert volatility_stats([], YEAR) == []


class TestTheAmortizedReading:
    def test_a_lumpy_bill_with_a_steady_cost_reads_flat(self):
        """The whole point of the toggle.

        A bill paid twice a year has a steady COST and irregular TIMING. The
        raw reading cannot tell that apart from a category whose cost genuinely
        swings — both show a wide spread. Spread each charge forward over the
        months until the next one and this reads a flat 100.
        """
        rows = [Row(date(2026, 1, 20), "-600.00"), Row(date(2026, 7, 20), "-600.00")]
        (r,) = volatility_stats(rows, YEAR, amortize=True)

        # January's 600 over Jan-Jun, July's over Jul-Dec: 100 every month.
        assert r["mean"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["min_val"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["max_val"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["std_dev"] == Decimal("0")

    def test_a_genuinely_variable_category_stays_variable(self):
        """Amortizing must not flatten everything, or the report says nothing.

        Two charges of very different size over equal gaps: the rate really did
        change, and the spread has to survive.
        """
        rows = [
            Row(date(2026, 1, 20), "-600.00", name="Home Repairs"),
            Row(date(2026, 7, 20), "-1800.00", name="Home Repairs"),
        ]
        (r,) = volatility_stats(rows, YEAR, amortize=True)

        # 100/month for six months, then 300/month for six.
        assert r["mean"] == pytest.approx(Decimal("200.0"), rel=Decimal("0.01"))
        assert r["min_val"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["max_val"] == pytest.approx(Decimal("300.0"), rel=Decimal("0.01"))
        assert r["std_dev"] > Decimal("90")

    def test_months_before_the_first_charge_stay_unknown(self):
        """Spreading is FORWARD. The months before a category's first charge
        are months we know nothing about, and back-filling them would invent
        history — and flattening the whole window to `total / 12` would drive
        every standard deviation to zero and make the report say nothing.
        """
        rows = [Row(date(2026, 7, 20), "-600.00")]
        (r,) = volatility_stats(rows, YEAR, amortize=True)

        # 600 over Jul-Dec is 100 a month; Jan-Jun stay zero.
        assert r["min_val"] == Decimal("0")
        assert r["max_val"] == pytest.approx(Decimal("100.0"), rel=Decimal("0.01"))
        assert r["mean"] == pytest.approx(Decimal("50.0"), rel=Decimal("0.01"))

    def test_months_included_still_counts_charges_not_spread_months(self):
        """Spreading one charge across six months must not report six.

        The client drops anything under two months from this report, which is
        what keeps a single annual charge — flat by construction once spread —
        out of a report about variation.
        """
        rows = [Row(date(2026, 1, 20), "-600.00"), Row(date(2026, 7, 20), "-600.00")]
        (r,) = volatility_stats(rows, YEAR, amortize=True)
        assert r["months_included"] == 2

        (single,) = volatility_stats([Row(date(2026, 3, 20), "-600.00")], YEAR, amortize=True)
        assert single["months_included"] == 1

    def test_a_steady_category_is_unchanged_by_amortizing(self):
        """Nothing to spread: a charge every month already covers one month."""
        rows = [Row(date(2026, m, 10), "-100.00", name="Groceries") for m in range(1, 13)]
        (raw,) = volatility_stats(rows, YEAR)
        (amortized,) = volatility_stats(rows, YEAR, amortize=True)

        assert amortized["mean"] == raw["mean"]
        assert amortized["std_dev"] == raw["std_dev"]
        assert amortized["months_included"] == raw["months_included"]


class TestMonthlyAccountBalances:
    """`net_worth_history` used to re-filter and re-group the whole register
    once per point. These pin what the single pass has to reproduce."""

    @staticmethod
    def frame(rows: list[tuple[date, float, str]]) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "date": [r[0] for r in rows],
                "amount": [r[1] for r in rows],
                "account_id": [r[2] for r in rows],
                "account_name": [r[2].title() for r in rows],
                "account_type": ["checking" for _ in rows],
                "classification": ["asset" for _ in rows],
            },
            schema_overrides={"date": pl.Date, "amount": pl.Float64},
        )

    def test_a_balance_is_cumulative_across_the_window(self):
        grid = months((2026, 1), (2026, 2), (2026, 3))
        ends = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
        df = self.frame(
            [
                (date(2026, 1, 10), 1000.0, "checking"),
                (date(2026, 2, 10), -400.0, "checking"),
                (date(2026, 3, 10), 250.0, "checking"),
            ]
        )
        (account,) = monthly_account_balances(df, grid, ends)
        assert account["running"] == [1000.0, 600.0, 850.0]
        assert account["first_month"] == 0

    def test_rows_older_than_the_window_open_the_first_month(self):
        # The opening point is everything that happened up to then, not just
        # that month's activity — a five-year-old savings account does not
        # start the chart at zero.
        grid = months((2026, 2), (2026, 3))
        ends = [date(2026, 2, 28), date(2026, 3, 31)]
        df = self.frame(
            [
                (date(2021, 6, 1), 5000.0, "savings"),
                (date(2026, 3, 2), 100.0, "savings"),
            ]
        )
        (account,) = monthly_account_balances(df, grid, ends)
        assert account["running"] == [5000.0, 5100.0]

    def test_an_account_with_no_rows_yet_is_absent_not_zero(self):
        grid = months((2026, 1), (2026, 2))
        ends = [date(2026, 1, 31), date(2026, 2, 28)]
        df = self.frame(
            [
                (date(2026, 1, 5), 300.0, "checking"),
                (date(2026, 2, 5), 900.0, "brokerage"),
            ]
        )
        by_id = {a["account_id"]: a for a in monthly_account_balances(df, grid, ends)}
        assert by_id["checking"]["first_month"] == 0
        # February's index — January's stack must not carry a brokerage tile.
        assert by_id["brokerage"]["first_month"] == 1

    def test_rows_after_the_last_month_end_are_dropped(self):
        # The newest point is clamped to today, so a future-dated row is not
        # part of "net worth now".
        grid = months(
            (2026, 1),
        )
        ends = [date(2026, 1, 20)]
        df = self.frame(
            [
                (date(2026, 1, 5), 300.0, "checking"),
                (date(2026, 1, 25), 900.0, "checking"),
            ]
        )
        (account,) = monthly_account_balances(df, grid, ends)
        assert account["running"] == [300.0]

    def test_an_empty_grid_claims_nothing(self):
        assert monthly_account_balances(self.frame([]), [], []) == []
