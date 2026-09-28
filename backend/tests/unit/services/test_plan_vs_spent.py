"""Plan vs Spent's fold: the matrix, its totals row and its Total column, from
one ledger and the budget page's balances (`services.plan_vs_spent`).

Carryover counts: a month carries in what the one before left, and is over
only when the envelope went negative. The balances handed in stand for
`BudgetService.envelope_series` and are the budget page's own walk
(`carryover.monthly_end_balances`) over the same cells; every expected figure
is written by hand.
"""

import random
import uuid
from datetime import date
from decimal import Decimal as D

from igab.domain.carryover import available_at, monthly_end_balances
from igab.domain.dates import ReportWindow, add_months
from igab.domain.plan import plan_effect
from igab.services.plan_ledger import PlanCategory, PlanMonth
from igab.services.plan_vs_spent import budget_vs_actual, plan_vs_spent

JUN, JUL, AUG, SEP = date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)
#: Three complete months and September running.
WINDOW = ReportWindow((JUN, JUL, AUG), SEP)
#: Six complete months, January to June 2026, and July running — the reproduction's window.
H1 = [date(2026, k, 1) for k in range(1, 8)]
HALF_YEAR = ReportWindow(tuple(H1[:6]), H1[6])


def cat(name: str, cells: dict[date, PlanMonth], *, sinking: bool = False) -> PlanCategory:
    return PlanCategory(uuid.uuid4(), name, "Everyday", sinking, dict(cells))


def m(assigned="0", spent="0", moved_in="0", moved_out="0") -> PlanMonth:
    return PlanMonth(
        assigned=D(assigned), moved_in=D(moved_in), moved_out=D(moved_out), spent=D(spent)
    )


def ledger(*cats: PlanCategory) -> dict[uuid.UUID, PlanCategory]:
    return {c.category_id: c for c in cats}


def page(led: dict[uuid.UUID, PlanCategory], months: list[date], opening=None) -> dict:
    """The budget page's Available for each category over
    `[month before months[0], *months]`, walked over the same cells —
    `opening` is `{category_name: (month, Available)}`, an import anchor."""
    out = {}
    for c in led.values():
        assigned = {mo: cell.assigned for mo, cell in c.months.items()}
        activity = {
            mo: cell.moved_in - cell.moved_out - cell.spent for mo, cell in c.months.items()
        }
        seed = (opening or {}).get(c.name)
        series = monthly_end_balances(assigned, activity, opening=seed)
        out[c.category_id] = [
            available_at(series, mo) for mo in [add_months(months[0], -1), *months]
        ]
    return out


def report_for(led, window=WINDOW, balances=None) -> dict:
    return plan_vs_spent(led, window, page(led, window.axis) if balances is None else balances)


def row(report: dict, name: str) -> dict:
    return next(c for c in report["categories"] if c["category_name"] == name)


def lefts(r: dict) -> list:
    return [c["left"] for c in r["monthly"]]


