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

from igab.services.report_stats import anomaly_rows, balance_sheet, volatility_stats


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

    def test_months_before_the_first_charge_are_left_out_not_zero(self):
        """Spreading is FORWARD, and the months before a category's first
        charge were paid for by a charge the window never saw. They used to
        count as zero, so a lumpy bill read flat only when the window happened
        to start on one of its charges.
        """
        # Feb and Aug on a Sep–Aug window: the phase that read 0 to 600, the
        # raw range exactly.
        grid = months(*[(2025, m) for m in range(9, 13)], *[(2026, m) for m in range(1, 9)])
        rows = [Row(date(2026, 2, 20), "-600.00"), Row(date(2026, 8, 20), "-600.00")]
        (r,) = volatility_stats(rows, grid, amortize=True)

        assert r["min_val"] == Decimal("100")
        assert r["max_val"] == Decimal("100")
        assert r["mean"] == Decimal("100")
        assert r["std_dev"] == Decimal("0")

    def test_unequal_gaps_spread_to_each_next_charge(self):
        """900 in Jan, Apr and Oct: Jan–Mar read 300, Apr–Sep read 150, and
        Oct keeps its six-month rhythm, 150 over Oct–Dec. A fixed-period
        spread (the window ÷ three charges) reads 0 to 300 and used to pass."""
        rows = [Row(date(2026, m, 20), "-900.00") for m in (1, 4, 10)]
        (r,) = volatility_stats(rows, YEAR, amortize=True)

        assert r["min_val"] == Decimal("150")
        assert r["max_val"] == Decimal("300")
        # (3 × 300 + 9 × 150) / 12
        assert r["mean"] == Decimal("187.5")
        # Sample σ: sqrt((3 × 112.5² + 9 × 37.5²) / 11) = sqrt(50,625 / 11).
        assert r["std_dev"] == pytest.approx(Decimal("67.8401"), abs=Decimal("0.0001"))
        assert r["months_included"] == 3

    def test_a_lumpy_category_beside_a_monthly_one_still_reads_flat(self):
        """The next charge is looked up within the category. A lookup that
        leaked across categories found Groceries' next month as Property Tax's
        next charge and read it 0 to 600."""
        rows = [
            Row(date(2026, 1, 20), "-600.00"),
            Row(date(2026, 7, 20), "-600.00"),
            *[Row(date(2026, m, 10), "-80.00", cid="c2", name="Groceries") for m in range(1, 13)],
        ]
        by_name = {r["category_name"]: r for r in volatility_stats(rows, YEAR, amortize=True)}

        tax = by_name["Property Tax"]
        assert (tax["min_val"], tax["max_val"], tax["std_dev"]) == (
            Decimal("100"),
            Decimal("100"),
            Decimal("0"),
        )
        groceries = by_name["Groceries"]
        assert (groceries["min_val"], groceries["max_val"]) == (Decimal("80"), Decimal("80"))

    def test_a_split_that_does_not_divide_evenly_is_right_to_the_cent(self):
        grid = months(*[(2026, m) for m in range(1, 7)])
        rows = [Row(date(2026, 1, 20), "-1000.00"), Row(date(2026, 4, 20), "-1000.00")]
        (r,) = volatility_stats(rows, grid, amortize=True)

        for field in ("mean", "min_val", "max_val", "p25", "p75"):
            assert r[field] == pytest.approx(Decimal("333.33"), abs=Decimal("0.005")), field

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
        # A lone charge has no rhythm, so it spreads to the end of the window.
        assert single["min_val"] == single["max_val"] == pytest.approx(Decimal("60"))

    def test_a_steady_category_is_unchanged_by_amortizing(self):
        """Nothing to spread: a charge every month already covers one month."""
        rows = [Row(date(2026, m, 10), "-100.00", name="Groceries") for m in range(1, 13)]
        (raw,) = volatility_stats(rows, YEAR)
        (amortized,) = volatility_stats(rows, YEAR, amortize=True)

        assert amortized["mean"] == raw["mean"]
        assert amortized["std_dev"] == raw["std_dev"]
        assert amortized["months_included"] == raw["months_included"]


