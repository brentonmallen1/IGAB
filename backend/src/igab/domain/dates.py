"""Calendar arithmetic over months.

Four implementations of "shift by a month" existed before this module, and
they disagreed at the edges the calendar actually has: a yearly schedule dated
29 February raised `ValueError`, and month bucketing silently discarded the day
where shifting must preserve it. The distinction that keeps them apart:

- `add_months` shifts a *date* and clamps the day to the target month's length.
  31 January + 1 month is 28 February, not an error and not 3 March.
- `month_start` / `month_end` name a *bucket*. Callers that group by month want
  these, and want the day discarded on purpose rather than by accident.

Both are total: every (date, int) pair has an answer, so no caller needs a
try/except around a calendar edge.
"""

import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month length.

    Clamping is what makes 29 Feb survivable: `add_months(date(2024, 2, 29), 12)`
    is 28 Feb 2025, where `d.replace(year=d.year + 1)` raises.
    """
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_start(d: date) -> date:
    """The first of `d`'s month — the canonical key for a month bucket."""
    return d.replace(day=1)


def month_end(d: date) -> date:
    """The last day of `d`'s month."""
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def months_between(start: date, end: date) -> int:
    """Whole months from `start` to `end`, floored at 1.

    The floor is a funding rule, not a calendar fact: a target due this month
    or already past still has to be met once, and dividing a shortfall by zero
    months has no meaning. Kept here so the backend and the budget UI cannot
    disagree about how many months are left.
    """
    return max(1, (end.year - start.year) * 12 + end.month - start.month)
