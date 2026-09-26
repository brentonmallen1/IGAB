"""The burn: the trailing thirty days against the sixty before them.

The Overview card and the Burn Rate chart each spelled this out, with floats
and gross outflows, and compared the thirty days with a ninety-day average
that contained them. Each case below is one of the differences that made:

- the windows (both copies): day 30 counting today as day 1 is in, day 31 is
  the prior window's newest day, day 90 its oldest, day 91 is nowhere;
- the comparison (both copies): the prior window ends the day before the
  thirty begin, so a spike in them moves one figure, not both;
- the unit (both copies divided a ninety-day total by 3): sixty days ÷ 2;
- the sign (both copies filtered `amount < 0`): a refund lowers the burn, as
  it lowers Spent This Period and Essentials;
- the Guide (`guide.concepts`, a third `90` and `3`): its essentials window is
  this lookback, derived rather than restated.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.activity_class import ActivityClass
from igab.domain.burn_rate import (
    LOOKBACK_DAYS,
    LOOKBACK_MONTHS,
    PRIOR_MONTHS,
    RECENT_DAYS,
    DayClassTotal,
    burn,
    burn_windows,
)
from igab.guide.concepts import ESSENTIALS_WINDOW_DAYS, TRAILING_MONTHS, essentials_since

D = Decimal
AS_OF = date(2026, 9, 25)
SPENDING = ActivityClass.SPENDING.value


def spend(days_back: int, amount: str, cls: str = SPENDING) -> DayClassTotal:
    """A signed day total `days_back` days before AS_OF (0 is AS_OF itself)."""
    return DayClassTotal(AS_OF - timedelta(days=days_back), cls, D(amount))


class TestWindows:
    def test_the_recent_window_is_today_and_the_29_days_before(self):
        w = burn_windows(AS_OF)
        assert (w.recent_start, w.recent_end) == (date(2026, 8, 27), AS_OF)
        assert (w.recent_end - w.recent_start).days + 1 == RECENT_DAYS == 30

    def test_the_prior_window_is_the_60_days_before_that(self):
        w = burn_windows(AS_OF)
        assert (w.prior_start, w.prior_end) == (date(2026, 6, 28), date(2026, 8, 26))
        assert (w.prior_end - w.prior_start).days + 1 == 60
        assert w.prior_end + timedelta(days=1) == w.recent_start

    def test_windows_count_days_not_calendar_months(self):
        # Across a 28-day February the recent window reaches back into January.
        w = burn_windows(date(2026, 3, 1))
        assert w.recent_start == date(2026, 1, 31)
        assert w.prior_start == date(2025, 12, 2)

    def test_today_is_in_the_recent_window(self):
        assert burn([spend(0, "-40.00")], AS_OF).recent == D("40.00")

    def test_day_30_is_recent_and_day_31_is_prior(self):
        result = burn([spend(29, "-200.00"), spend(30, "-700.00")], AS_OF)
        assert result.recent == D("200.00")
        # 700 over the prior sixty days is 350 per thirty.
        assert result.prior == D("350.00")

    def test_day_90_is_prior_and_day_91_is_nowhere(self):
        result = burn([spend(89, "-600.00"), spend(90, "-5000.00")], AS_OF)
        assert result.recent == D("0.00")
        assert result.prior == D("300.00")

    def test_a_row_after_today_is_not_money_burned(self):
        result = burn([spend(2, "-300.00"), spend(-1, "-900.00")], AS_OF)
        assert result.recent == D("300.00")
        assert result.prior == D("0.00")


class TestComparison:
    def test_the_prior_window_excludes_the_current_30(self):
        """The old ninety-day average held these thirty days too: a $900 spike
        moved it by $300 and hid the change it was there to show."""
        steady = [spend(d, "-300.00") for d in (40, 55, 70, 85)]
        spike = [spend(3, "-900.00")]
        before = burn(steady, AS_OF)
        after = burn(steady + spike, AS_OF)
        assert after.recent - before.recent == D("900.00")
        assert after.prior == before.prior == D("600.00")

    def test_the_prior_60_days_are_divided_by_2(self):
        assert PRIOR_MONTHS == 2
        result = burn([spend(45, "-1000.00"), spend(75, "-200.00")], AS_OF)
        assert result.prior == D("600.00")

    def test_both_figures_are_per_30_days_so_steady_spending_reads_equal(self):
        # $20 every day for ninety days: $600 in each thirty.
        daily = [spend(d, "-20.00") for d in range(90)]
        result = burn(daily, AS_OF)
        assert result.recent == result.prior == D("600.00")

    def test_half_cents_round_half_even(self):
        # 100.01 over sixty days is 50.005 per thirty.
        assert burn([spend(50, "-100.01")], AS_OF).prior == D("50.00")
        assert burn([spend(50, "-100.03")], AS_OF).prior == D("50.02")

    def test_runway_divides_the_recent_burn_by_its_days(self):
        assert burn([spend(5, "-900.00")], AS_OF).per_day == D("30")


class TestSign:
    def test_a_refund_lowers_the_recent_burn(self):
        result = burn([spend(4, "-300.00"), spend(2, "120.00")], AS_OF)
        assert result.recent == D("180.00")

    def test_a_refund_lowers_the_prior_burn(self):
        result = burn([spend(40, "-500.00"), spend(35, "100.00")], AS_OF)
        assert result.prior == D("200.00")

    def test_refunds_beyond_spending_read_negative_not_zero(self):
        """Net is net: a month of returns is money coming back, and flooring it
        at zero would state a figure no row adds up to."""
        result = burn([spend(4, "-50.00"), spend(2, "80.00")], AS_OF)
        assert result.recent == D("-30.00")

    def test_only_spending_counts(self):
        rows = [
            spend(3, "-100.00"),
            spend(3, "-2000.00", ActivityClass.SAVINGS.value),
            spend(3, "-750.00", ActivityClass.DEBT_PRINCIPAL.value),
            spend(3, "-40.00", ActivityClass.TRANSFER_INTERNAL.value),
            spend(3, "4000.00", ActivityClass.INCOME.value),
        ]
        assert burn(rows, AS_OF).recent == D("100.00")


class TestZero:
    def test_no_prior_spending_reads_zero_not_negative_zero(self):
        result = burn([spend(3, "-450.00")], AS_OF)
        assert result.prior == D("0")
        # Decimal("-0.00") == 0 too; the string is what a client would print.
        assert str(result.prior) == "0.00"

    def test_an_empty_budget_burns_nothing(self):
        result = burn([], AS_OF)
        assert (str(result.recent), str(result.prior)) == ("0.00", "0.00")
        assert result.per_day == 0

    def test_a_fully_refunded_window_is_positive_zero(self):
        result = burn([spend(3, "-80.00"), spend(1, "80.00")], AS_OF)
        assert str(result.recent) == "0.00"


class TestTheGuideReadsTheSameNinetyDays:
    def test_the_essentials_window_is_the_burn_lookback(self):
        assert ESSENTIALS_WINDOW_DAYS == LOOKBACK_DAYS == 90
        assert TRAILING_MONTHS == LOOKBACK_MONTHS == 3

    @pytest.mark.parametrize("as_of", [AS_OF, date(2026, 3, 1), date(2024, 2, 29)], ids=str)
    def test_both_start_on_the_same_day(self, as_of):
        assert essentials_since(as_of) == burn_windows(as_of).prior_start
