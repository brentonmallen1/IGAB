"""Income Split's arithmetic (domain/income_split.py), without a database.

Every figure is written by hand and round enough to check on paper. The
household is invented: $7,200 a month take-home, a $2,100 mortgage, a $400 car
loan whose minimum is $325, a $1,752 yearly car premium.
"""

import uuid
from datetime import date
from decimal import Decimal

from igab.domain import income_split as split
from igab.domain.income_split import (
    CHOSEN,
    COMMITTED,
    DEBT,
    NEEDS,
    UNCATEGORIZED,
    CategoryRow,
    Minimum,
    SavedPart,
    clamp_to_history,
    months_covered,
    partition,
    spread_year,
    strict_reading,
)
from igab.guide.concepts import SPREAD_MONTHS

D = Decimal
CAR_LOAN = uuid.uuid4()
INSURANCE = uuid.uuid4()


def row(bucket, outflow, *, name="Groceries", debt=False, sinking=False, cid=None, liab=None):
    return CategoryRow(
        bucket=bucket,
        category_id=cid or uuid.uuid4(),
        name=name,
        group_name="Everyday",
        is_debt=debt,
        sinking=sinking,
        outflow=D(outflow),
        count=1,
        liability_id=liab,
    )


class TestMonthsCovered:
    def test_counts_whole_calendar_months(self):
        assert months_covered(date(2026, 7, 1), date(2026, 9, 30)) == (D(3), True)

    def test_a_year_across_new_year(self):
        assert months_covered(date(2025, 10, 1), date(2026, 9, 30)) == (D(12), True)

    def test_a_partial_month_is_days_over_an_average_month(self):
        months, whole = months_covered(date(2026, 10, 1), date(2026, 10, 22))
        assert not whole
        assert D("0.72") < months < D("0.73")  # 22 days of ~30.44

    def test_an_empty_range_is_no_months(self):
        assert months_covered(date(2026, 10, 2), date(2026, 10, 1)) == (D(0), False)


class TestSpreadYear:
    def test_is_the_month_of_the_end_and_the_eleven_before(self):
        assert spread_year(date(2026, 9, 30)) == (date(2025, 10, 1), date(2026, 9, 30))

    def test_spans_the_same_twelve_months_as_the_essentials_figure(self):
        assert split.SPREAD_MONTHS == SPREAD_MONTHS


class TestClampToHistory:
    def test_moves_a_start_before_the_history_to_its_first_month(self):
        assert clamp_to_history(date(2026, 1, 1), date(2026, 3, 14)) == (date(2026, 3, 1), True)

    def test_leaves_a_start_inside_the_history(self):
        assert clamp_to_history(date(2026, 4, 1), date(2026, 3, 14)) == (date(2026, 4, 1), False)

    def test_leaves_an_empty_budget_alone(self):
        assert clamp_to_history(date(2026, 4, 1), None) == (date(2026, 4, 1), False)


class TestPartition:
    def household(self, **kw):
        rows = [
            row(NEEDS, "6300", name="Mortgage", debt=True),
            row(NEEDS, "2460", name="Groceries"),
            row(NEEDS, "1200", name="Car loan", debt=True, liab=CAR_LOAN),
            row(COMMITTED, "180", name="Gym"),
            row(CHOSEN, "1560", name="Dining out"),
            row(UNCATEGORIZED, "432"),
            row(DEBT, "642", name="Student loan", debt=True),
        ]
        return partition(
            income=D("21600"),
            rows=rows,
            saved=[SavedPart(name="Cascade Point HYSA", reason_label="moved", total=D("1500"))],
            months=D(3),
            spread_on=False,
            minimums={CAR_LOAN: Minimum(name="Car loan", monthly=D("325"))},
            **kw,
        )

    def test_the_buckets_add_back_up_to_income(self):
        s = self.household()
        assert s.needs_total == D("9960")
        assert s.wants_total == D("1740")
        assert s.savings_debt_total == D("2142")
        assert s.uncategorized == D("432")
        assert s.left_over == D("7326")
        total = s.needs_total + s.wants_total + s.savings_debt_total + s.uncategorized
        assert total + s.left_over == s.income

    def test_says_why_each_line_is_where_it_is(self):
        s = self.household()
        reasons = {line.name: line.reason for line in [*s.needs, *s.committed, *s.chosen, *s.debt]}
        assert reasons == {
            "Mortgage": "essential_debt",
            "Groceries": "essential",
            "Car loan": "essential_debt",
            "Gym": "cost_of_living",
            "Dining out": "untagged",
            "Student loan": "debt_not_essential",
        }

    def test_a_debt_paid_above_its_minimum_says_by_how_much(self):
        # $400 a month against a $325 minimum, for three months: $225 above.
        car = next(line for line in self.household().needs if line.name == "Car loan")
        assert (car.minimum, car.above_minimum) == (D("325"), D("225.00"))

    def test_a_debt_with_no_minimum_on_file_says_so(self):
        mortgage = next(line for line in self.household().needs if line.name == "Mortgage")
        assert mortgage.minimum is None and mortgage.minimum_unknown

    def test_the_strict_reading_moves_only_what_went_above_the_minimum(self):
        needs, savings_debt = strict_reading(self.household())
        assert (needs, savings_debt) == (D("9735.00"), D("2367.00"))

    def test_lines_run_largest_first(self):
        assert [line.name for line in self.household().needs] == [
            "Mortgage",
            "Groceries",
            "Car loan",
        ]

    def test_left_over_goes_negative_when_outflows_ran_past_income(self):
        s = partition(
            income=D("1000"), rows=[row(CHOSEN, "1200")], saved=[], months=D(1), spread_on=False
        )
        assert s.left_over == D("-200")

    def test_counts_uncategorized_rows_on_their_own(self):
        rows = [row(UNCATEGORIZED, "100"), row(UNCATEGORIZED, "44")]
        s = partition(income=D("1000"), rows=rows, saved=[], months=D(1), spread_on=False)
        assert (s.uncategorized, s.uncategorized_count) == (D("144"), 2)
        assert s.chosen == []


class TestSpreading:
    """A $1,752 yearly premium paid in August, inside a July–September window."""

    def rows(self):
        return [row(NEEDS, "1752", name="Car insurance", sinking=True, cid=INSURANCE)]

    def test_counts_a_twelfth_of_the_year_per_month_covered(self):
        s = partition(
            income=D("21600"),
            rows=self.rows(),
            saved=[],
            months=D(3),
            spread_on=True,
            year_sinking={(NEEDS, INSURANCE): D("1752")},
        )
        [line] = s.needs
        assert (line.total, line.as_paid, line.spread) == (D("438.00"), D("1752.00"), True)

    def test_counts_as_paid_when_the_budget_turned_spreading_off(self):
        s = partition(
            income=D("21600"),
            rows=self.rows(),
            saved=[],
            months=D(3),
            spread_on=False,
            year_sinking={(NEEDS, INSURANCE): D("1752")},
        )
        [line] = s.needs
        assert (line.total, line.as_paid, line.spread) == (D("1752.00"), None, False)

    def test_the_difference_lands_in_left_over_so_income_still_adds_up(self):
        s = partition(
            income=D("21600"),
            rows=self.rows(),
            saved=[],
            months=D(3),
            spread_on=True,
            year_sinking={(NEEDS, INSURANCE): D("1752")},
        )
        assert s.needs_total + s.left_over == s.income