class TestSixReproducedCases:
    """ "One Transfer, Three Totals" (v2026.09.28): six ledgers on which the
    carryover-blind report contradicted the budget page. Each now reads what
    the page says."""

    OUT = plan_effect(D("-1000"), "savings", savings_envelope=False)
    TAGGED = plan_effect(D("-1000"), "savings", savings_envelope=True)

    def _one(self, cells, *, sinking=False) -> dict:
        led = ledger(cat("Envelope", {H1[i]: c for i, c in cells.items()}, sinking=sinking))
        return report_for(led, HALF_YEAR)

    def test_a_transfer_out_the_month_after_is_not_a_phantom_underspend(self):
        # Case A: 1,000 assigned in February, moved to a brokerage in March.
        # It read +1,000 under: March's plan floored the transfer away.
        cells = {1: PlanMonth(assigned=D("1000")), 2: PlanMonth(moved_out=self.OUT.moved_out)}
        r = self._one(cells)
        env = r["categories"][0]
        assert lefts(env)[:6] == [D("0"), D("1000"), D("0"), D("0"), D("0"), D("0")]
        assert (env["total"]["left"], env["total"]["overspent"], env["months_over"]) == (
            D("0"),
            D("0"),
            0,
        )

    def test_a_tagged_transfer_out_the_month_after_is_not_drawn_over(self):
        # Case B: the Savings-tagged path drew March as a red over cell.
        cells = {1: PlanMonth(assigned=D("1000")), 2: PlanMonth(spent=self.TAGGED.spent)}
        env = self._one(cells)["categories"][0]
        assert [c["over"] for c in env["monthly"]] == [False] * 7
        assert (env["total"]["funded"], env["total"]["spent"], env["total"]["left"]) == (
            D("1000"),
            D("1000"),
            D("0"),
        )

    def test_a_transfer_out_the_same_month_reads_the_same(self):
        # Case C: the one the old report already got right, and still does.
        env = self._one({1: PlanMonth(assigned=D("1000"), moved_out=D("1000"))})["categories"][0]
        assert (env["total"]["left"], env["total"]["overspent"], env["months_over"]) == (
            D("0"),
            D("0"),
            0,
        )

    def test_saving_reads_as_left_not_under(self):
        # Case D: 200 a month toward a car fund, never drawn.
        env = self._one({i: PlanMonth(assigned=D("200")) for i in range(6)})["categories"][0]
        assert lefts(env)[:6] == [D("200"), D("400"), D("600"), D("800"), D("1000"), D("1200")]
        assert (env["total"]["left"], env["total"]["overspent"]) == (D("1200"), D("0"))

    def test_funded_once_and_spent_over_months_is_not_chronic(self):
        # Case E: 600 in January, 100 a month. It was chronic, 5 months over.
        cells = {0: PlanMonth(assigned=D("600"), spent=D("100"))} | {
            i: PlanMonth(spent=D("100")) for i in range(1, 6)
        }
        env = self._one(cells)["categories"][0]
        assert lefts(env)[:6] == [D("500"), D("400"), D("300"), D("200"), D("100"), D("0")]
        assert (env["chronic"], env["months_over"], env["months_active"]) == (False, 0, 6)

    def test_the_answer_no_longer_depends_on_a_tag(self):
        # Case F: the same cells tagged Long-term expense — the same answer.
        cells = {0: PlanMonth(assigned=D("600"), spent=D("100"))} | {
            i: PlanMonth(spent=D("100")) for i in range(1, 6)
        }
        untagged = self._one(cells)["categories"][0]
        tagged = self._one(cells, sinking=True)["categories"][0]
        assert (tagged["chronic"], tagged["months_over"]) == (False, 0)
        assert lefts(tagged) == lefts(untagged)

    def test_a_real_habit_is_still_chronic(self):
        # 100 assigned, 150 spent, every month: negative every month.
        env = self._one({i: PlanMonth(assigned=D("100"), spent=D("150")) for i in range(6)})[
            "categories"
        ][0]
        assert (env["chronic"], env["months_over"]) == (True, 6)
        assert (env["total"]["overspent"], env["avg_overspend"]) == (D("300"), D("50.00"))


