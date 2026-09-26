"""Cash projection's simulation: `domain.cash_projection`.

Each class below is one of the ways the old simulation misread the register:

- the history (`TestHistoryWindow`, `TestZeroFilled`): it grouped rows by date,
  so a day with no rows never entered it and a quiet weekend sampled a rare
  busy one; and a young budget must not be padded with the months before its
  first row;
- the draws (`TestBlockSampler`): single weekday-matched days made a
  twice-monthly salary arrive a random number of times;
- day 0 (`TestDayZero`): a sampled day was added on top of a balance that
  already held today's rows;
- the warning (`TestCrossingDates`): only the median's crossing was served.

Every `today` is fixed, so the seeded draws are the same on every run; the
scenario tests also sweep a spread of days, because the seed is today's
ordinal and a property that held on one seed only would be the seed's.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.cash_projection import (
    BLOCK_DAYS,
    HISTORY_DAYS,
    BlockSampler,
    HistoryWindow,
    history_window,
    project,
    zero_filled,
)

D = Decimal
TODAY = date(2026, 9, 25)  # a Friday
ZERO = D("0")

#: Thirteen consecutive days, so every weekday — and every seed's weekday
#: alignment — is exercised by the sweeps.
SWEEP = [TODAY + timedelta(days=k) for k in range(0, 91, 7)] + [
    TODAY + timedelta(days=k) for k in range(1, 7)
]


def window_ending_yesterday(today: date, days: int) -> HistoryWindow:
    return HistoryWindow(today - timedelta(days=days), today - timedelta(days=1))


def quiet_weekends(today: date) -> tuple[HistoryWindow, list[Decimal]]:
    """Twenty-four weeks that net to zero: +$300 pay every Monday, -$50 every
    weekday, and nothing on a weekend — except every sixth Saturday, a -$300
    one. The bank's week: a Saturday with rows is rare, and it is expensive."""
    window = window_ending_yesterday(today, 168)
    history = []
    saturdays = 0
    for i in range(window.days):
        day = window.start + timedelta(days=i)
        flow = ZERO
        if day.weekday() == 0:
            flow += 300
        if day.weekday() < 5:
            flow -= 50
        if day.weekday() == 5:
            saturdays += 1
            if saturdays % 6 == 0:
                flow -= 300
        history.append(flow)
    assert sum(history) == 0
    return window, history


def twice_monthly_pay(today: date) -> tuple[HistoryWindow, list[Decimal]]:
    """Six months of +$2,000 on the 1st and the 15th and -$130 every day."""
    window = window_ending_yesterday(today, HISTORY_DAYS)
    history = []
    for i in range(window.days):
        day = window.start + timedelta(days=i)
        history.append(D(2000) - 130 if day.day in (1, 15) else D(-130))
    return window, history


def run(
    history: list[Decimal],
    window: HistoryWindow | None,
    *,
    start: str = "0",
    today: date = TODAY,
    horizon: int = 90,
    fixed: dict[date, Decimal] | None = None,
):
    return project(
        start_balance=D(start),
        today=today,
        horizon_days=horizon,
        history=history,
        window=window,
        fixed=fixed or {},
    )


class TestHistoryWindow:
    def test_no_rows_is_no_history(self):
        assert history_window(TODAY, None) is None

    def test_twenty_six_whole_weeks_ending_yesterday(self):
        w = history_window(TODAY, date(2020, 1, 1))
        assert w is not None
        assert w.end == TODAY - timedelta(days=1)
        assert w.start == TODAY - timedelta(days=HISTORY_DAYS)
        assert w.days == HISTORY_DAYS == 182

    def test_a_young_budget_keeps_its_newest_whole_weeks(self):
        """Ten days of register are one whole week: the sampler wraps a run
        from yesterday to the first day, and only whole weeks land it on the
        same weekday. The three oldest days go."""
        w = history_window(TODAY, TODAY - timedelta(days=10))
        assert w == HistoryWindow(TODAY - timedelta(days=7), TODAY - timedelta(days=1))

    def test_under_a_week_keeps_every_day(self):
        """No weekday to keep under a week, so nothing is dropped."""
        first = TODAY - timedelta(days=5)
        assert history_window(TODAY, first) == HistoryWindow(first, TODAY - timedelta(days=1))

    def test_a_young_budget_starts_at_its_first_row(self):
        """Three weeks of register are three weeks of history. Zero-filling
        back to 180 days would read 159 days of nothing happening."""
        first = TODAY - timedelta(days=21)
        w = history_window(TODAY, first)
        assert w == HistoryWindow(first, TODAY - timedelta(days=1))
        assert w.days == 21

    def test_a_first_row_exactly_at_the_limit_keeps_the_full_window(self):
        first = TODAY - timedelta(days=HISTORY_DAYS)
        assert history_window(TODAY, first) == HistoryWindow(first, TODAY - timedelta(days=1))

    def test_a_first_row_yesterday_is_one_day(self):
        assert history_window(TODAY, TODAY - timedelta(days=1)).days == 1

    def test_a_first_row_today_or_later_is_no_history(self):
        """Today's rows are in the start balance, and today is not over."""
        assert history_window(TODAY, TODAY) is None
        assert history_window(TODAY, TODAY + timedelta(days=3)) is None


