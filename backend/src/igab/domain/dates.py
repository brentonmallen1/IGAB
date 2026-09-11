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
from datetime import date, timedelta


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


def months_spanned(start: date, end: date) -> int:
    """How many calendar months the range touches, inclusive of both ends.

    Not `months_between`: that one measures a funding horizon and floors at 1
    because a target due this month must still be met once. This one counts
    the months a report can actually draw — one, for a budget whose history
    starts this month — so the two differ by exactly the inclusive end and the
    floor. Both live here so neither gets rebuilt at a call site.
    """
    return max(0, (end.year - start.year) * 12 + end.month - start.month) + 1


def month_starts(start: date, end: date) -> list[date]:
    """The first of every month the range touches, oldest first, both ends
    included. A report's month axis: build it from the same bounds as the
    query, or a column and its cells drift a month apart.
    """
    months = []
    cur = month_start(start)
    while cur <= end:
        months.append(cur)
        cur = add_months(cur, 1)
    return months


def report_months(today: date, months: int) -> list[date]:
    """The `months` month buckets ending with `today`'s month, oldest first:
    the axis of a report that draws a SERIES — net worth, burn rate, plan
    discipline, a category's history — whose newest point is "now".

    Not `complete_month_window`, which is for a per-month AVERAGE and so
    leaves the running month out. A series draws it, clamped to today
    (`clamped_month_end`). Which window a report reads is its choice; the
    arithmetic is here.

    Exactly `months` buckets. The rule was spelled at a dozen call sites, and
    two drifted to `months + 1` — subtract the count, then include the current
    month too — so Savings and Subscriptions drew a thirteenth, empty column on
    the default twelve and divided their averages by it.
    """
    current = month_start(today)
    return [add_months(current, -i) for i in range(months - 1, -1, -1)]


def clamped_month_end(month: date, today: date) -> date:
    """The last day of `month`'s month, or `today` if that comes first.

    A series point stands for everything through its month's end, and the
    current month's end is a future date: summing through it counted rows
    dated after today as "now", and read a month-to-date figure under a label
    promising a trailing thirty days.
    """
    return min(month_end(month), today)


def complete_month_window(
    today: date, months: int, history_from: date | None = None
) -> tuple[date, date]:
    """The last `months` COMPLETE months: (first day of the oldest, last day of
    the previous month) — the window of every per-month AVERAGE.

    An average has to divide by months that happened. Dividing a twelve-month
    total by twelve on the 3rd of the month spreads eleven months of spending
    plus two days across twelve, and the figure is at its lowest exactly when
    a household checks it at the start of a month: Cost of Living quoted
    $2,750/month where the Essentials report, reading the same tag and the
    same query over its own window, quoted $3,000. The current month is never
    in the window — not even on its last day, since the day is not over — so
    every month in it is complete, and a report divides by all of them.

    `history_from` is when the budget's history starts. The window never
    reaches before that month: a zero-filled month before the first
    transaction is not a month of zero spending, it is a month nobody
    recorded. Volatility filled them in, so on "All time" — which counts the
    current month the window leaves out, and so always asked for one month
    too many — every category gained an invented zero, and a young budget on
    the default twelve months had steady grocery spending reading as the most
    volatile thing in it. A budget whose history starts this month has no
    complete month, and the window comes back empty (start after end).

    One helper because the window was spelled out four times — volatility,
    seasonality, anomalies, essentials — and seasonality then drew its axis
    from a fifth spelling that ran through the current month instead.
    """
    current = month_start(today)
    start = add_months(current, -months)
    if history_from is not None:
        start = max(start, month_start(history_from))
    return start, current - timedelta(days=1)


def trailing_start(today: date, days: int) -> date:
    """The first day of the `days`-day window that ends on `today`, both ends
    inclusive.

    `today - timedelta(days=days)` is the trap: with inclusive bounds it spans
    `days + 1` days. The Overview's burn figures and the Burn Rate chart were
    fixed to 29 and 89 while the Essentials figure kept `today - 90` — a 91-day
    window, divided by three, beside a 90-day one — so on a register tagged
    entirely Essential the "subset" read higher than the burn it is part of.
    """
    return today - timedelta(days=days - 1)


def weekday_occurrences(month: date, weekday: int) -> int:
    """How many times `weekday` (0=Monday … 6=Sunday) falls in `month`'s
    month: 4 or 5, and only ever 4 in a 28-day February.

    A weekly target's duty for the month is its amount times this — "$50
    every Friday" is five Fridays in some months and four in others, and a
    flat ×4 under-asks a fifth week while a flat ×4.33 asks for money on no
    Friday at all.
    """
    if not 0 <= weekday <= 6:
        raise ValueError(f"weekday must be 0..6, got {weekday}")
    first = month.replace(day=1)
    days = calendar.monthrange(first.year, first.month)[1]
    offset = (weekday - first.weekday()) % 7
    return (days - offset + 6) // 7 if offset < days else 0
