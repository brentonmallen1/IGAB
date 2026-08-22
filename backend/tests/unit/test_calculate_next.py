from datetime import date
from unittest.mock import MagicMock

from igab.services.scheduled_transaction_service import calculate_next


def sched(frequency: str, next_date: date) -> MagicMock:
    m = MagicMock()
    m.frequency = frequency
    m.next_occurrence_date = next_date
    return m


class TestCalculateNextDaily:
    def test_basic(self):
        assert calculate_next(sched("daily", date(2024, 3, 15))) == date(2024, 3, 16)

    def test_end_of_month(self):
        assert calculate_next(sched("daily", date(2024, 3, 31))) == date(2024, 4, 1)

    def test_end_of_year(self):
        assert calculate_next(sched("daily", date(2024, 12, 31))) == date(2025, 1, 1)


class TestCalculateNextWeekly:
    def test_basic(self):
        assert calculate_next(sched("weekly", date(2024, 3, 15))) == date(2024, 3, 22)

    def test_crosses_month(self):
        assert calculate_next(sched("weekly", date(2024, 3, 29))) == date(2024, 4, 5)


class TestCalculateNextBiweekly:
    def test_basic(self):
        assert calculate_next(sched("biweekly", date(2024, 3, 1))) == date(2024, 3, 15)

    def test_crosses_month(self):
        assert calculate_next(sched("biweekly", date(2024, 3, 22))) == date(2024, 4, 5)


class TestCalculateNextMonthly:
    def test_basic(self):
        assert calculate_next(sched("monthly", date(2024, 3, 15))) == date(2024, 4, 15)

    def test_december_to_january(self):
        assert calculate_next(sched("monthly", date(2024, 12, 15))) == date(2025, 1, 15)

    def test_jan_31_to_feb_leap(self):
        # 2024 is a leap year
        assert calculate_next(sched("monthly", date(2024, 1, 31))) == date(2024, 2, 29)

    def test_jan_31_to_feb_non_leap(self):
        assert calculate_next(sched("monthly", date(2023, 1, 31))) == date(2023, 2, 28)

    def test_march_31_to_april(self):
        # April has 30 days
        assert calculate_next(sched("monthly", date(2024, 3, 31))) == date(2024, 4, 30)

    def test_end_of_november_to_december(self):
        assert calculate_next(sched("monthly", date(2024, 11, 30))) == date(2024, 12, 30)


class TestCalculateNextYearly:
    def test_basic(self):
        assert calculate_next(sched("yearly", date(2024, 3, 15))) == date(2025, 3, 15)

    def test_end_of_year(self):
        assert calculate_next(sched("yearly", date(2024, 12, 31))) == date(2025, 12, 31)


class TestCalculateNextUnknown:
    def test_unknown_frequency_is_noop(self):
        d = date(2024, 3, 15)
        assert calculate_next(sched("unknown", d)) == d