class TestCarryover:
    def test_the_first_month_carries_in_what_the_month_before_left(self):
        # 900 left in May (before the window), 300 spent in each month.
        cells = {date(2026, 5, 1): m("900"), JUN: m("0", "300"), JUL: m("0", "300")}
        led = ledger(cat("Groceries", cells))
        g = row(report_for(led), "Groceries")
        june = g["monthly"][0]
        assert (june["carried_in"], june["funded"], june["left"], june["over"]) == (
            D("900"),
            D("900"),
            D("600"),
            False,
        )
        assert g["total"]["carried_in"] == D("900")
        assert g["total"]["funded"] == D("900")

    def test_an_overspent_month_is_covered_and_the_next_starts_from_zero(self):
        led = ledger(cat("Dining", {JUN: m("100", "180"), JUL: m("100", "60")}))
        g = row(report_for(led), "Dining")
        jun, jul, *_ = g["monthly"]
        assert (jun["left"], jun["overspent"], jun["over"]) == (D("-80"), D("80"), True)
        assert (jul["carried_in"], jul["left"], jul["over"]) == (D("0"), D("40"), False)
        assert (g["total"]["overspent"], g["total"]["left"]) == (D("80"), D("40"))

    def test_the_budget_pages_balance_is_what_a_cell_shows(self):
        # The page says 25 left where the ledger alone would say 40 — a
        # pending 15 the ledger does not read. The cell is the page's.
        led = ledger(cat("Fuel", {JUN: m("100", "60")}))
        (cid,) = led
        balances = {cid: [D("0"), D("25"), D("25"), D("25"), D("25")]}
        june = row(report_for(led, balances=balances), "Fuel")["monthly"][0]
        assert (june["left"], june["other"]) == (D("25"), D("-15"))

    def test_a_month_the_page_states_no_figure_for_is_walked_and_said(self):
        # Before an import the page cannot walk back through: None.
        led = ledger(cat("Fuel", {JUN: m("100", "130"), JUL: m("100", "50")}))
        (cid,) = led
        balances = {cid: [None, None, D("50"), D("50"), D("50")]}
        g = row(report_for(led, balances=balances), "Fuel")
        jun, jul, *_ = g["monthly"]
        assert (jun["carried_in"], jun["left"], jun["estimated"], jun["over"]) == (
            None,
            D("-30"),
            True,
            True,
        )
        assert (jul["carried_in"], jul["left"], jul["estimated"]) == (D("0"), D("50"), False)
        assert g["total"]["estimated"] is True

    def test_an_import_anchor_seeds_the_carry(self):
        # YNAB said 400 at the end of May; nothing assigned since.
        led = ledger(cat("Gifts", {JUN: m("0", "150")}))
        balances = page(led, WINDOW.axis, opening={"Gifts": (date(2026, 5, 1), D("400"))})
        g = row(report_for(led, balances=balances), "Gifts")
        assert (g["monthly"][0]["carried_in"], g["monthly"][0]["left"]) == (D("400"), D("250"))
        assert g["months_over"] == 0

    def test_a_balance_held_through_a_quiet_month_is_drawn(self):
        led = ledger(cat("Car fund", {JUN: m("500")}))
        g = row(report_for(led), "Car fund")
        assert [c["active"] for c in g["monthly"]] == [True, True, True, True]
        assert lefts(g) == [D("500")] * 4

    def test_a_category_absent_from_the_balances_walks_from_nothing(self):
        led = ledger(cat("Fuel", {JUN: m("100", "40")}))
        g = row(plan_vs_spent(led, WINDOW, {}), "Fuel")
        assert (g["monthly"][0]["carried_in"], g["monthly"][0]["left"]) == (None, D("60"))


class TestTheTotalsRow:
    def test_a_month_total_is_its_cells_summed(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "400"), JUL: m("500", "600")}),
            cat("Fuel", {JUN: m("100", "150"), JUL: m("100", "100")}),
        )
        jun, jul, aug, sep = report_for(led)["month_totals"]
        # Groceries: 100 left, then 100 + 500 - 600 = 0. Fuel: 50 short
        # (covered), then 0 + 100 - 100 = 0.
        assert (jun["funded"], jun["spent"], jun["left"], jun["overspent"]) == (
            D("600"),
            D("550"),
            D("50"),
            D("50"),
        )
        assert (jul["carried_in"], jul["funded"], jul["left"]) == (D("100"), D("700"), D("0"))
        assert (aug["funded"], aug["left"]) == (D("0"), D("0"))
        assert sep["partial_month"] is True
        assert "cumulative_variance" not in jun

    def test_it_counts_the_categories_over_each_month(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "600"), JUL: m("500", "600")}),
            cat("Fuel", {JUN: m("100", "150")}),
            # A few cents short is not over, and not counted.
            cat("Power", {JUN: m("80", "80.40")}),
        )
        jun, jul, aug, _ = report_for(led)["month_totals"]
        assert (jun["categories_over"], jul["categories_over"], aug["categories_over"]) == (
            2,
            1,
            0,
        )

    def test_the_running_month_is_drawn_and_counted_in_no_verdict(self):
        led = ledger(cat("Groceries", {AUG: m("400", "400"), SEP: m("900", "1000")}))
        report = report_for(led)
        *_, sep = report["month_totals"]
        assert (sep["spent"], sep["left"], sep["categories_over"]) == (D("1000"), D("-100"), 0)
        g = row(report, "Groceries")
        assert g["monthly"][-1]["over"] is False
        assert g["months_over"] == 0
        # The Total column is the complete months alone.
        assert (g["total"]["spent"], report["total_spent"]) == (D("400"), D("400"))


