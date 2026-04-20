from datetime import date

import pytest

from igab.services.report_service import _last_day, _subtract_months


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
