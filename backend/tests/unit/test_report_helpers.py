from datetime import date

import pytest

from igab.services.report_service import (
    _last_day,
    _months_in_range,
    _next_occurrence,
    _subtract_months,
)


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


class TestNextOccurrence:
    def test_daily_weekly_biweekly(self):
        assert _next_occurrence(date(2024, 3, 1), "daily") == date(2024, 3, 2)
        assert _next_occurrence(date(2024, 3, 1), "weekly") == date(2024, 3, 8)
        assert _next_occurrence(date(2024, 3, 1), "biweekly") == date(2024, 3, 15)

    def test_monthly_plain(self):
        assert _next_occurrence(date(2024, 3, 15), "monthly") == date(2024, 4, 15)

    def test_monthly_clamps_to_shorter_month(self):
        assert _next_occurrence(date(2024, 1, 31), "monthly") == date(2024, 2, 29)
        assert _next_occurrence(date(2023, 1, 31), "monthly") == date(2023, 2, 28)
        assert _next_occurrence(date(2024, 3, 31), "monthly") == date(2024, 4, 30)

    def test_monthly_december_rolls_year(self):
        assert _next_occurrence(date(2024, 12, 15), "monthly") == date(2025, 1, 15)

    def test_yearly_plain(self):
        assert _next_occurrence(date(2024, 5, 10), "yearly") == date(2025, 5, 10)

    def test_yearly_clamps_leap_day(self):
        # Feb 29 + 1 year lands in a non-leap February — must clamp, not raise
        assert _next_occurrence(date(2024, 2, 29), "yearly") == date(2025, 2, 28)

    def test_unknown_frequency_is_none(self):
        assert _next_occurrence(date(2024, 3, 1), "fortnightly") is None


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
