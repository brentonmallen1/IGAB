from datetime import date

from igab.services.report_service import _subtract_months

# TestNextOccurrence lived here, testing `report_service._next_occurrence` — a
# fourth copy of recurrence stepping with no `twice_monthly` branch. The copy
# is gone and `cash_projection` calls `domain.schedule.next_occurrence`, whose
# 44 cases in tests/unit/test_calculate_next.py cover everything this class
# asserted plus the branch it was missing.
#
# TestLastDay went the same way: `report_service._last_day` was a private copy
# of `domain.dates.month_end`, and its cases live in test_domain_dates.py. So
# did TestMonthsInRange, now `domain.dates.month_starts`.


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