class TestTheTotalColumn:
    def test_it_is_the_complete_months_walked(self):
        cells = {JUN: m("500", "420", moved_in="50"), JUL: m("500", "700"), SEP: m("500", "90")}
        led = ledger(cat("Groceries", cells))
        total = row(report_for(led), "Groceries")["total"]
        # June: 550 funded, 130 left. July: 630 funded, 70 short, covered.
        assert total == {
            "carried_in": D("0"),
            "assigned": D("1000"),
            "moved_in": D("50"),
            "moved_out": D("0"),
            "funded": D("1050"),
            "spent": D("1120"),
            "other": D("0"),
            "left": D("0"),
            "overspent": D("70"),
            "over": True,
            "estimated": False,
        }

    def test_it_is_what_the_ai_reads_for_the_same_months(self):
        cells = {JUN: m("500", "420", moved_in="50"), JUL: m("500", "700")}
        led = ledger(cat("Groceries", cells))
        total = row(report_for(led), "Groceries")["total"]
        months = [JUN, JUL, AUG]
        (served,) = budget_vs_actual(led, months, page(led, months))["categories"]
        assert {k: served[k] for k in total} == total

    def test_money_taken_back_the_next_month_is_simply_gone(self):
        """300 assigned in June and swept back in July, nothing spent. The
        old per-month floor read it 300 under; it left nothing."""
        led = ledger(cat("Gifts", {JUN: m("300"), JUL: m("-300")}))
        total = row(report_for(led), "Gifts")["total"]
        assert (total["funded"], total["left"], total["overspent"], total["over"]) == (
            D("0"),
            D("0"),
            D("0"),
            False,
        )

    def test_the_window_totals_are_the_column_summed(self):
        led = ledger(
            cat("Groceries", {JUN: m("500", "400"), JUL: m("500", "600")}),
            cat("Fuel", {JUN: m("100", "150", moved_out="20")}),
            cat("Gifts", {JUL: m("-300")}),
        )
        report = report_for(led)
        totals = [c["total"] for c in report["categories"]]
        for key in ("assigned", "moved_in", "moved_out", "funded", "spent", "left", "overspent"):
            assert report[f"total_{key}"] == sum((t[key] for t in totals), D("0")), key

    def test_a_category_active_only_in_the_running_month_has_a_quiet_total(self):
        report = report_for(ledger(cat("New envelope", {SEP: m("200", "40")})))
        total = row(report, "New envelope")["total"]
        assert (total["funded"], total["spent"], total["left"], total["over"]) == (
            D("0"),
            D("0"),
            D("0"),
            False,
        )

    def test_a_plan_taken_back_is_still_a_row(self):
        # Nets to nothing over the window, and says so rather than vanishing.
        led = ledger(cat("Gifts", {JUN: m("300"), JUL: m("-300")}))
        assert [c["category_name"] for c in report_for(led)["categories"]] == ["Gifts"]
        months = [JUN, JUL, AUG]
        served = budget_vs_actual(led, months, page(led, months))["categories"]
        assert [c["category_name"] for c in served] == ["Gifts"]

    def test_a_quiet_category_is_no_row(self):
        report = report_for(ledger(cat("Nothing", {JUN: m()})))
        assert report["categories"] == []
        assert report["total_overspent"] == D("0")


