"""Plan vs Spent's fold: the matrix, its totals row and its Total column, from
one ledger (`services.plan_vs_spent`).

Budget vs Actual, Cumulative Variance and Plan vs Reality were three reports
over this dataset. These tests hold the one report to what each of them
served — the Total column is a Budget vs Actual row, the totals row a
Cumulative Variance point — and pin the one place the two totals legitimately
differ: which grain the plan floors at.
"""

import random
import uuid
from datetime import date
from decimal import Decimal as D

from igab.domain.dates import ReportWindow
from igab.services.plan_ledger import PlanCategory, PlanMonth
from igab.services.plan_vs_spent import budget_vs_actual, plan_vs_spent, window_total

JUN, JUL, AUG, SEP = date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)
#: Three complete months and September running.
WINDOW = ReportWindow((JUN, JUL, AUG), SEP)


def cat(name: str, cells: dict[date, PlanMonth], *, sinking: bool = False) -> PlanCategory:
    return PlanCategory(uuid.uuid4(), name, "Everyday", sinking, dict(cells))


def m(assigned="0", spent="0", moved_in="0", moved_out="0") -> PlanMonth:
    return PlanMonth(
        assigned=D(assigned), moved_in=D(moved_in), moved_out=D(moved_out), spent=D(spent)
    )


def ledger(*cats: PlanCategory) -> dict[uuid.UUID, PlanCategory]:
    return {c.category_id: c for c in cats}


def row(report: dict, name: str) -> dict:
    return next(c for c in report["categories"] if c["category_name"] == name)


def floor_gap_bound(led: dict, months) -> D:
    """The plan each month's floor threw away, summed: how far the month-grain
    running total may sit above the window-grain total variance."""
    return sum(
        (
            max(cell.moved_out - cell.assigned - cell.moved_in, D("0"))
            for c in led.values()
            for mo, cell in c.months.items()
            if mo in months
        ),
        D("0"),
    )


class TestTheTotalsRow:
    """Each month over every category — what Cumulative Variance served."""

    def test_a_month_total_is_its_cells_summed(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "400"), JUL: m("500", "600")}),
            cat("Fuel", {JUN: m("100", "150"), JUL: m("100", "100")}),
        )
        jun, jul, aug, sep = plan_vs_spent(led, WINDOW)["month_totals"]
        assert (jun["plan"], jun["spent"], jun["variance"]) == (D("600"), D("550"), D("50"))
        assert (jul["plan"], jul["spent"], jul["variance"]) == (D("600"), D("700"), D("-100"))
        assert (aug["plan"], aug["spent"], aug["variance"]) == (D("0"), D("0"), D("0"))
        assert jun["cumulative_variance"] == D("50")
        assert jul["cumulative_variance"] == D("-50")
        assert aug["cumulative_variance"] == D("-50")
        assert (sep["partial_month"], sep["cumulative_variance"]) == (True, None)

    def test_it_counts_the_categories_over_each_month(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "600"), JUL: m("500", "600")}),
            cat("Fuel", {JUN: m("100", "150")}),
            # A few cents over is on plan, and not counted.
            cat("Power", {JUN: m("80", "80.40")}),
        )
        jun, jul, aug, _ = plan_vs_spent(led, WINDOW)["month_totals"]
        assert (jun["categories_over"], jul["categories_over"], aug["categories_over"]) == (
            2,
            1,
            0,
        )

    def test_the_running_month_is_drawn_and_counted_in_no_verdict(self):
        """Its whole assignment is in on the 1st while its spending arrives
        over thirty days: in the running total it leapt "under budget" every
        1st, and a week-old month is neither over nor under yet."""
        led = ledger(cat("Groceries", {AUG: m("400", "400"), SEP: m("900", "1000")}))
        report = plan_vs_spent(led, WINDOW)
        *_, aug, sep = report["month_totals"]
        assert aug["cumulative_variance"] == D("0")
        assert (sep["assigned"], sep["spent"], sep["variance"]) == (D("900"), D("1000"), D("-100"))
        assert sep["categories_over"] == 0
        assert sep["cumulative_variance"] is None
        g = row(report, "Groceries")
        assert g["monthly"][-1]["over"] is False
        assert g["months_over"] == 0
        # The Total column is the complete months alone.
        assert g["total"]["spent"] == D("400")
        assert report["total_spent"] == D("400")


