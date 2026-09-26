"""`domain.tracking_start`: where counting began, placed on a chart's points,
and a change quoted like-for-like.

Every figure is invented and round enough to check on paper.
"""

from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from igab.domain.tracking_start import (
    STALE_AFTER_DAYS,
    Entry,
    StatedValue,
    entered,
    is_stale,
    like_for_like,
    place_entries,
    stated_total,
)
from igab.services.account_hygiene import DORMANT_AFTER_MONTHS, STALE_ASSET_VALUE_MONTHS

JUN_30, JUL_31, AUG_31, SEP_15 = (
    date(2026, 6, 30),
    date(2026, 7, 31),
    date(2026, 8, 31),
    date(2026, 9, 15),
)
CUTOFFS = [JUN_30, JUL_31, AUG_31, SEP_15]
SINCE = date(2026, 6, 1)


def acct(name: str, day: date, amount: str, kind="account") -> Entry:
    return Entry(kind=kind, id=name.lower(), name=name, day=day, amount=D(amount))


class TestPlaceEntries:
    def test_a_cutoff_day_closes_its_own_stretch_and_the_next_day_opens_the_next(self):
        buckets = place_entries(
            [acct("Harborstone", JUL_31, "100"), acct("Brokerage", date(2026, 8, 1), "200")],
            CUTOFFS,
            SINCE,
        )
        assert [[e.name for e in b] for b in buckets] == [[], ["Harborstone"], ["Brokerage"], []]

    def test_what_entered_before_the_first_stretch_is_not_news_on_this_chart(self):
        """It is already in the first point's balance."""
        buckets = place_entries([acct("Harborstone", date(2026, 5, 31), "1000")], CUTOFFS, SINCE)
        assert buckets == [[], [], [], []]

    def test_the_first_stretch_starts_at_since_inclusive(self):
        buckets = place_entries([acct("Harborstone", SINCE, "1000")], CUTOFFS, SINCE)
        assert entered(buckets[0]) == D("1000")

    def test_nothing_after_the_last_cutoff(self):
        buckets = place_entries([acct("Harborstone", date(2026, 9, 16), "1000")], CUTOFFS, SINCE)
        assert all(b == [] for b in buckets)

    def test_one_account_arriving_over_several_days_is_one_entry(self):
        """A card linked with a Starting Balance row and pre-start swipes
        arrives once: the sum, dated its first row."""
        buckets = place_entries(
            [
                acct("Sapphire Visa", date(2026, 7, 15), "-300"),
                acct("Sapphire Visa", date(2026, 7, 1), "-2000"),
            ],
            CUTOFFS,
            SINCE,
        )
        (card,) = buckets[1]
        assert card.amount == D("-2300")
        assert card.day == date(2026, 7, 1)

    def test_the_same_account_in_two_stretches_is_two_entries(self):
        """Pre-start history spread over two months marks both."""
        buckets = place_entries(
            [
                acct("Sapphire Visa", date(2026, 7, 1), "-2000"),
                acct("Sapphire Visa", date(2026, 8, 3), "-150"),
            ],
            CUTOFFS,
            SINCE,
        )
        assert [entered(b) for b in buckets] == [D("0"), D("-2000"), D("-150"), D("0")]

    def test_an_arrival_that_nets_to_zero_is_not_marked(self):
        buckets = place_entries(
            [acct("Cash", date(2026, 7, 2), "50"), acct("Cash", date(2026, 7, 9), "-50")],
            CUTOFFS,
            SINCE,
        )
        assert buckets[1] == []

    def test_largest_first_whatever_the_sign(self):
        buckets = place_entries(
            [
                acct("Brokerage", date(2026, 7, 5), "20000"),
                acct("Sapphire Visa", date(2026, 7, 1), "-2300"),
                acct("House", date(2026, 7, 20), "300000", kind="stated_asset"),
                acct("Loan", date(2026, 7, 21), "-50000", kind="manual_debt"),
            ],
            CUTOFFS,
            SINCE,
        )
        assert [e.name for e in buckets[1]] == ["House", "Loan", "Brokerage", "Sapphire Visa"]
        assert entered(buckets[1]) == D("267700")

    def test_an_asset_and_an_account_sharing_an_id_stay_apart(self):
        buckets = place_entries(
            [acct("Same", JUL_31, "10"), acct("Same", JUL_31, "20", kind="stated_asset")],
            CUTOFFS,
            SINCE,
        )
        assert len(buckets[1]) == 2

    def test_cutoffs_must_ascend(self):
        with pytest.raises(ValueError):
            place_entries([], [AUG_31, JUL_31], SINCE)

    def test_equal_cutoffs_file_into_the_first(self):
        """A range ending after today clamps both days to today."""
        buckets = place_entries([acct("Harborstone", SEP_15, "5")], [SEP_15, SEP_15], SINCE)
        assert [entered(b) for b in buckets] == [D("5"), D("0")]


