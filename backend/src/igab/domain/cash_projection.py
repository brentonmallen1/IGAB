"""Cash projection: where the cash balance lands if things carry on.

The Cash Projection report and the assistant's `cash_projection` tool both read
`project` here. `ReportService.cash_projection` only gathers the inputs — the
start balance, the fixed events (schedules and subscriptions), and the
register's recent net flow per day — and hands them in. Pure: no session, no
clock. `today` is the reader's day (`client_today` when the browser sent one),
and the draws come from a generator seeded by it, so two calls on one day
agree.

The paths replay recent cash in and out — paychecks included — on top of the
fixed events. That is what "if things carry on" means, and it is why each of
the rules below exists:

**Every calendar day is history, quiet ones included.** The sampled layer used
to group the register by date, so only days that HAD rows entered it. A bank
posts almost nothing on a weekend — a handful of Saturdays in six months had a
row at all — so every simulated Saturday drew one of that handful, most of
them expensive, and the median slid by the price of a busy Saturday every week
while the real balance held level. `zero_filled` makes a day with no rows a
zero flow.

**Runs, not days.** Even zero-filled, drawing each future day on its own made
pay random: a Friday drawn from six months of Fridays is a payday some fraction
of the time, so a twice-monthly salary arrived a binomial number of times and
the band came out about three times as wide as any real ninety days had been.
A path now copies contiguous runs of real history (`BlockSampler`), so a run
carries its paydays with the bills between them.

**Day 0 is the balance.** The start balance already holds today's rows, and a
path used to add a sampled day on top of it, so the median began below the
"Current Balance" printed beside it. Draws begin at day 1. A fixed event
booked on today — a schedule due or overdue and not yet entered — still lands
on day 0, as it does on the "Scheduled only" line.

**The warning says how likely.** `goes_negative_date` is the first day the
median is below zero, `p10_negative_date` the first day the low band is. With
the median alone, a budget whose median brushed zero read "goes negative" on
most days' seeds and not on the rest — the warning was the seed's, not the
budget's.
"""

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import accumulate
from typing import NamedTuple

from igab.domain.dates import trailing_start
from igab.domain.money import quantize_cents

ZERO = Decimal("0")

#: How far back the paths look: the six months ending yesterday.
HISTORY_DAYS = 180

#: The length of one replayed run. Four whole weeks, so a run that starts on the
#: path's weekday stays on it, and long enough to hold two paydays of any
#: twice-monthly, biweekly or weekly salary together with the bills they pay.
BLOCK_DAYS = 28

#: Simulated paths per projection. Enough that p10 — the 100th lowest — moves
#: little from one day's seed to the next.
PATHS = 1000

#: The bands served per day, as (field, quantile).
BANDS: tuple[tuple[str, float], ...] = (
    ("p10", 0.10),
    ("p25", 0.25),
    ("p50", 0.50),
    ("p75", 0.75),
    ("p90", 0.90),
)


@dataclass(frozen=True)
class HistoryWindow:
    """The days whose net flow the paths replay, both ends inclusive."""

    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def history_window(today: date, first_row: date | None) -> HistoryWindow | None:
    """The `HISTORY_DAYS` ending yesterday, or from `first_row` when the
    register is younger than that. None when no day qualifies: no rows, or none
    before today.

    Ending yesterday: today's rows are already in the start balance, and today
    is not over. Starting no earlier than the first row: a budget three weeks
    old has three weeks of history, and zero-filling the months before it
    existed would read as months of nothing happening, pulling every path
    toward flat.
    """
    if first_row is None:
        return None
    end = today - timedelta(days=1)
    start = max(trailing_start(end, HISTORY_DAYS), first_row)
    if start > end:
        return None
    return HistoryWindow(start, end)


def zero_filled(flows: Iterable[tuple[date, Decimal]], window: HistoryWindow) -> list[Decimal]:
    """Net flow for every calendar day of `window`, oldest first. A day with no
    row is a zero flow — it happened, and nothing moved. Several entries for
    one day add up; entries outside the window are ignored."""
    days = [ZERO] * window.days
    for day, amount in flows:
        if window.start <= day <= window.end:
            days[(day - window.start).days] += amount
    return days