class TestTheTotalColumn:
    """Each category over the complete months — what Budget vs Actual
    served, floored once over the window's sums."""

    def test_it_is_the_budget_vs_actual_row_for_the_complete_months(self):
        cells = {JUN: m("500", "420", moved_in="50"), JUL: m("500", "700"), SEP: m("500", "90")}
        report = plan_vs_spent(ledger(cat("Groceries", cells)), WINDOW)
        complete = {k: v for k, v in cells.items() if k != SEP}
        bva = budget_vs_actual(ledger(cat("Groceries", complete)))
        (served,) = bva["categories"]
        total = row(report, "Groceries")["total"]
        for key in ("assigned", "moved_in", "moved_out", "plan", "spent", "variance", "over"):
            assert total[key] == served[key], key
        assert total == {
            "assigned": D("1000"),
            "moved_in": D("50"),
            "moved_out": D("0"),
            "plan": D("1050"),
            "spent": D("1120"),
            "variance": D("-70"),
            "variance_pct": float(D("-70") / D("1050") * 100),
            "over": True,
        }

    def test_the_window_totals_are_the_column_summed(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "400"), JUL: m("500", "600")}),
            cat("Fuel", {JUN: m("100", "150", moved_out="20")}),
            cat("Gifts", {JUL: m("-300")}),
        )
        report = plan_vs_spent(led, WINDOW)
        totals = [c["total"] for c in report["categories"]]
        for key in ("assigned", "moved_in", "moved_out", "plan", "spent", "variance"):
            assert report[f"total_{key}"] == sum((t[key] for t in totals), D("0")), key
        assert report["total_plan"] - report["total_spent"] == report["total_variance"]

    def test_spent_and_assigned_agree_with_the_totals_row_exactly(self):
        """Spent and assigned are linear, so the totals row and the Total
        column cannot differ on them, floor or no floor."""
        led = ledger(
            cat("Groceries", {JUN: m("500", "400"), JUL: m("-200", "600")}),
            cat("Fuel", {JUN: m("100", "150", moved_out="300")}),
        )
        report = plan_vs_spent(led, WINDOW)
        complete = [t for t in report["month_totals"] if not t["partial_month"]]
        for key in ("assigned", "moved_in", "moved_out", "spent"):
            assert report[f"total_{key}"] == sum((t[key] for t in complete), D("0")), key

    def test_a_category_active_only_in_the_running_month_is_a_row_with_a_quiet_total(self):
        report = plan_vs_spent(ledger(cat("New envelope", {SEP: m("200", "40")})), WINDOW)
        total = row(report, "New envelope")["total"]
        assert (total["plan"], total["spent"], total["variance"], total["over"]) == (
            D("0"),
            D("0"),
            D("0"),
            False,
        )

    def test_a_quiet_category_is_no_row(self):
        report = plan_vs_spent(ledger(cat("Nothing", {JUN: m()})), WINDOW)
        assert report["categories"] == []
        assert report["total_variance"] == D("0")


class TestTheTwoGrains:
    """The one place the totals row and the Total column may differ, stated
    at `services.plan_vs_spent` and bounded here."""

    def test_they_agree_when_no_month_planned_below_zero(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "400"), JUL: m("500", "600"), AUG: m("0", "80")}),
            cat("Medical", {JUL: m("0", "2000", moved_in="2000")}),
            cat("Mortgage", {JUN: m("1500", moved_out="1500")}),
        )
        report = plan_vs_spent(led, WINDOW)
        *_, last, _running = report["month_totals"]
        assert last["cumulative_variance"] == report["total_variance"]

    def test_money_taken_back_the_next_month_is_under_plan_by_month_and_on_plan_by_window(self):
        """300 assigned in June and moved back out in July, nothing spent. June
        alone reads 300 under; July's plan floors at zero, so the month grain
        never sees the assignment the move undid. The window sees both."""
        led = ledger(cat("Gifts", {JUN: m("300"), JUL: m("-300")}))
        report = plan_vs_spent(led, WINDOW)
        *_, aug, _running = report["month_totals"]
        assert aug["cumulative_variance"] == D("300")
        assert report["total_variance"] == D("0")
        assert row(report, "Gifts")["total"]["plan"] == D("0")
        assert aug["cumulative_variance"] - report["total_variance"] == floor_gap_bound(
            led, WINDOW.complete
        )

    def test_the_gap_is_never_negative_and_never_past_what_the_floors_threw_away(self):
        rng = random.Random(20260927)
        for _ in range(300):
            cats = []
            for i in range(rng.randint(1, 4)):
                cells = {}
                for mo in WINDOW.axis:
                    if rng.random() < 0.3:
                        continue
                    cells[mo] = m(
                        str(rng.choice([-400, -100, 0, 0, 100, 250, 500])),
                        str(rng.choice([-20, 0, 0, 90, 300, 600])),
                        moved_in=str(rng.choice([0, 0, 0, 200])),
                        moved_out=str(rng.choice([0, 0, 0, 150, 700])),
                    )
                cats.append(cat(f"c{i}", cells))
            led = ledger(*cats)
            report = plan_vs_spent(led, WINDOW)
            complete = [t for t in report["month_totals"] if not t["partial_month"]]
            gap = complete[-1]["cumulative_variance"] - report["total_variance"]
            bound = floor_gap_bound(led, WINDOW.complete)
            assert D("0") <= gap <= bound
            if bound == D("0"):
                assert gap == D("0")


