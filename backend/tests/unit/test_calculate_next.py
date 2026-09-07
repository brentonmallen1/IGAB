"""Occurrence arithmetic — domain/schedule.py, the one home for it.

`calculate_next` on the service is a wrapper over `next_occurrence`; these
cases exercise the pure function directly, with the row-shaped wrapper
covered once at the bottom.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.domain.schedule import first_occurrence_after, next_occurrence, validate_schedule
from igab.services.scheduled_transaction_service import calculate_next


def nxt(frequency: str, current: date, **kw) -> date | None:
    return next_occurrence(frequency, current, **kw)


def twice(current: date, *, start_day: int, second: int) -> date | None:
    return next_occurrence(
        "twice_monthly", current, start_day=start_day, second_day_of_month=second
    )


class TestDaily:
    def test_basic(self):
        assert nxt("daily", date(2024, 3, 15)) == date(2024, 3, 16)

    def test_end_of_month(self):
        assert nxt("daily", date(2024, 3, 31)) == date(2024, 4, 1)

    def test_end_of_year(self):
        assert nxt("daily", date(2024, 12, 31)) == date(2025, 1, 1)


class TestWeekly:
    def test_basic(self):
        assert nxt("weekly", date(2024, 3, 15)) == date(2024, 3, 22)

    def test_crosses_month(self):
        assert nxt("weekly", date(2024, 3, 29)) == date(2024, 4, 5)


class TestBiweekly:
    def test_basic(self):
        assert nxt("biweekly", date(2024, 3, 1)) == date(2024, 3, 15)

    def test_crosses_month(self):
        assert nxt("biweekly", date(2024, 3, 22)) == date(2024, 4, 5)


class TestMonthly:
    def test_basic(self):
        assert nxt("monthly", date(2024, 3, 15)) == date(2024, 4, 15)

    def test_december_to_january(self):
        assert nxt("monthly", date(2024, 12, 15)) == date(2025, 1, 15)

    def test_jan_31_to_feb_leap(self):
        assert nxt("monthly", date(2024, 1, 31)) == date(2024, 2, 29)

    def test_jan_31_to_feb_non_leap(self):
        assert nxt("monthly", date(2023, 1, 31)) == date(2023, 2, 28)

    def test_march_31_to_april(self):
        assert nxt("monthly", date(2024, 3, 31)) == date(2024, 4, 30)

    def test_end_of_november_to_december(self):
        assert nxt("monthly", date(2024, 11, 30)) == date(2024, 12, 30)

    def test_start_day_reanchors_after_a_clamped_month(self):
        # Stepping from the clamped 28 Feb without the start day drifted a
        # schedule dated the 31st to the 28th of every month after.
        assert nxt("monthly", date(2023, 2, 28), start_day=31) == date(2023, 3, 31)


class TestYearly:
    def test_basic(self):
        assert nxt("yearly", date(2024, 3, 15)) == date(2025, 3, 15)

    def test_end_of_year(self):
        assert nxt("yearly", date(2024, 12, 31)) == date(2025, 12, 31)

    def test_leap_day_does_not_raise(self):
        # `current.replace(year=current.year + 1)` raised ValueError here, so a
        # yearly schedule dated 29 February stalled its run every time — and
        # the failure was a 500, not a skipped occurrence.
        assert nxt("yearly", date(2024, 2, 29)) == date(2025, 2, 28)

    def test_leap_day_to_leap_day(self):
        assert nxt("yearly", date(2023, 2, 28)) == date(2024, 2, 28)

    def test_leap_day_returns_on_the_next_leap_year_with_start_day(self):
        assert nxt("yearly", date(2025, 2, 28), start_day=29) == date(2026, 2, 28)
        assert nxt("yearly", date(2027, 2, 28), start_day=29) == date(2028, 2, 29)


class TestTwiceMonthly:
    """The branch that did not exist: a due twice-monthly auto-create
    schedule fell through to "same date" and posted a fresh row every
    night. Days are the start date's day and `second_day_of_month`."""

    def test_first_day_to_second_day(self):
        assert twice(date(2024, 3, 1), start_day=1, second=15) == date(2024, 3, 15)

    def test_second_day_rolls_to_next_month(self):
        assert twice(date(2024, 3, 15), start_day=1, second=15) == date(2024, 4, 1)

    def test_second_day_31_clamps_in_february(self):
        assert nxt(
            "twice_monthly", date(2024, 2, 15), start_day=15, second_day_of_month=31
        ) == date(2024, 2, 29)
        assert nxt(
            "twice_monthly", date(2023, 2, 15), start_day=15, second_day_of_month=31
        ) == date(2023, 2, 28)

    def test_clamped_day_reanchors_next_month(self):
        # From the clamped 28 Feb the next is 15 Mar, then 31 Mar — not 28 Mar.
        assert nxt(
            "twice_monthly", date(2023, 2, 28), start_day=15, second_day_of_month=31
        ) == date(2023, 3, 15)
        assert nxt(
            "twice_monthly", date(2023, 3, 15), start_day=15, second_day_of_month=31
        ) == date(2023, 3, 31)

    def test_start_day_after_second_day_orders_correctly(self):
        assert twice(date(2024, 3, 20), start_day=20, second=5) == date(2024, 4, 5)
        assert twice(date(2024, 4, 5), start_day=20, second=5) == date(2024, 4, 20)

    def test_without_a_second_day_is_refused(self):
        with pytest.raises(InvariantViolation):
            nxt("twice_monthly", date(2024, 3, 1), start_day=1)


