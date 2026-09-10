from datetime import date

from igab.services.report_service import (
    _last_day,
    _months_in_range,
    _subtract_months,
)

# TestNextOccurrence lived here, testing `report_service._next_occurrence` — a
# fourth copy of recurrence stepping with no `twice_monthly` branch. The copy
# is gone and `cash_projection` calls `domain.schedule.next_occurrence`, whose
# 44 cases in tests/unit/test_calculate_next.py cover everything this class
# asserted plus the branch it was missing.


class TestSubtractMonths:
    def test_basic(self):
        assert _subtract_months(date(2024, 3, 1), 2) == date(2024, 1, 1)

    def test_year_rollover(self):
        assert _subtract_months(date(2024, 1, 1), 2) == date(2023, 11, 1)

    def test_multiple_years(self):
        assert _subtract_months(date(2024, 1, 1), 18) == date(2022, 7, 1)

    def test_zero(self):
        assert _subtract_months(date(2024, 6, 1), 0) == date(2024, 6, 1)

    def test_twelve(self):
        assert _subtract_months(date(2024, 6, 1), 12) == date(2023, 6, 1)

    def test_exactly_one_year(self):
        assert _subtract_months(date(2024, 12, 1), 12) == date(2023, 12, 1)

    def test_december_minus_one(self):
        assert _subtract_months(date(2024, 1, 1), 1) == date(2023, 12, 1)


class TestMonthsInRange:
    def test_single_month(self):
        assert _months_in_range(date(2024, 3, 10), date(2024, 3, 20)) == [date(2024, 3, 1)]

    def test_spans_year_boundary(self):
        assert _months_in_range(date(2023, 11, 15), date(2024, 2, 1)) == [
            date(2023, 11, 1),
            date(2023, 12, 1),
            date(2024, 1, 1),
            date(2024, 2, 1),
        ]

    def test_empty_when_start_after_end(self):
        assert _months_in_range(date(2024, 5, 1), date(2024, 4, 30)) == []


class TestLastDay:
    def test_january(self):
        assert _last_day(date(2024, 1, 1)) == date(2024, 1, 31)

    def test_february_non_leap(self):
        assert _last_day(date(2023, 2, 1)) == date(2023, 2, 28)

    def test_february_leap(self):
        assert _last_day(date(2024, 2, 1)) == date(2024, 2, 29)

    def test_april(self):
        assert _last_day(date(2024, 4, 1)) == date(2024, 4, 30)

    def test_november(self):
        assert _last_day(date(2024, 11, 1)) == date(2024, 11, 30)

    def test_december(self):
        assert _last_day(date(2024, 12, 1)) == date(2024, 12, 31)
