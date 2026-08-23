"""Month arithmetic, and the distinction the four old copies kept losing.

`add_months` shifts a date and clamps; `month_start`/`month_end` name a bucket
and discard the day on purpose. Mixing them up is how a yearly schedule dated
29 February came to raise ValueError, and how month bucketing came to be
written three different ways.
"""

from datetime import date

import pytest

from igab.domain.dates import add_months, month_end, month_start, months_between


class TestAddMonths:
    def test_shifts_forward(self):
        assert add_months(date(2024, 3, 15), 1) == date(2024, 4, 15)

    def test_shifts_backward(self):
        assert add_months(date(2024, 3, 15), -1) == date(2024, 2, 15)

    def test_crosses_year_in_both_directions(self):
        assert add_months(date(2024, 12, 15), 1) == date(2025, 1, 15)
        assert add_months(date(2024, 1, 15), -1) == date(2023, 12, 15)

    def test_crosses_multiple_years(self):
        assert add_months(date(2024, 1, 15), -13) == date(2022, 12, 15)
        assert add_months(date(2024, 1, 15), 25) == date(2026, 2, 15)

    def test_zero_is_identity(self):
        assert add_months(date(2024, 2, 29), 0) == date(2024, 2, 29)

    @pytest.mark.parametrize(
        ("start", "months", "expected"),
        [
            (date(2024, 1, 31), 1, date(2024, 2, 29)),  # into a leap February
            (date(2023, 1, 31), 1, date(2023, 2, 28)),  # into a common February
            (date(2024, 3, 31), 1, date(2024, 4, 30)),  # into a 30-day month
            (date(2024, 2, 29), 12, date(2025, 2, 28)),  # the leap-day crash
            (date(2024, 5, 31), -1, date(2024, 4, 30)),  # clamping backwards too
        ],
    )
    def test_clamps_the_day_to_the_target_month(self, start, months, expected):
        assert add_months(start, months) == expected

    def test_clamping_is_not_reversible(self):
        # Worth pinning: shifting away and back does not return the 31st. Any
        # caller that round-trips a date through add_months is already wrong.
        there = add_months(date(2024, 1, 31), 1)
        assert add_months(there, -1) == date(2024, 1, 29)

    def test_never_raises_on_any_day_of_any_month(self):
        for month in range(1, 13):
            for day in (1, 28, 29, 30, 31):
                try:
                    start = date(2024, month, day)
                except ValueError:
                    continue
                for shift in (-13, -1, 0, 1, 12, 13):
                    add_months(start, shift)  # must not raise


class TestMonthBuckets:
    def test_month_start_discards_the_day(self):
        assert month_start(date(2024, 3, 15)) == date(2024, 3, 1)

    def test_month_end_knows_february(self):
        assert month_end(date(2024, 2, 10)) == date(2024, 2, 29)
        assert month_end(date(2023, 2, 10)) == date(2023, 2, 28)

    def test_month_end_knows_thirty_day_months(self):
        assert month_end(date(2024, 4, 5)) == date(2024, 4, 30)

    def test_bucket_shift_keeps_day_one(self):
        # The composition report_service._subtract_months is built from.
        assert add_months(month_start(date(2024, 3, 31)), -2) == date(2024, 1, 1)


class TestMonthsBetween:
    def test_counts_whole_months(self):
        assert months_between(date(2026, 1, 15), date(2026, 4, 1)) == 3

    def test_ignores_the_day(self):
        # Deliberate: the funding rule counts month boundaries, not elapsed days.
        assert months_between(date(2026, 1, 1), date(2026, 2, 28)) == 1

    def test_floors_at_one_for_the_current_month(self):
        assert months_between(date(2026, 8, 23), date(2026, 8, 1)) == 1

    def test_floors_at_one_for_a_past_target(self):
        # An overdue target still has to be met once; dividing by zero or by a
        # negative month count has no meaning.
        assert months_between(date(2026, 8, 1), date(2025, 1, 1)) == 1

    def test_crosses_a_year(self):
        assert months_between(date(2025, 11, 1), date(2026, 2, 1)) == 3