class TestOnceAndEndDate:
    def test_once_has_no_next(self):
        assert nxt("once", date(2024, 3, 15)) is None

    def test_any_frequency_past_end_date_has_no_next(self):
        assert nxt("monthly", date(2024, 3, 15), end_date=date(2024, 4, 1)) is None
        assert nxt("weekly", date(2024, 3, 15), end_date=date(2024, 3, 21)) is None

    def test_end_date_on_the_occurrence_still_occurs(self):
        assert nxt("monthly", date(2024, 3, 15), end_date=date(2024, 4, 15)) == date(2024, 4, 15)


class TestUnknown:
    def test_unknown_frequency_raises(self):
        # It used to return the same date, which is how a typo became a
        # schedule that never advanced.
        with pytest.raises(ValueError):
            nxt("fortnightly", date(2024, 3, 15))


class TestFirstOccurrenceAfter:
    """Pins the sample generator's old answers, which this replaced."""

    def test_monthly_lands_on_this_month_when_still_ahead(self):
        anchor = date(2026, 9, 6)
        assert first_occurrence_after("monthly", anchor, start_date=date(2026, 3, 10)) == date(
            2026, 9, 10
        )

    def test_monthly_lands_next_month_when_passed(self):
        anchor = date(2026, 9, 6)
        assert first_occurrence_after("monthly", anchor, start_date=date(2026, 3, 1)) == date(
            2026, 10, 1
        )

    def test_twice_monthly(self):
        anchor = date(2026, 9, 6)
        assert first_occurrence_after(
            "twice_monthly", anchor, start_date=date(2026, 3, 1), second_day_of_month=15
        ) == date(2026, 9, 15)

    def test_yearly_from_last_occurrence(self):
        anchor = date(2026, 9, 6)
        assert first_occurrence_after("yearly", anchor, start_date=date(2026, 3, 10)) == date(
            2027, 3, 10
        )

    def test_start_in_the_future_is_the_answer(self):
        assert first_occurrence_after(
            "monthly", date(2026, 9, 6), start_date=date(2026, 10, 1)
        ) == (date(2026, 10, 1))

    def test_once_in_the_past_has_no_next(self):
        assert first_occurrence_after("once", date(2026, 9, 6), start_date=date(2026, 8, 1)) is None


class TestValidateSchedule:
    def ok(self, **kw):
        base = dict(
            frequency="monthly",
            start_date=date(2026, 9, 1),
            second_day_of_month=None,
            end_date=None,
            days_before_reminder=3,
        )
        base.update(kw)
        validate_schedule(**base)

    def test_accepts_every_frequency(self):
        for f in ("once", "daily", "weekly", "biweekly", "monthly", "yearly"):
            self.ok(frequency=f)
        self.ok(frequency="twice_monthly", second_day_of_month=15)

    def test_rejects_unknown_frequency(self):
        with pytest.raises(InvariantViolation, match="Frequency must be one of"):
            self.ok(frequency="fortnightly")

    def test_twice_monthly_requires_second_day(self):
        with pytest.raises(InvariantViolation, match="second day"):
            self.ok(frequency="twice_monthly")

    def test_rejects_second_day_equal_to_start_day(self):
        with pytest.raises(InvariantViolation, match="differ"):
            self.ok(frequency="twice_monthly", second_day_of_month=1)

    def test_rejects_end_before_start(self):
        with pytest.raises(InvariantViolation, match="End date"):
            self.ok(end_date=date(2026, 8, 31))

    def test_end_on_start_is_fine(self):
        self.ok(end_date=date(2026, 9, 1))

    def test_rejects_negative_reminder(self):
        with pytest.raises(InvariantViolation, match="Reminder"):
            self.ok(days_before_reminder=-1)


class TestRowWrapper:
    def test_calculate_next_reads_the_row(self):
        m = MagicMock()
        m.frequency = "twice_monthly"
        m.next_occurrence_date = date(2024, 3, 15)
        m.start_date = date(2024, 1, 1)
        m.second_day_of_month = 15
        m.end_date = None
        assert calculate_next(m) == date(2024, 4, 1)

    def test_calculate_next_honours_end_date(self):
        m = MagicMock()
        m.frequency = "monthly"
        m.next_occurrence_date = date(2024, 3, 15)
        m.start_date = date(2024, 1, 15)
        m.second_day_of_month = None
        m.end_date = date(2024, 3, 31)
        assert calculate_next(m) is None