class TestZeroFilled:
    def test_a_day_without_rows_is_a_zero_flow(self):
        w = HistoryWindow(date(2026, 9, 1), date(2026, 9, 7))
        flows = [(date(2026, 9, 1), D("-40")), (date(2026, 9, 5), D("2000"))]
        assert zero_filled(flows, w) == [D(-40), 0, 0, 0, D(2000), 0, 0]

    def test_entries_for_one_day_add_up(self):
        w = HistoryWindow(date(2026, 9, 1), date(2026, 9, 2))
        flows = [(date(2026, 9, 2), D("-12.50")), (date(2026, 9, 2), D("-7.25"))]
        assert zero_filled(flows, w) == [0, D("-19.75")]

    def test_entries_outside_the_window_are_ignored(self):
        w = HistoryWindow(date(2026, 9, 1), date(2026, 9, 2))
        flows = [(date(2026, 8, 31), D("-99")), (date(2026, 9, 3), D("99"))]
        assert zero_filled(flows, w) == [0, 0]

    def test_across_a_month_and_a_year_end(self):
        w = HistoryWindow(date(2025, 12, 30), date(2026, 1, 2))
        flows = [(date(2025, 12, 31), D("-5")), (date(2026, 1, 1), D("5"))]
        assert zero_filled(flows, w) == [0, D(-5), D(5), 0]

    def test_no_rows_at_all_is_every_day_zero(self):
        w = HistoryWindow(date(2026, 9, 1), date(2026, 9, 30))
        assert zero_filled([], w) == [ZERO] * 30


