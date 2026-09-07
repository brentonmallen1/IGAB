"""Occurrence arithmetic and shape rules for scheduled transactions.

Three implementations of "when is the next one" existed before this module:
the service's `calculate_next` (no `twice_monthly` branch, so a due
twice-monthly auto-create schedule fell through to "same date" and posted a
fresh row every night without ever advancing), the sample generator's
`_next_occurrence` (twice-monthly but no weekly/biweekly/daily), and nothing
at all for a one-off. They agreed on the cases they shared only because the
sample budget never asked the service to advance anything.

`None` is the answer for "there is no next occurrence": a `once` schedule
after its date, or any schedule whose next date would fall past `end_date`.
The service turns `None` into completion. It is not a synonym for "unknown"
— an unknown frequency raises, because it is a validation failure that
should have been refused at the edge.

Pure on purpose: dates in, dates out, so every calendar edge is a one-line
test.
"""

import calendar
from datetime import date, timedelta

from igab.domain.dates import add_months
from igab.domain.enums import ScheduleFrequency
from igab.domain.exceptions import InvariantViolation

#: How far `first_occurrence_after` will walk before deciding the inputs are
#: nonsense (a daily schedule started decades ago). Not a business rule.
_MAX_WALK = 20_000


def _day_in(year: int, month: int, day: int) -> date:
    """`day` of that month, clamped to the month's length — 31 in February
    is the 28th (or 29th), not an error and not 3 March."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_occurrence(
    frequency: str,
    current: date,
    *,
    start_day: int | None = None,
    second_day_of_month: int | None = None,
    end_date: date | None = None,
) -> date | None:
    """The occurrence after `current`, or None when the schedule is complete.

    `start_day` is the day-of-month the schedule was created on. Monthly and
    yearly schedules re-anchor to it each step so a schedule dated the 31st
    reads 28 Feb, then 31 Mar — stepping from the clamped date instead
    would drift to the 28th forever. Twice-monthly uses `start_day` and
    `second_day_of_month` as its two days, each clamped to the month.
    """
    freq = ScheduleFrequency(frequency)
    day = start_day or current.day

    if freq is ScheduleFrequency.ONCE:
        return None
    if freq is ScheduleFrequency.DAILY:
        nxt = current + timedelta(days=1)
    elif freq is ScheduleFrequency.WEEKLY:
        nxt = current + timedelta(weeks=1)
    elif freq is ScheduleFrequency.BIWEEKLY:
        nxt = current + timedelta(weeks=2)
    elif freq is ScheduleFrequency.MONTHLY:
        shifted = add_months(current, 1)
        nxt = _day_in(shifted.year, shifted.month, day)
    elif freq is ScheduleFrequency.YEARLY:
        # add_months, not `replace(year=...)`: a schedule dated 29 February
        # raised ValueError every leap year and stalled the run.
        shifted = add_months(current, 12)
        nxt = _day_in(shifted.year, shifted.month, day)
    elif freq is ScheduleFrequency.TWICE_MONTHLY:
        if second_day_of_month is None:
            raise InvariantViolation("A twice-monthly schedule needs its second day of the month")
        days = sorted({day, second_day_of_month})
        following = add_months(current.replace(day=1), 1)
        candidates = [_day_in(current.year, current.month, d) for d in days] + [
            _day_in(following.year, following.month, d) for d in days
        ]
        nxt = min(c for c in candidates if c > current)
    else:  # pragma: no cover — the enum is closed
        raise InvariantViolation(f"Unknown frequency {frequency!r}")

    if end_date is not None and nxt > end_date:
        return None
    return nxt


def first_occurrence_after(
    frequency: str,
    after: date,
    *,
    start_date: date,
    second_day_of_month: int | None = None,
    end_date: date | None = None,
) -> date | None:
    """Walk a schedule forward from `start_date` to its first occurrence
    strictly after `after`. `start_date` itself counts when it is later.

    The sample generator needs this to seed a schedule whose history is
    months old with a next date in the anchor's window; it had its own
    arithmetic for the purpose.
    """
    current = start_date
    if current > after:
        return current
    for _ in range(_MAX_WALK):
        nxt = next_occurrence(
            frequency,
            current,
            start_day=start_date.day,
            second_day_of_month=second_day_of_month,
            end_date=end_date,
        )
        if nxt is None:
            return None
        if nxt > after:
            return nxt
        current = nxt
    raise InvariantViolation("Schedule walks too far — check the start date")


def validate_schedule(
    *,
    frequency: str,
    start_date: date,
    second_day_of_month: int | None,
    end_date: date | None,
    days_before_reminder: int,
) -> None:
    """The cross-field rules a schedule must satisfy, applied to the merged
    state on create and update so a PATCH cannot leave a row the arithmetic
    above will refuse. Raises InvariantViolation."""
    try:
        freq = ScheduleFrequency(frequency)
    except ValueError:
        allowed = ", ".join(f.value for f in ScheduleFrequency)
        raise InvariantViolation(f"Frequency must be one of: {allowed}") from None
    if freq is ScheduleFrequency.TWICE_MONTHLY:
        if second_day_of_month is None or not 1 <= second_day_of_month <= 31:
            raise InvariantViolation(
                "A twice-monthly schedule needs a second day of the month (1–31)"
            )
        if second_day_of_month == start_date.day:
            raise InvariantViolation("The second day must differ from the start date's day")
    if end_date is not None and end_date < start_date:
        raise InvariantViolation("End date cannot be before the start date")
    if days_before_reminder < 0:
        raise InvariantViolation("Reminder days cannot be negative")
