"""Volatility statistics, and the balance sheet net worth is read from.

Pure — no session, no database. Every expectation is written by hand; the
arithmetic is the thing under test, and the figures are round enough to check
on paper.
"""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from igab.services.report_stats import balance_sheet, volatility_stats


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


class TestBalanceSheet:
    """Net worth at one cutoff, from each account's balances there. Moved
    here from mocked-session tests of `net_worth_history`: the composition is
    pure, and a mock only returned whatever the test made up."""

    @staticmethod
    def account(name: str, classification: str | None = "asset", **kw) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid.uuid4(),
            name=name,
            account_type=kw.get("type", "checking"),
            classification=classification,
        )

    @staticmethod
    def sheet(pairs, i=0, stated=Decimal("0"), unmanaged=Decimal("0")) -> dict:
        accounts = [a for a, _ in pairs]
        balances = {a.id: (0, [Decimal(v) for v in vals]) for a, vals in pairs}
        return balance_sheet(accounts, balances, i, stated, unmanaged)

    def test_an_asset_balance_is_an_asset(self):
        got = self.sheet([(self.account("Checking"), ["5000"])])
        assert (got["total_assets"], got["total_liabilities"], got["net_worth"]) == (
            Decimal("5000"),
            Decimal("0"),
            Decimal("5000"),
        )

    def test_a_card_owing_is_a_liability(self):
        got = self.sheet([(self.account("Sapphire Visa", "liability"), ["-1500"])])
        assert (got["total_assets"], got["total_liabilities"], got["net_worth"]) == (
            Decimal("0"),
            Decimal("1500"),
            Decimal("-1500"),
        )

    def test_an_overdrawn_checking_account_nets_assets_down(self):
        """The old type-bucketing counted a negative checking balance in
        NEITHER pile; classification math keeps the identity exact."""
        got = self.sheet(
            [(self.account("Checking"), ["-300"]), (self.account("Savings"), ["1000"])]
        )
        assert (got["total_assets"], got["net_worth"]) == (Decimal("700"), Decimal("700"))

    def test_an_overpaid_card_nets_liabilities_down(self):
        got = self.sheet(
            [
                (self.account("Sapphire Visa", "liability"), ["50"]),
                (self.account("Car", "liability"), ["-1050"]),
            ]
        )
        assert (got["total_assets"], got["total_liabilities"], got["net_worth"]) == (
            Decimal("0"),
            Decimal("1000"),
            Decimal("-1000"),
        )

    def test_no_classification_reads_as_an_asset(self):
        got = self.sheet([(self.account("Cash", None), ["40"])])
        assert got["total_assets"] == Decimal("40")
        assert got["accounts"][0]["classification"] == "asset"

    def test_stated_values_join_their_side_without_a_tile(self):
        """A stated house raises assets and an unmanaged debt raises
        liabilities; neither is an account, so both are served beside the
        totals for the chart's footnote."""
        got = self.sheet(
            [(self.account("Checking"), ["1000"])],
            stated=Decimal("300000"),
            unmanaged=Decimal("240000"),
        )
        assert got["total_assets"] == Decimal("301000")
        assert got["total_liabilities"] == Decimal("240000")
        assert got["net_worth"] == Decimal("61000")
        assert (got["asset_value_total"], got["unmanaged_liability_total"]) == (
            Decimal("300000"),
            Decimal("240000"),
        )
        assert len(got["accounts"]) == 1

    def test_an_account_before_its_first_row_is_absent_not_zero(self):
        checking, brokerage = self.account("Checking"), self.account("Brokerage")
        balances = {
            checking.id: (0, [Decimal("300"), Decimal("300")]),
            brokerage.id: (1, [Decimal("0"), Decimal("900")]),
        }
        jan = balance_sheet([checking, brokerage], balances, 0, Decimal("0"), Decimal("0"))
        feb = balance_sheet([checking, brokerage], balances, 1, Decimal("0"), Decimal("0"))
        assert [a["account_name"] for a in jan["accounts"]] == ["Checking"]
        assert [a["account_name"] for a in feb["accounts"]] == ["Checking", "Brokerage"]

    def test_an_account_with_no_rows_at_all_is_absent(self):
        got = balance_sheet([self.account("Unused")], {}, 0, Decimal("0"), Decimal("0"))
        assert got["accounts"] == [] and got["net_worth"] == Decimal("0")