class TestBlockSampler:
    def _drawn(self, window, first_day, days, seed=7):
        return BlockSampler(window).indices(first_day, days, random.Random(seed))

    def test_every_drawn_day_shares_the_path_days_weekday(self):
        window = window_ending_yesterday(TODAY, HISTORY_DAYS)
        first = TODAY + timedelta(days=1)
        for k, i in enumerate(self._drawn(window, first, 365)):
            assert (window.start + timedelta(days=i)).weekday() == (
                first + timedelta(days=k)
            ).weekday()

    def test_runs_are_contiguous_and_break_only_after_a_full_block(self):
        """A run copies consecutive history days, wrapping from yesterday to
        the first day; a new one starts only once it has copied BLOCK_DAYS."""
        window = window_ending_yesterday(TODAY, HISTORY_DAYS)
        drawn = self._drawn(window, TODAY + timedelta(days=1), 365)
        run = 1
        for prev, cur in zip(drawn, drawn[1:], strict=False):
            if cur == (prev + 1) % window.days and run < BLOCK_DAYS:
                run += 1
                continue
            assert run == BLOCK_DAYS, (prev, cur, run)
            run = 1

    def test_a_run_reaching_yesterday_wraps_to_the_first_day(self):
        """Two weeks of history: a run carries on from yesterday into the
        oldest day, which falls on the weekday after yesterday's."""
        window = window_ending_yesterday(TODAY, 14)
        drawn = self._drawn(window, TODAY + timedelta(days=1), 120)
        wraps = [k for k in range(1, len(drawn)) if drawn[k - 1] == 13 and drawn[k] == 0]
        assert wraps
        assert window.start.weekday() == (window.end + timedelta(days=1)).weekday()

    def test_every_history_day_is_equally_likely(self):
        """Every run that could start on a Saturday, laid end to end, covers
        each history day the same number of times.

        A run used to stop at yesterday, so the oldest days were reachable only
        from the few runs that began before them — the first four weeks were
        drawn a fraction as often as the rest, and a register whose oldest
        weeks held a bonus projected $3k lower over ninety days than the same
        register with the bonus last."""

        class NthStart(random.Random):
            def __init__(self, n):
                super().__init__(0)
                self.n = n

            def choice(self, seq):
                return seq[self.n]

        window = window_ending_yesterday(TODAY, HISTORY_DAYS)
        sampler = BlockSampler(window)
        saturday = TODAY + timedelta(days=(5 - TODAY.weekday()) % 7 or 7)
        counts = [0] * window.days
        n = 0
        while True:
            try:
                drawn = sampler.indices(saturday, BLOCK_DAYS, NthStart(n))
            except IndexError:
                break
            for i in drawn:
                counts[i] += 1
            n += 1
        assert n == HISTORY_DAYS // 7
        assert set(counts) == {BLOCK_DAYS // 7}

    def test_a_history_of_part_weeks_is_refused(self):
        """Wrapping lands on the same weekday only over whole weeks;
        `history_window` never builds anything else."""
        with pytest.raises(ValueError):
            BlockSampler(window_ending_yesterday(TODAY, 10))

    def test_under_a_week_of_history_every_weekday_still_draws(self):
        """Some weekday has no day of its own in a 3-day history; any day
        stands in for it rather than the path stopping."""
        window = window_ending_yesterday(TODAY, 3)
        drawn = self._drawn(window, TODAY + timedelta(days=1), 30)
        assert len(drawn) == 30
        assert set(drawn) <= {0, 1, 2}

    def test_one_day_of_history_is_that_day_every_day(self):
        window = window_ending_yesterday(TODAY, 1)
        assert self._drawn(window, TODAY + timedelta(days=1), 14) == [0] * 14

    def test_the_same_seed_draws_the_same_path(self):
        window = window_ending_yesterday(TODAY, HISTORY_DAYS)
        first = TODAY + timedelta(days=1)
        assert self._drawn(window, first, 90, seed=3) == self._drawn(window, first, 90, seed=3)

    def test_a_block_length_below_one_is_refused(self):
        with pytest.raises(ValueError):
            BlockSampler(window_ending_yesterday(TODAY, 7), block_days=0)


class TestDayZero:
    def test_day_zero_is_the_start_balance_with_a_busy_history(self):
        """The start balance already holds today's rows. A sampled day on top
        of it put the median below "Current Balance" before anything had
        happened."""
        window, history = twice_monthly_pay(TODAY)
        p = run(history, window, start="9000.00").points[0]
        assert p.day == TODAY
        assert p.p10 == p.p25 == p.p50 == p.p75 == p.p90 == D("9000.00")

    def test_a_fixed_event_booked_on_today_lands_on_day_zero_for_every_band(self):
        """An overdue schedule is booked on today and is not in the balance
        yet. Every band carries it."""
        window, history = twice_monthly_pay(TODAY)
        p = run(history, window, start="9000.00", fixed={TODAY: D("-250")}).points[0]
        assert p.p10 == p.p25 == p.p50 == p.p75 == p.p90 == D("8750.00")

    def test_sampled_flows_begin_on_day_one(self):
        window = window_ending_yesterday(TODAY, 14)
        points = run([D(-10)] * 14, window, start="100").points
        assert [p.p50 for p in points[:4]] == [D(100), D(90), D(80), D(70)]

    def test_a_zero_day_horizon_is_the_balance_alone(self):
        window, history = twice_monthly_pay(TODAY)
        projection = run(history, window, start="42.00", horizon=0)
        assert [(p.day, p.p50) for p in projection.points] == [(TODAY, D("42.00"))]


class TestNothingToReplay:
    def test_no_history_collapses_every_band_onto_the_fixed_path(self):
        fixed = {TODAY + timedelta(days=3): D("2000"), TODAY + timedelta(days=10): D("-1200")}
        points = run([], None, start="5000", horizon=30, fixed=fixed).points
        for p in points:
            assert p.p10 == p.p25 == p.p50 == p.p75 == p.p90
        assert points[0].p50 == D(5000)
        assert points[2].p50 == D(5000)
        assert points[3].p50 == D(7000)
        assert points[10].p50 == points[30].p50 == D(5800)

    def test_an_all_zero_history_does_too(self):
        window = window_ending_yesterday(TODAY, HISTORY_DAYS)
        points = run([ZERO] * HISTORY_DAYS, window, start="5000", horizon=30).points
        assert {p.p10 for p in points} == {p.p90 for p in points} == {D("5000.00")}

    def test_a_history_that_does_not_match_its_window_is_refused(self):
        window = window_ending_yesterday(TODAY, 10)
        with pytest.raises(ValueError):
            run([ZERO] * 9, window)


class TestQuietDays:
    def test_quiet_weekends_project_flat_when_the_real_net_is_flat(self):
        """The register nets to zero, and so must the median, to within the
        one expensive Saturday a stretch may or may not hold.

        The old simulation grouped the rows by date, so the Saturday bucket
        held only the four busy Saturdays: every simulated Saturday cost $300,
        and the median fell about $3,200 in ninety days from a register that
        had not moved at all."""
        for today in SWEEP:
            window, history = quiet_weekends(today)
            end = run(history, window, today=today).points[-1]
            assert abs(end.p50) <= 300, (today, end)
            assert end.p10 >= -900 and end.p90 <= 900, (today, end)

    def test_a_weekend_draws_a_weekend(self):
        """Weekday alignment survives the zero-fill and the runs: a register
        that only ever moves on weekdays projects a weekend that moves
        nothing, on every path. From a Friday, the balance holds through
        Saturday and Sunday and falls again on Monday."""
        window = window_ending_yesterday(TODAY, 28)
        history = []
        for i in range(window.days):
            day = window.start + timedelta(days=i)
            history.append(ZERO if day.weekday() >= 5 else D(-20))
        points = run(history, window, start="1000", horizon=9).points
        assert TODAY.weekday() == 4
        # Sat and Sun move nothing; Mon-Fri each cost 20.
        assert [p.p50 for p in points] == [
            D(n) for n in (1000, 1000, 1000, 980, 960, 940, 920, 900, 900, 900)
        ]


class TestRuns:
    def test_a_twice_monthly_salary_arrives_about_as_often_as_it_does(self):
        """Ninety real days of this register hold six paydays, give or take one.
        Drawn day by day, a Friday was a payday some fraction of the time,
        so the count of paydays was binomial and the p10–p90 band spanned
        five to six paychecks. Copied in runs it spans two or three, and the
        median lands where ninety real days do."""
        for today in SWEEP:
            window, history = twice_monthly_pay(today)
            end = run(history, window, today=today).points[-1]
            assert end.p90 - end.p10 <= 6000, (today, end)
            assert abs(end.p50 - 300) <= 2000, (today, end)

    def test_bands_are_ordered_on_every_day(self):
        window, history = twice_monthly_pay(TODAY)
        for p in run(history, window, start="3000", horizon=180).points:
            assert p.p10 <= p.p25 <= p.p50 <= p.p75 <= p.p90

    def test_the_same_day_projects_the_same_bands(self):
        window, history = twice_monthly_pay(TODAY)
        assert run(history, window) == run(history, window)

    def test_amounts_are_whole_cents(self):
        window = window_ending_yesterday(TODAY, 3)
        points = run([D("-0.3333"), D("0.0049"), D("-1.005")], window, horizon=30).points
        for p in points:
            for value in (p.p10, p.p25, p.p50, p.p75, p.p90):
                assert value == value.quantize(D("0.01"))


class TestCrossingDates:
    def test_a_uniform_decline_crosses_on_the_same_day_for_both(self):
        """$100 falling $10 a day: 100 - 10k first goes below zero on day 11
        (day 0 draws nothing)."""
        window = window_ending_yesterday(TODAY, 21)
        projection = run([D(-10)] * 21, window, start="100", horizon=30)
        assert projection.goes_negative_date == TODAY + timedelta(days=11)
        assert projection.p10_negative_date == TODAY + timedelta(days=11)

    def test_a_rare_large_bill_warns_on_p10_only(self):
        """One $3,000 day in six months of nothing, against $1,000: a path
        that replays it goes $2,000 under, and fewer than half of them do in
        sixty days. The median never crosses, so `goes_negative_date` stays
        None — and the old warning, which read the median alone, said nothing
        at all about a one-in-three chance of an overdraft."""
        for today in SWEEP:
            window = window_ending_yesterday(today, HISTORY_DAYS)
            history = [ZERO] * HISTORY_DAYS
            history[90] = D(-3000)
            projection = run(history, window, start="1000", today=today, horizon=60)
            assert projection.goes_negative_date is None, today
            crossed = projection.p10_negative_date
            assert crossed is not None, today
            first_low = next(p.day for p in projection.points if p.p10 < 0)
            assert crossed == first_low

    def test_a_negative_start_crosses_today(self):
        projection = run([], None, start="-5", horizon=10)
        assert projection.goes_negative_date == projection.p10_negative_date == TODAY

    def test_a_balance_that_touches_zero_has_not_crossed(self):
        window = window_ending_yesterday(TODAY, 7)
        projection = run([D(-10)] * 7, window, start="100", horizon=10)
        assert projection.points[10].p50 == 0
        assert projection.goes_negative_date is None
        assert projection.p10_negative_date is None