class TestLikeForLike:
    def test_the_change_less_what_entered_after_the_first_point(self):
        """The whole shape of the audit: +277,900 on the chart, of which
        267,700 was the register filling in."""
        values = [D("1000"), D("18600"), D("318900"), D("278900")]
        entries = [D("0"), D("17700"), D("300000"), D("-50000")]
        assert like_for_like(values, entries) == D("10200")

    def test_the_first_points_own_entries_are_its_baseline(self):
        assert like_for_like([D("5000"), D("5100")], [D("5000"), D("0")]) == D("100")

    def test_a_debt_arriving_is_not_a_loss(self):
        assert like_for_like([D("1000"), D("-49000")], [D("0"), D("-50000")]) == D("0")

    def test_a_single_point_has_not_changed(self):
        assert like_for_like([D("700")], [D("700")]) == D("0")

    def test_no_points_is_no_change_to_state(self):
        assert like_for_like([], []) is None

    def test_one_entered_figure_per_point(self):
        with pytest.raises(ValueError):
            like_for_like([D("1"), D("2")], [D("0")])


HOUSE = StatedValue(
    kind="stated_asset",
    id="house",
    name="Maple St House",
    current=D("310000"),
    points=((date(2026, 8, 3), D("300000")), (date(2026, 9, 2), D("310000"))),
)
LOAN = StatedValue(
    kind="manual_debt",
    id="loan",
    name="Harborstone Loan",
    current=D("50000"),
    points=((date(2026, 9, 5), D("50000")),),
)


class TestStatedValue:
    def test_nothing_before_its_first_point(self):
        assert HOUSE.at(date(2026, 8, 2)) == D("0")

    def test_its_first_point_counts_on_its_own_day(self):
        assert HOUSE.at(date(2026, 8, 3)) == D("300000")

    def test_the_latest_point_on_or_before(self):
        assert HOUSE.at(date(2026, 9, 1)) == D("300000")
        assert HOUSE.at(date(2026, 9, 2)) == D("310000")

    def test_a_negative_point_counts_nothing(self):
        odd = StatedValue("manual_debt", "x", "Overpaid", D("0"), ((date(2026, 7, 1), D("-40")),))
        assert odd.at(date(2026, 8, 1)) == D("0")

    def test_as_of_is_the_newest_point(self):
        assert HOUSE.as_of == date(2026, 9, 2)
        assert StatedValue("manual_debt", "y", "Typed in", D("900"), ()).as_of is None

    def test_an_asset_enters_positive_at_its_first_point(self):
        assert HOUSE.entry(SEP_15) == Entry(
            "stated_asset", "house", "Maple St House", date(2026, 8, 3), D("300000")
        )

    def test_a_debt_enters_negative(self):
        assert LOAN.entry(SEP_15).amount == D("-50000")

    def test_a_zero_first_point_is_not_where_it_began_to_count(self):
        late = StatedValue(
            "stated_asset",
            "car",
            "Cedar Wagon",
            D("9000"),
            ((date(2026, 6, 10), D("0")), (date(2026, 7, 10), D("9000"))),
        )
        assert late.entry(SEP_15).day == date(2026, 7, 10)

    def test_a_debt_with_no_dated_balance_enters_today(self):
        """The sheet counts `manual_balance` on today only, so today is when
        it began to count."""
        typed = StatedValue("manual_debt", "z", "Family loan", D("1200"), ())
        assert typed.entry(SEP_15) == Entry("manual_debt", "z", "Family loan", SEP_15, D("-1200"))

    def test_one_that_never_counts_never_enters(self):
        assert StatedValue("manual_debt", "z", "Paid", D("0"), ()).entry(SEP_15) is None


class TestStatedTotal:
    def test_today_reads_the_current_figure(self):
        assert stated_total([HOUSE, LOAN], "stated_asset", SEP_15, SEP_15) == D("310000")

    def test_before_today_reads_the_step_function(self):
        assert stated_total([HOUSE, LOAN], "stated_asset", AUG_31, SEP_15) == D("300000")
        assert stated_total([HOUSE, LOAN], "manual_debt", AUG_31, SEP_15) == D("0")


class TestStale:
    TODAY = date(2026, 9, 15)

    def test_under_the_threshold_is_current(self):
        assert not is_stale(self.TODAY - timedelta(days=STALE_AFTER_DAYS - 1), self.TODAY)

    def test_at_the_threshold_is_stale(self):
        assert is_stale(self.TODAY - timedelta(days=STALE_AFTER_DAYS), self.TODAY)

    def test_no_date_is_stale(self):
        assert is_stale(None, self.TODAY)

    def test_the_chart_flags_before_the_hygiene_page_nags(self):
        """Deliberate divergence: the chart says a line is flat because
        nothing moved it (60 days); the account hygiene findings ask for an
        update at twelve months. The chart's must stay the shorter, or a
        figure the hygiene page calls stale would draw unflagged."""
        assert STALE_AFTER_DAYS < STALE_ASSET_VALUE_MONTHS * 30
        assert STALE_AFTER_DAYS < DORMANT_AFTER_MONTHS * 30
