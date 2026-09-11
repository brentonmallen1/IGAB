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


def _step_months(current: date, months: int, day: int) -> date:
    """`months` calendar months on from `current`, landing on `day` — clamped
    in a short month, and back on `day` the month after. Stepping from the
    clamped date instead drifts a bill on the 31st to the 28th for good."""
    shifted = add_months(current, months)
    return _day_in(shifted.year, shifted.month, day)


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
        nxt = _step_months(current, 1, day)
    elif freq is ScheduleFrequency.YEARLY:
        # add_months, not `replace(year=...)`: a schedule dated 29 February
        # raised ValueError every leap year and stalled the run.
        nxt = _step_months(current, 12, day)
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


def projected_occurrences(
    frequency: str,
    next_date: date,
    *,
    start_day: int,
    second_day_of_month: int | None,
    end_date: date | None,
    today: date,
    horizon_end: date,
) -> tuple[list[date], bool]:
    """A schedule's occurrences on a projection from `today` to `horizon_end`,
    and whether it keeps running past the horizon.

    An occurrence already due but not entered is booked on `today` — the path
    starts there, so a past date is one no projected balance would visit. But
    everything due on or before today is ONE charge, the one row the register
    shows for the schedule. A manual schedule advances only through Enter or
    Skip, so one kept as a reminder for a bill paid through bank sync piles up
    missed occurrences whose money has already left: booking every one of
    them put -$7,000 on day 0 of a six-month-stale $1,000 rent reminder, and
    read "goes negative today".
    """
    out: list[date] = []
    current: date | None = next_date
    while current is not None and current <= horizon_end:
        if end_date is not None and current > end_date:
            return out, False
        if current > today:
            out.append(current)
        elif not out:
            out.append(today)
        current = next_occurrence(
            frequency,
            current,
            start_day=start_day,
            second_day_of_month=second_day_of_month,
            end_date=end_date,
        )
    return out, current is not None and (end_date is None or current <= end_date)


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


# ─── Observed cadence ─────────────────────────────────────────────────────────
#
# A scheduled transaction states its frequency. A subscription inferred from a
# tagged category does not — all the cash projection has is the charges it can
# see — so the cadence has to be measured. This lives beside `next_occurrence`
# because it is the same kind of arithmetic, and because the projection had its
# own copy of the stepping once already.

#: One charge says nothing about cadence, so it is assumed monthly: the tag is
#: "Subscription" and monthly is what that overwhelmingly means.
ASSUMED_INTERVAL_DAYS = 30
#: A payee charged twice on one day would otherwise divide by zero days and
#: project daily forever.
MIN_INTERVAL_DAYS = 7
MAX_INTERVAL_DAYS = 400


def observed_interval_days(first: date, last: date, charge_count: int) -> int:
    """The mean gap between charges, in days.

    The cash projection used to step every subscription by a flat 30 days,
    which charged an annual subscription twelve times a year and walked a
    monthly one backwards through the calendar — twelve 30-day steps is 360
    days, so a thirteenth charge appeared inside a year.
    """
    if charge_count < 2 or last <= first:
        return ASSUMED_INTERVAL_DAYS
    span = (last - first).days
    return max(MIN_INTERVAL_DAYS, min(MAX_INTERVAL_DAYS, round(span / (charge_count - 1))))


def step_cadence(d: date, interval_days: int, *, anchor_day: int | None = None) -> date:
    """Advance one billing cycle.

    A near-monthly interval steps a CALENDAR month and a near-annual one a
    calendar year, both landing on `anchor_day` (default: `d`'s own day) the
    way `next_occurrence` re-anchors a schedule. Anything else steps by days.
    Stepping 30 days for a monthly bill is what made a subscription drift off
    its billing date, and the drift compounds across a 90-day horizon.
    """
    day = anchor_day or d.day
    if 25 <= interval_days <= 35:
        return _step_months(d, 1, day)
    if 350 <= interval_days <= MAX_INTERVAL_DAYS:
        return _step_months(d, 12, day)
    return d + timedelta(days=interval_days)


def billing_day(first_charge: date, last_charge: date) -> int:
    """The day of the month a subscription bills on, read off its charges.

    The last charge's day — unless it sits on the final day of a month and an
    earlier charge fell later in its month. A bill on the 31st posts on 28
    February; anchoring to that 28 kept every later charge on the 28th.
    """
    month_length = calendar.monthrange(last_charge.year, last_charge.month)[1]
    if last_charge.day == month_length and first_charge.day > last_charge.day:
        return first_charge.day
    return last_charge.day


def subscription_occurrences(
    first_charge: date, last_charge: date, charge_count: int, today: date, end_date: date
) -> list[date]:
    """Future charge dates for a subscription inferred from its own history.

    Empty when the subscription has missed two cycles — treated as cancelled.
    The cash projection had no recency bound at all, so a payee last charged
    years ago was projected forward forever: the walk stepped from its final
    charge up to today and then booked every future cycle.
    """
    interval = observed_interval_days(first_charge, last_charge, charge_count)
    if last_charge < today - timedelta(days=2 * interval):
        return []

    day = billing_day(first_charge, last_charge)
    out: list[date] = []
    nxt = step_cadence(last_charge, interval, anchor_day=day)
    while nxt <= end_date:
        if nxt >= today:
            out.append(nxt)
        nxt = step_cadence(nxt, interval, anchor_day=day)
    return out
