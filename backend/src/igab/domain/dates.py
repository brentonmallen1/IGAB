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
from dataclasses import dataclass
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


def month_is_editable(month: date, *, import_month: date | None) -> bool:
    """Whether a month's plan can be written: every month of a budget with no
    anchor in force, and from the import month on of one that has.

    Before the import month an anchored budget shows YNAB's own figures,
    read-only (`db.models.ImportPlanMonth`); its arithmetic starts at B, so an
    assignment written there would move nothing anyone could see — and would
    reappear, uninvited, if the budget were switched to re-derive its history.
    `import_month` is B when the anchor is in force (`BudgetAnchor.month`),
    None otherwise. The server refuses on it; the client is served the answer
    (`BudgetMonthResponse.read_only`) rather than comparing months itself.
    """
    return import_month is None or month_start(month) >= import_month


def budget_month(day: date, *, anchor_month: date | None, late_eligible: bool) -> date:
    """The month a row counts in for budget math — its own month, except a
    late arrival, which counts in the import month.

    The pure twin of `txn_filters.BUDGET_MONTH`, for the layers that run no
    SQL (the card-scenario walk, the sample generator's own check). The two
    are irreducible duplication and a differential test holds them together
    (`tests/integration/test_late_arrivals.py`); this docstring is not the
    mechanism.

    `anchor_month` is the import anchor's month, B−1 (`ImportAnchor.month`),
    or None for a budget with no anchor in force — then every row counts in
    its own month, the byte-identical path. `late_eligible` is "not a YNAB
    row, on an account that came with the import" — see `LATE_ARRIVAL`.
    """
    own = month_start(day)
    if anchor_month is not None and late_eligible and own == anchor_month:
        return add_months(own, 1)
    return own


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


def months_ending(month: date, months: int) -> list[date]:
    """The `months` month buckets ending with `month`'s, oldest first.

    Calendar arithmetic only — NOT a report window. A report's "N months" is
    `report_window`, which never counts the running month among its N. This
    is for a rule that genuinely means "this month and the ones before it",
    like the wishlist's fallback pace over assigned money, where the current
    month's assignment is a plan, not a partial measurement.
    """
    current = month_start(month)
    return [add_months(current, -i) for i in range(months - 1, -1, -1)]


@dataclass(frozen=True)
class ReportWindow:
    """What "the last N months" means on every report: N COMPLETE months,
    and the running month beside them, never among them.

    One "12 months" picker gave some reports twelve complete months (Income by
    Source, Volatility), others eleven complete plus the running one (Income
    vs Expenses, Savings Rate, Variance, Plan vs Reality, Category History),
    and Anomalies thirteen. Savings Rate's headline flipped from +0.8% over
    complete months to -1.8% because a few days of a new month rode in it: the
    pay had not landed, the bills had. So a window names its complete months
    and its running month separately, and a report that draws the running
    month draws it apart — labelled "so far" — and never adds it to an
    average, a total or a headline.

    `complete` may be empty: a budget whose history starts this month has no
    complete month yet (`complete_month_window`'s clamp).
    """

    complete: tuple[date, ...]
    running: date

    @property
    def axis(self) -> list[date]:
        """Every month a series draws: the complete ones, then the running one."""
        return [*self.complete, self.running]

    @property
    def start(self) -> date:
        """The first day any query for this window reads."""
        return self.complete[0] if self.complete else self.running

    @property
    def complete_end(self) -> date:
        """The last day of the last complete month — where a headline stops."""
        return self.running - timedelta(days=1)

    def is_running(self, month: date) -> bool:
        return month_start(month) == self.running


def report_window(today: date, months: int, history_from: date | None = None) -> ReportWindow:
    """The last `months` complete months before `today`, and `today`'s month.

    `complete_month_window` is the arithmetic, and its history clamp applies:
    a month before the budget's first transaction is a month nobody recorded,
    not a month of zeros. `report_basics.history_window` supplies the history
    from the database.
    """
    start, end = complete_month_window(today, months, history_from)
    return ReportWindow(tuple(month_starts(start, end)), month_start(today))


def clamped_month_end(month: date, today: date) -> date:
    """The last day of `month`'s month, or `today` if that comes first.

    A series point stands for everything through its month's end, and the
    current month's end is a future date: summing through it counted rows
    dated after today as "now", and read a month-to-date figure under a label
    promising a trailing thirty days.
    """
    return min(month_end(month), today)


def months_touched(start: date, end: date, today: date) -> tuple[date, date]:
    """A date range widened to the whole months it touches: the 1st of
    `start`'s month through the end of `end`'s — never past `today`, so the
    running month reads month-to-date, as Plan vs Spent draws it.

    A plan is a month's (`domain.plan`), so a range that cuts a month cannot
    hold part of one to it: the whole month's assignment would stand against
    half its spending, and prorating an assignment invents a plan nobody made.
    The AI's `budget_vs_actual` reads this and reports the widened dates."""
    return month_start(start), clamped_month_end(end, today)


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


def complete_months_within(start: date, end: date, today: date) -> list[date]:
    """The months a date range holds WHOLE and that are over by `today`: the
    months a per-month average over an arbitrary range may divide by.

    For the reports whose window is a date range rather than "N months"
    (Spending Trends). A range from the 15th, or one ending on today, draws
    its first and last months partial; averaging them in as months spreads
    half a month across a whole one — the same fault `ReportWindow` removes
    from the month-windowed reports.
    """
    running = month_start(today)
    return [
        m for m in month_starts(start, end) if m >= start and month_end(m) <= end and m < running
    ]


def history_index(months: list[date], history_from: date | None) -> int:
    """The index of the first month in `months` the budget has history for.

    From the budget's first transaction — `earliest_date`, the start "All
    time" counts from — not from the first month with essentials spending.
    That was the first version, and it is a second answer to "when does this
    budget begin": a real month in which nothing essential was spent read as a
    month before the budget existed, so a household whose first Essential bill
    landed in March had March averaged alone instead of with the two quiet
    months before it.

    A budget with no transactions has no history to cut from: 0. One whose
    history starts after every month listed: `len(months)`.
    """
    if history_from is None:
        return 0
    start = month_start(history_from)
    return next((i for i, m in enumerate(months) if m >= start), len(months))


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


def previous_window(start: date, end: date) -> tuple[date, date]:
    """The equal-length window immediately before [start, end], both inclusive.

    What "vs prior period" means on a report. The Overview used to take the
    month before `start` whatever the range was, so a twelve-day "this month"
    was held against a whole thirty-one-day August and read as spending down by
    half, while the Cash Flow Sankey's "vs prior period" beside it compared
    equal lengths. The client's `previousWindow` (utils/dateWindow.ts) is the
    other side of this rule; `shared/previous_window_cases.json` holds both.
    """
    length = end - start
    prev_end = start - timedelta(days=1)
    return prev_end - length, prev_end


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


def weekday_counts(start: date, end: date) -> list[int]:
    """How many Mondays, Tuesdays … Sundays fall in [start, end], both ends
    included — seven counts, Monday first. All zero when `end` is before
    `start`.

    The divisor for a per-weekday average: "a typical Saturday" is the
    Saturdays' total over every Saturday in the window, the quiet ones
    included. Dividing by the Saturdays that had spending — or by the number
    of transactions — reads a household that shops once a fortnight as
    spending twice what it does.
    """
    days = (end - start).days + 1
    if days <= 0:
        return [0] * 7
    weeks, rest = divmod(days, 7)
    counts = [weeks] * 7
    for i in range(rest):
        counts[(start.weekday() + i) % 7] += 1
    return counts