class TestTheIdentityHolds:
    """funded - spent + other + overspent == left, for every Total and the
    headline, over random ledgers."""

    def test_over_300_random_ledgers(self):
        rng = random.Random(20260928)
        for _ in range(300):
            cats = []
            for i in range(rng.randint(1, 4)):
                cells = {}
                for mo in [date(2026, 5, 1), *WINDOW.axis]:
                    if rng.random() < 0.3:
                        continue
                    cells[mo] = m(
                        str(rng.choice([-400, -100, 0, 0, 100, 250, 500])),
                        str(rng.choice([-20, 0, 0, 90, 300, 600])),
                        moved_in=str(rng.choice([0, 0, 0, 200])),
                        moved_out=str(rng.choice([0, 0, 0, 150, 700])),
                    )
                cats.append(cat(f"c{i}", cells))
            report = report_for(ledger(*cats))
            for c in report["categories"]:
                t = c["total"]
                assert t["funded"] - t["spent"] + t["other"] + t["overspent"] == t["left"]
                for cell in c["monthly"]:
                    assert cell["funded"] - cell["spent"] + cell["other"] == cell["left"]
            h = {k: report[f"total_{k}"] for k in ("funded", "spent", "other", "overspent", "left")}
            assert h["funded"] - h["spent"] + h["other"] + h["overspent"] == h["left"]


class TestChronic:
    def test_negative_in_three_of_the_last_six_complete_months_is_chronic(self):
        window = ReportWindow(tuple(date(2026, k, 1) for k in range(3, 9)), SEP)
        over = {date(2026, k, 1): m("100", "200") for k in (4, 6, 8)}
        report = report_for(ledger(cat("Dining", over)), window)
        dining = row(report, "Dining")
        assert (dining["chronic"], dining["months_over"], dining["months_active"]) == (
            True,
            3,
            3,
        )
        assert dining["avg_overspend"] == D("100.00")
        assert report["chronic_count"] == 1

    def test_a_sinking_fund_paying_its_bill_is_not_over(self):
        # 100 a month for a 300 quarterly bill: it leaves zero, not below.
        cells = {JUN: m("100"), JUL: m("100"), AUG: m("100", "300")}
        fund = row(report_for(ledger(cat("Car insurance", cells, sinking=True))), "Car insurance")
        assert (fund["chronic"], fund["months_over"]) == (False, 0)
        assert "sinking_fund" not in fund

    def test_a_running_month_over_does_not_make_it_chronic(self):
        cells = {JUL: m("100", "200"), AUG: m("100", "200"), SEP: m("100", "900")}
        assert row(report_for(ledger(cat("Dining", cells))), "Dining")["chronic"] is False

    def test_chronic_sorts_first(self):
        window = ReportWindow(tuple(date(2026, k, 1) for k in range(3, 9)), SEP)
        led = ledger(
            cat("Big spender", {date(2026, 3, 1): m("0", "5000")}),
            cat("Habit", {date(2026, k, 1): m("10", "50") for k in (6, 7, 8)}),
        )
        names = [c["category_name"] for c in report_for(led, window)["categories"]]
        assert names == ["Habit", "Big spender"]


class TestTheWindow:
    def test_a_budget_with_no_complete_month_has_no_totals_window(self):
        window = ReportWindow((), SEP)
        report = report_for(ledger(cat("Groceries", {SEP: m("500", "40")})), window)
        assert (report["totals_start"], report["totals_end"]) == (None, None)
        assert report["months"] == [SEP]
        assert report["total_spent"] == D("0")

    def test_the_totals_window_is_the_complete_months(self):
        report = plan_vs_spent(ledger(), WINDOW, {})
        assert (report["totals_start"], report["totals_end"]) == (JUN, date(2026, 8, 31))
        assert report["running_month"] == SEP