class BlockSampler:
    """Draws a path as indices into a window's days: contiguous runs, each
    starting on a random history day of the same weekday as the path day it
    fills, and running until it has copied `block_days` days or reaches the
    end of the history — then a new run starts the same way.

    Weekday-matched starts keep a run's weekends on the path's weekends; the
    run itself keeps a payday's spacing from the next one.
    """

    def __init__(self, window: HistoryWindow, block_days: int = BLOCK_DAYS) -> None:
        if block_days < 1:
            raise ValueError("block_days must be at least 1")
        self.size = window.days
        self.block_days = block_days
        by_weekday: list[list[int]] = [[] for _ in range(7)]
        for i in range(window.days):
            by_weekday[(window.start + timedelta(days=i)).weekday()].append(i)
        # Under a week of history some weekday has no day of its own. Any day
        # stands in for it rather than the path stopping there.
        everything = list(range(window.days))
        self._starts = [days or everything for days in by_weekday]

    def indices(self, first_day: date, days: int, rng: random.Random) -> list[int]:
        """History-day indices for `first_day` and the `days - 1` days after."""
        out: list[int] = []
        i = left = 0
        weekday = first_day.weekday()
        for _ in range(days):
            if left == 0 or i == self.size:
                i = rng.choice(self._starts[weekday])
                left = self.block_days
            out.append(i)
            i += 1
            left -= 1
            weekday = (weekday + 1) % 7
        return out


class BandPoint(NamedTuple):
    """One projected day: the bands across the simulated paths, and the path
    with the fixed events alone."""

    day: date
    p10: Decimal
    p25: Decimal
    p50: Decimal
    p75: Decimal
    p90: Decimal
    deterministic: Decimal


@dataclass(frozen=True)
class Projection:
    points: list[BandPoint]
    #: The first day the median is below zero.
    goes_negative_date: date | None
    #: The first day the low band (1 path in 10 ends lower) is below zero.
    #: Never later than `goes_negative_date`.
    p10_negative_date: date | None


def project(
    *,
    start_balance: Decimal,
    today: date,
    horizon_days: int,
    history: Sequence[Decimal],
    window: HistoryWindow | None,
    fixed: Mapping[date, Decimal],
    paths: int = PATHS,
    seed: int | None = None,
) -> Projection:
    """Days 0..`horizon_days` from `today`.

    `history` is `zero_filled` over `window`, and holds only the flows the
    fixed layer does not re-apply — the caller's partition. `fixed` is the
    fixed events' net per day. Every path, and the deterministic line, starts
    from `start_balance` plus whatever is fixed on today; sampled flows begin
    on day 1. `seed` defaults to today's ordinal: reproducible within a day.
    """
    days = [today + timedelta(days=k) for k in range(horizon_days + 1)]
    fixed_by_day = [fixed.get(d, ZERO) for d in days]
    deterministic = list(accumulate(fixed_by_day, initial=start_balance))[1:]

    if window is None or not history:
        # Nothing to replay: every path is the deterministic one.
        columns = [[balance] for balance in deterministic]
    else:
        if len(history) != window.days:
            raise ValueError("history must hold one flow per day of its window")
        sampler = BlockSampler(window)
        rng = random.Random(today.toordinal() if seed is None else seed)
        columns = [[] for _ in days]
        for _ in range(paths):
            balance = deterministic[0]
            columns[0].append(balance)
            drawn = sampler.indices(days[1], horizon_days, rng) if horizon_days else []
            for k, i in enumerate(drawn, start=1):
                balance += fixed_by_day[k] + history[i]
                columns[k].append(balance)

    points: list[BandPoint] = []
    for day, column, det in zip(days, columns, deterministic, strict=True):
        column.sort()
        bands = [quantize_cents(column[int(len(column) * q)]) for _, q in BANDS]
        points.append(BandPoint(day, *bands, deterministic=quantize_cents(det)))

    return Projection(
        points=points,
        goes_negative_date=next((p.day for p in points if p.p50 < 0), None),
        p10_negative_date=next((p.day for p in points if p.p10 < 0), None),
    )