class TestOnlyTheWindowCounts:
    """Rows outside the grid count nowhere — not in `months_included`, and not
    in the spread. The count was taken off the sparse frame, and the spread
    carried a charge dated before the window into its first months, while the
    comments still promised in-window counting."""

    GRID = months(*[(2026, m) for m in range(1, 7)])

    def test_months_included_ignores_rows_before_and_after(self):
        rows = [
            Row(date(2025, 11, 5), "-100.00"),
            Row(date(2026, 3, 5), "-100.00"),
            Row(date(2026, 8, 5), "-100.00"),
        ]
        for amortize in (False, True):
            (r,) = volatility_stats(rows, self.GRID, amortize=amortize)
            # One charge in the window, so the client's two-month floor drops it.
            assert r["months_included"] == 1, amortize

    def test_a_category_with_no_row_in_the_window_is_absent(self):
        rows = [Row(date(2026, 10, 5), "-100.00")]
        assert volatility_stats(rows, self.GRID) == []
        assert volatility_stats(rows, self.GRID, amortize=True) == []

    def test_a_charge_before_the_window_is_not_spread_into_it(self):
        rows = [Row(date(2025, 12, 5), "-600.00"), Row(date(2026, 3, 5), "-100.00")]

        (raw,) = volatility_stats(rows, self.GRID)
        assert raw["mean"] == pytest.approx(Decimal("16.67"), abs=Decimal("0.005"))

        (spread,) = volatility_stats(rows, self.GRID, amortize=True)
        # March's 100 alone, over Mar–Jun: 25 a month. Carrying December's
        # 600 in read 116.67.
        assert spread["mean"] == Decimal("25")
        assert spread["max_val"] == Decimal("25")


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


class TestAnomalyRows:
    """Which months are scored, and which verdicts survive.

    Every figure is written by hand. The baseline alternates 380/420, so its
    mean is 400 and its population standard deviation is exactly 20 — a spike
    of 1,200 is 40 sigma, and that is checkable on paper. Today is 2026-07-15,
    so July is the month in progress and June the newest complete one.
    """

    BASELINE = ["380", "420", "380", "420", "380", "420"]

    def month_back(self, n: int) -> date:
        month, year = 7 - n, 2026
        while month <= 0:
            month, year = month + 12, year - 1
        return date(year, month, 1)

    def rows(self, complete: list[str], running: str | None = None):
        """One `(category_id, name, group, month, signed_total)` per month:
        `complete` ends with June 2026, `running` lands in July."""
        out = [
            ("c1", "Groceries", "Everyday", self.month_back(len(complete) - i), Decimal(f"-{a}"))
            for i, a in enumerate(complete)
        ]
        if running is not None:
            out.append(("c1", "Groceries", "Everyday", date(2026, 7, 1), Decimal(f"-{running}")))
        return out

    def score(self, rows, threshold: float = 2.0):
        return anomaly_rows(rows, today=date(2026, 7, 15), threshold=threshold)

    def test_a_spike_in_the_month_in_progress_flags_the_day_it_happens(self):
        got = self.score(self.rows(self.BASELINE, running="1200"))

        assert len(got) == 1
        assert got[0]["month"] == date(2026, 7, 1)
        assert got[0]["actual"] == Decimal("1200.00")
        assert got[0]["baseline_mean"] == Decimal("400.00")
        assert got[0]["z_score"] == pytest.approx(40.0)  # (1200 - 400) / 20
        assert got[0]["direction"] == "high"
        assert got[0]["partial_month"] is True

    def test_the_month_in_progress_is_never_flagged_low(self):
        """Spending accumulates, so a month that is not over can only
        understate itself: 12.00 by the 15th is the calendar talking, not a
        collapse. Scored as a full observation it is -19.4 sigma, well past
        every threshold the report offers."""
        assert self.score(self.rows(self.BASELINE, running="12")) == []

    def test_a_complete_month_still_flags_low(self):
        got = self.score(self.rows(["180", "220", "180", "220", "180", "220", "40"]))

        assert len(got) == 1
        assert got[0]["month"] == date(2026, 6, 1)
        assert got[0]["z_score"] == pytest.approx(-8.0)  # (40 - 200) / 20
        assert got[0]["direction"] == "low"
        assert got[0]["partial_month"] is False

    def test_the_month_in_progress_is_in_no_other_months_baseline(self):
        """June's 1,200 is 40 sigma off the six months before it. Let July's
        5.00 into that baseline and the mean falls to 343.57 while the spread
        triples, so June would read about 6 sigma instead."""
        got = self.score(self.rows([*self.BASELINE, "1200"], running="5"))

        assert len(got) == 1
        assert got[0]["month"] == date(2026, 6, 1)
        assert got[0]["baseline_mean"] == Decimal("400.00")
        assert got[0]["z_score"] == pytest.approx(40.0)
        assert got[0]["partial_month"] is False

    def test_the_month_in_progress_needs_six_complete_months_like_any_other(self):
        assert self.score(self.rows(["380", "420", "380", "420", "380"], running="1200")) == []
