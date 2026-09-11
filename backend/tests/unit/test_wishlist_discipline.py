"""What the cooling-off period actually did.

The headline is money that was wanted, waited on, and then not spent. Getting
it wrong in the flattering direction would make the feature a liar about the
one habit it exists to reinforce, so every bucket is pinned here — including
the unflattering one (bought before the period ended) and the honest refusal
to guess (no ending we can place).
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.guide.wishlist import DisciplineInput, discipline

ADDED = date(2026, 1, 1)
COOLS = ADDED + timedelta(days=30)


def wish(**over) -> DisciplineInput:
    base = {
        "status": "open",
        "cost": Decimal("100.00"),
        "created_at": ADDED,
        "cooling_until": COOLS,
        "done_at": None,
        "dropped_at": None,
    }
    return DisciplineInput(**{**base, **over})


class TestBuckets:
    def test_dropped_after_cooling_is_resisted(self):
        d = discipline([wish(status="dropped", dropped_at=COOLS + timedelta(days=2))])
        assert d.cooled_then_dropped == 1
        assert d.resisted_total == Decimal("100.00")
        assert d.bought_total == Decimal("0")

    def test_dropped_before_the_period_ended_is_not_what_the_period_did(self):
        # Still resisted money, still good discipline — but the cooling-off
        # period did not do it, and this bucket used to be reported under
        # "waited, then decided against". A wish abandoned on day three of
        # thirty is not a wish anyone waited on.
        d = discipline([wish(status="dropped", dropped_at=ADDED + timedelta(days=3))])
        assert d.dropped_early == 1
        assert d.cooled_then_dropped == 0
        assert d.unplaced == 0
        assert d.resisted_total == Decimal("100.00")

    def test_dropping_on_the_day_the_period_ends_counts_as_waiting(self):
        # The mirror of the bought-on-the-last-day case: the period is over on
        # its end date, so both sides of the fork read the boundary alike.
        d = discipline([wish(status="dropped", dropped_at=COOLS)])
        assert d.cooled_then_dropped == 1
        assert d.dropped_early == 0

    def test_bought_after_cooling_is_a_considered_purchase(self):
        d = discipline([wish(status="done", done_at=COOLS + timedelta(days=1))])
        assert d.cooled_then_bought == 1
        assert d.bought_early == 0
        assert d.bought_total == Decimal("100.00")

    def test_bought_before_the_period_ended_is_counted_as_such(self):
        # The date is editable after the fact, so this is reachable — and
        # worth showing rather than hiding. The number is for honesty about
        # the habit, not a score to protect.
        d = discipline([wish(status="done", done_at=ADDED + timedelta(days=3))])
        assert d.bought_early == 1
        assert d.cooled_then_bought == 0

    def test_buying_on_the_day_the_period_ends_counts_as_waiting(self):
        # The period is over on its end date; waiting one more day is not
        # what was asked of anyone.
        d = discipline([wish(status="done", done_at=COOLS)])
        assert d.cooled_then_bought == 1
        assert d.bought_early == 0

    def test_open_wishes_are_their_own_bucket(self):
        d = discipline([wish(), wish(cost=Decimal("40.00"))])
        assert d.still_open == 2
        assert d.open_total == Decimal("140.00")
        assert d.resisted_total == Decimal("0")


class TestWhatItRefusesToGuess:
    def test_a_drop_with_no_date_is_unplaced_not_resisted(self):
        # Wishes dropped before dropped_at existed. Counting them as resisted
        # would inflate the headline with data we do not have.
        d = discipline([wish(status="dropped", dropped_at=None)])
        assert d.unplaced == 1
        assert d.cooled_then_dropped == 0
        # The money is still real, and still was not spent.
        assert d.resisted_total == Decimal("100.00")

    def test_a_wish_with_no_cooling_period_is_unplaced(self):
        d = discipline([wish(status="done", done_at=ADDED + timedelta(days=2), cooling_until=None)])
        assert d.unplaced == 1
        assert d.cooled_then_bought == 0
        assert d.bought_early == 0

    def test_no_purchases_means_no_average_days(self):
        # None, not zero: an average of nothing is not "bought the same day".
        d = discipline([wish(), wish(status="dropped", dropped_at=COOLS)])
        assert d.avg_days_to_buy is None

    def test_an_empty_wishlist_claims_nothing(self):
        d = discipline([])
        assert d.avg_days_to_buy is None
        assert d.avg_wish_cost is None
        assert d.resisted_total == Decimal("0")


class TestAverages:
    def test_days_to_buy_measures_from_when_it_was_added(self):
        d = discipline(
            [
                wish(status="done", done_at=ADDED + timedelta(days=40)),
                wish(status="done", done_at=ADDED + timedelta(days=60)),
            ]
        )
        assert d.avg_days_to_buy == 50

    def test_average_cost_spans_every_wish_whatever_became_of_it(self):
        d = discipline(
            [
                wish(cost=Decimal("100.00")),
                wish(status="done", cost=Decimal("200.00"), done_at=COOLS),
                wish(status="dropped", cost=Decimal("300.00"), dropped_at=COOLS),
            ]
        )
        assert d.avg_wish_cost == Decimal("200.00")


def test_a_full_history_adds_up():
    """The buckets partition the closed wishes: nothing counted twice, nothing
    dropped on the floor."""
    wishes = [
        wish(status="done", done_at=COOLS + timedelta(days=1)),
        wish(status="done", done_at=ADDED + timedelta(days=2)),
        wish(status="dropped", dropped_at=COOLS + timedelta(days=5)),
        wish(status="dropped", dropped_at=ADDED + timedelta(days=4)),
        wish(status="dropped", dropped_at=None),
        wish(),
    ]
    d = discipline(wishes)

    closed = (
        d.cooled_then_bought + d.bought_early + d.cooled_then_dropped + d.dropped_early + d.unplaced
    )
    assert closed == 5
    assert d.still_open == 1
    assert closed + d.still_open == len(wishes)