class TestChronic:
    def test_over_in_three_of_the_last_six_complete_months_is_chronic(self):
        window = ReportWindow(tuple(date(2026, k, 1) for k in range(3, 9)), SEP)
        over = {date(2026, k, 1): m("100", "200") for k in (4, 6, 8)}
        report = plan_vs_spent(ledger(cat("Dining", over)), window)
        dining = row(report, "Dining")
        assert (dining["chronic"], dining["months_over"], dining["months_active"]) == (
            True,
            3,
            3,
        )
        assert dining["avg_overspend"] == D("100.00")
        assert report["chronic_count"] == 1

    def test_a_sinking_fund_paying_its_bill_is_never_chronic(self):
        bills = {mo: m("100", "400") for mo in (JUN, JUL, AUG)}
        report = plan_vs_spent(ledger(cat("Car insurance", bills, sinking=True)), WINDOW)
        fund = row(report, "Car insurance")
        assert (fund["chronic"], fund["months_over"], fund["sinking_fund"]) == (False, 3, True)
        assert report["chronic_count"] == 0

    def test_a_running_month_over_does_not_make_it_chronic(self):
        cells = {JUL: m("100", "200"), AUG: m("100", "200"), SEP: m("100", "900")}
        report = plan_vs_spent(ledger(cat("Dining", cells)), WINDOW)
        assert row(report, "Dining")["chronic"] is False

    def test_chronic_sorts_first(self):
        window = ReportWindow(tuple(date(2026, k, 1) for k in range(3, 9)), SEP)
        led = ledger(
            cat("Big spender", {date(2026, 3, 1): m("0", "5000")}),
            cat("Habit", {date(2026, k, 1): m("10", "50") for k in (6, 7, 8)}),
        )
        names = [c["category_name"] for c in plan_vs_spent(led, window)["categories"]]
        assert names == ["Habit", "Big spender"]


class TestTheWindow:
    def test_a_budget_with_no_complete_month_has_no_totals_window(self):
        window = ReportWindow((), SEP)
        report = plan_vs_spent(ledger(cat("Groceries", {SEP: m("500", "40")})), window)
        assert (report["totals_start"], report["totals_end"]) == (None, None)
        assert report["months"] == [SEP]
        assert report["total_spent"] == D("0")

    def test_the_totals_window_is_the_complete_months(self):
        report = plan_vs_spent(ledger(), WINDOW)
        assert (report["totals_start"], report["totals_end"]) == (JUN, date(2026, 8, 31))
        assert report["running_month"] == SEP


class TestWindowTotal:
    def test_a_drained_envelope_is_on_plan_not_over(self):
        """A negative assignment with nothing spent: `0 > -300` once read it
        as a 300 overrun."""
        t = window_total(m("-300"))
        assert (t["plan"], t["variance"], t["over"], t["variance_pct"]) == (
            D("0"),
            D("0"),
            False,
            None,
        )

    def test_spending_with_no_plan_has_no_percentage(self):
        t = window_total(m("0", "100"))
        assert (t["variance"], t["variance_pct"], t["over"]) == (D("-100"), None, True)

    def test_refunds_beating_spending_leave_room(self):
        t = window_total(m("100", "-20"))
        assert (t["variance"], t["over"]) == (D("120"), False)
