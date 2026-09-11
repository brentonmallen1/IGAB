"""Occurrence arithmetic — domain/schedule.py, the one home for it.

`stored_next_occurrence` maps a stored row onto `next_occurrence`; these
cases exercise the pure function directly, with the row-shaped mapping
covered in `TestStoredRow`.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.domain.schedule import (
    billing_day,
    first_occurrence_after,
    next_occurrence,
    observed_interval_days,
    projected_occurrences,
    step_cadence,
    stored_next_occurrence,
    subscription_occurrences,
    validate_schedule,
)


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


@dataclass
class Row:
    """A stored schedule: what `StoredSchedule` reads off the model."""

    frequency: str
    next_occurrence_date: date
    start_date: date
    second_day_of_month: int | None = None
    end_date: date | None = None


class TestStoredRow:
    """The row's stored next date is already clamped, so the mapping has to
    anchor on `start_date` — the fixtures here are the ones where the two
    differ, which no fixture did while the mapping was written twice."""

    def test_reads_the_row(self):
        row = Row("twice_monthly", date(2024, 3, 15), date(2024, 1, 1), second_day_of_month=15)
        assert stored_next_occurrence(row) == date(2024, 4, 1)

    def test_honours_end_date(self):
        row = Row("monthly", date(2024, 3, 15), date(2024, 1, 15), end_date=date(2024, 3, 31))
        assert stored_next_occurrence(row) is None

    def test_a_row_stored_on_a_clamped_day_returns_to_its_start_day(self):
        # Started 31 Jan, already advanced to 28 Feb: 31 Mar, not 28 Mar.
        row = Row("monthly", date(2027, 2, 28), date(2027, 1, 31))
        assert stored_next_occurrence(row) == date(2027, 3, 31)
        assert stored_next_occurrence(row, date(2027, 3, 31)) == date(2027, 4, 30)
        assert stored_next_occurrence(row, date(2027, 4, 30)) == date(2027, 5, 31)

    def test_a_twice_monthly_row_stored_on_its_second_day_keeps_its_first(self):
        # 1st/15th, stored on the 15th: anchored on the stored day, the 1st
        # would be lost for good.
        row = Row("twice_monthly", date(2027, 1, 15), date(2027, 1, 1), second_day_of_month=15)
        assert stored_next_occurrence(row) == date(2027, 2, 1)
        assert stored_next_occurrence(row, date(2027, 2, 1)) == date(2027, 2, 15)


class TestObservedIntervalDays:
    """A scheduled transaction states its frequency; a subscription inferred
    from a tagged category does not, so the cadence is measured from the
    charges the projection can see. It used to be a flat 30 days for
    everything.
    """

    def test_two_charges_a_month_apart_read_as_monthly(self):
        assert observed_interval_days(date(2026, 7, 15), date(2026, 8, 15), 2) == 31

    def test_a_year_of_monthly_charges_averages_to_a_month(self):
        # 12 charges spanning 11 months: 334 / 11 = 30.4 -> 30.
        assert observed_interval_days(date(2026, 1, 1), date(2026, 12, 1), 12) == 30

    def test_two_charges_a_year_apart_read_as_annual(self):
        assert observed_interval_days(date(2025, 3, 1), date(2026, 3, 1), 2) == 365

    def test_one_charge_says_nothing_so_monthly_is_assumed(self):
        assert observed_interval_days(date(2026, 8, 1), date(2026, 8, 1), 1) == 30

    def test_two_charges_on_one_day_do_not_project_daily(self):
        # No span at all, so this says no more than one charge: monthly is
        # assumed. It never reaches the floor below.
        assert observed_interval_days(date(2026, 8, 1), date(2026, 8, 1), 2) == 30

    def test_charges_bunched_inside_a_week_are_floored_to_weekly(self):
        # Three charges over one day: 1 / 2 rounds to 0. Without the floor,
        # stepping by 0 days never passes the horizon and the projection hangs.
        assert observed_interval_days(date(2026, 8, 1), date(2026, 8, 2), 3) == 7

    def test_a_very_long_gap_is_bounded(self):
        assert observed_interval_days(date(2020, 1, 1), date(2026, 1, 1), 2) == 400


class TestStepCadence:
    def test_a_monthly_interval_steps_a_calendar_month(self):
        # The old flat 30 days walked a monthly bill backwards through the
        # calendar: twelve steps is 360 days, so a thirteenth charge appeared
        # inside a year.
        assert step_cadence(date(2026, 1, 31), 30) == date(2026, 2, 28)
        assert step_cadence(date(2026, 8, 15), 31) == date(2026, 9, 15)

    def test_an_annual_interval_steps_a_calendar_year(self):
        assert step_cadence(date(2026, 3, 1), 365) == date(2027, 3, 1)

    def test_a_weekly_interval_steps_days(self):
        assert step_cadence(date(2026, 8, 1), 7) == date(2026, 8, 8)

    def test_a_quarterly_interval_steps_days(self):
        # 91 is outside both calendar bands, so it stays arithmetic.
        assert step_cadence(date(2026, 1, 1), 91) == date(2026, 4, 2)

    def test_an_anchor_day_brings_a_clamped_date_back(self):
        # From the clamped 28 Feb, a bill on the 31st is back on the 31st.
        # Without the anchor it stepped from the 28 and stayed there.
        assert step_cadence(date(2027, 2, 28), 30, anchor_day=31) == date(2027, 3, 31)
        assert step_cadence(date(2027, 2, 28), 365, anchor_day=29) == date(2028, 2, 29)


class TestProjectedOccurrences:
    TODAY = date(2026, 9, 10)

    def project(self, frequency, next_date, horizon_end, *, end_date=None):
        row = Row(frequency, next_date, next_date, end_date=end_date)
        return projected_occurrences(row, today=self.TODAY, horizon_end=horizon_end)

    def test_a_row_stored_on_a_clamped_day_projects_from_its_start_day(self):
        row = Row("monthly", date(2027, 2, 28), date(2027, 1, 31))
        dates, runs_on = projected_occurrences(
            row, today=date(2027, 2, 20), horizon_end=date(2027, 5, 1)
        )
        assert dates == [date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]
        assert runs_on

    def test_a_stale_backlog_books_one_occurrence_on_today(self):
        # Weekly, first due 185 days ago: 27 missed occurrences. One reaches
        # the path — booking all 27 on day 0 is what read "goes negative today".
        dates, runs_on = self.project("weekly", date(2026, 3, 9), date(2026, 9, 15))
        assert dates == [date(2026, 9, 10), date(2026, 9, 14)]
        assert runs_on

    def test_a_backlog_and_an_occurrence_due_today_are_one_charge(self):
        # Due 27 Aug, 3 Sep and today: one row in the register, one charge on
        # the path — not the backlog's charge plus today's.
        dates, runs_on = self.project("weekly", date(2026, 8, 27), date(2026, 9, 18))
        assert dates == [date(2026, 9, 10), date(2026, 9, 17)]
        assert runs_on

    def test_an_occurrence_due_today_with_no_backlog_is_booked_today(self):
        dates, _ = self.project("weekly", date(2026, 9, 10), date(2026, 9, 18))
        assert dates == [date(2026, 9, 10), date(2026, 9, 17)]

    def test_a_schedule_that_ended_while_overdue_books_its_last_one_and_stops(self):
        dates, runs_on = self.project(
            "monthly", date(2026, 8, 10), date(2026, 12, 9), end_date=date(2026, 8, 31)
        )
        assert dates == [date(2026, 9, 10)]
        assert not runs_on

    def test_a_schedule_due_after_the_horizon_books_nothing_and_runs_on(self):
        dates, runs_on = self.project("yearly", date(2027, 3, 1), date(2026, 12, 9))
        assert dates == []
        assert runs_on

    def test_a_schedule_whose_next_date_is_past_its_end_is_finished(self):
        dates, runs_on = self.project(
            "monthly", date(2026, 9, 20), date(2026, 12, 9), end_date=date(2026, 9, 15)
        )
        assert dates == []
        assert not runs_on

    def test_an_overdue_one_off_lands_on_today_once(self):
        dates, runs_on = self.project("once", date(2026, 9, 1), date(2026, 12, 9))
        assert dates == [date(2026, 9, 10)]
        assert not runs_on


class TestBillingDay:
    def test_the_last_charges_day(self):
        assert billing_day(date(2026, 6, 15), date(2026, 8, 15)) == 15

    def test_a_bill_on_the_31st_seen_last_on_a_short_month(self):
        # 28 February is the 31st, clamped; the earlier charge says so.
        assert billing_day(date(2027, 1, 31), date(2027, 2, 28)) == 31
        assert billing_day(date(2026, 7, 31), date(2026, 9, 30)) == 31

    def test_a_bill_that_moved_earlier_in_the_month_follows_the_move(self):
        # The last charge is not a month end, so it is not a clamp: the bill
        # really moved from the 20th to the 5th.
        assert billing_day(date(2026, 6, 20), date(2026, 8, 5)) == 5


class TestSubscriptionOccurrences:
    TODAY = date(2026, 9, 10)
    END = date(2026, 12, 9)

    def test_a_live_monthly_subscription_projects_every_cycle(self):
        out = subscription_occurrences(
            date(2026, 6, 16), date(2026, 8, 16), 3, self.TODAY, self.END
        )
        assert out == [date(2026, 9, 16), date(2026, 10, 16), date(2026, 11, 16)]

    def test_a_subscription_that_missed_two_cycles_is_treated_as_cancelled(self):
        # Last charged 400 days ago on a monthly cadence.
        assert (
            subscription_occurrences(date(2025, 7, 1), date(2025, 8, 1), 2, self.TODAY, self.END)
            == []
        )

    # The boundary itself: missing two cycles is cancelled, missing them by a
    # day more is. Only a thirteen-cycle gap was pinned, so any threshold from
    # two cycles to twelve passed — and a subscription cancelled three months
    # ago would have gone on being projected. Weekly and 40-day cadences step
    # by days; 30 steps a calendar month.
    @pytest.mark.parametrize("interval", [7, 30, 40])
    def test_a_last_charge_exactly_two_cycles_back_is_still_projected(self, interval):
        last = self.TODAY - timedelta(days=2 * interval)
        first = last - timedelta(days=interval)
        out = subscription_occurrences(first, last, 2, self.TODAY, self.END)
        assert out and min(out) >= self.TODAY

    @pytest.mark.parametrize("interval", [7, 30, 40])
    def test_a_day_past_two_cycles_is_cancelled(self, interval):
        last = self.TODAY - timedelta(days=2 * interval + 1)
        first = last - timedelta(days=interval)
        assert subscription_occurrences(first, last, 2, self.TODAY, self.END) == []

    def test_an_annual_subscription_projects_at_most_once(self):
        # Charged each November: one charge inside the horizon, not twelve.
        # The flat 30-day step used to book it every month.
        out = subscription_occurrences(
            date(2024, 11, 20), date(2025, 11, 20), 2, self.TODAY, self.END
        )
        assert out == [date(2026, 11, 20)]

    def test_nothing_is_booked_before_today(self):
        out = subscription_occurrences(date(2026, 7, 2), date(2026, 8, 2), 2, self.TODAY, self.END)
        assert out and min(out) >= self.TODAY

    def test_an_empty_horizon_books_nothing(self):
        assert (
            subscription_occurrences(
                date(2026, 7, 16), date(2026, 8, 16), 2, self.TODAY, self.TODAY
            )
            == []
        )

    def test_a_month_end_bill_keeps_its_day_across_several_cycles(self):
        # One step lands on a short month and clamps; every later step has to
        # come back to the 31st. Stepping from the clamped date read 28 Mar
        # and 28 Apr — charges landing up to three days early.
        out = subscription_occurrences(
            date(2026, 12, 31), date(2027, 1, 31), 2, date(2027, 2, 1), date(2027, 5, 2)
        )
        assert out == [date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]

    def test_a_last_charge_already_clamped_still_returns_to_the_31st(self):
        out = subscription_occurrences(
            date(2027, 1, 31), date(2027, 2, 28), 2, date(2027, 3, 5), date(2027, 6, 1)
        )
        assert out == [date(2027, 3, 31), date(2027, 4, 30), date(2027, 5, 31)]
