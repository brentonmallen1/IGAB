"""What the cooling-off period actually did.

The headline is money that was wanted, waited on, and then not spent. Getting
it wrong in the flattering direction would make the feature a liar about the
one habit it exists to reinforce, so every bucket is pinned here — including
the unflattering one (bought before the period ended) and the honest refusal
to guess (no ending we can place).
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.guide.wishlist import DisciplineInput, is_cooling
from igab.guide.wishlist import discipline as discipline_on

ADDED = date(2026, 1, 1)
COOLS = ADDED + timedelta(days=30)
#: Long after every wish's wait: the buckets below are about endings, and an
#: open wish on this day is past its cooling-off.
LATER = COOLS + timedelta(days=100)


def discipline(wishes):
    return discipline_on(wishes, LATER)


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


def test_the_resisted_count_is_the_wishes_its_total_sums():
    """Every dropped wish is resisted money — waited on, abandoned early, or
    unplaceable. The card's count read `cooled_then_dropped` alone, so three
    wishes dropped on day three read "$300 — 0 talked yourself out of"."""
    d = discipline(
        [
            wish(status="dropped", dropped_at=COOLS + timedelta(days=5)),
            wish(status="dropped", dropped_at=ADDED + timedelta(days=3)),
            wish(status="dropped", dropped_at=ADDED + timedelta(days=4)),
            wish(status="dropped", dropped_at=None),
            wish(status="done", done_at=COOLS),
        ]
    )
    assert d.resisted_total == Decimal("400.00")
    assert d.resisted_count == 4
    assert d.resisted_count == d.cooled_then_dropped + d.dropped_early + 1  # + the unplaced drop


class TestWhatTheWaitDid:
    """The headline: of the wishes decided, how many waited the period out.

    "Resisted $600" was one wish dropped on day ten of a thirty-day wait — the
    wait played no part in it, and the report led with it anyway."""

    def test_an_early_drop_is_decided_but_did_not_wait_it_out(self):
        d = discipline([wish(status="dropped", dropped_at=ADDED + timedelta(days=10))])
        assert d.decided_count == 1
        assert d.waited_out_count == 0
        assert d.waited_out_share == 0.0
        # Still resisted money: the card keeps it, the headline does not.
        assert d.resisted_count == 1

    def test_the_share_counts_purchases_and_drops_alike(self):
        d = discipline(
            [
                wish(status="dropped", dropped_at=COOLS),
                wish(status="done", done_at=COOLS + timedelta(days=3)),
                wish(status="done", done_at=ADDED + timedelta(days=2)),
                wish(status="dropped", dropped_at=ADDED + timedelta(days=5)),
            ]
        )
        assert (d.waited_out_count, d.decided_count) == (2, 4)
        assert d.waited_out_share == 0.5

    def test_unplaceable_endings_and_open_wishes_are_not_decisions_it_can_judge(self):
        d = discipline(
            [
                wish(status="dropped", dropped_at=None),
                wish(status="done", done_at=COOLS, cooling_until=None),
                wish(),
                wish(status="done", done_at=COOLS),
            ]
        )
        assert d.decided_count == 1
        assert d.waited_out_share == 1.0

    def test_nothing_decided_is_no_share_not_zero(self):
        assert discipline([]).waited_out_share is None
        assert discipline([wish()]).waited_out_share is None

    def test_the_bought_count_is_the_wishes_its_total_sums(self):
        d = discipline(
            [
                wish(status="done", done_at=COOLS),
                wish(status="done", done_at=ADDED + timedelta(days=1)),
                wish(status="done", done_at=None),
                wish(status="dropped", dropped_at=COOLS),
            ]
        )
        assert d.bought_total == Decimal("300.00")
        assert d.bought_count == 3


class TestReadyToDecide:
    """An open wish past its wait is waiting on a decision, not the calendar."""

    def test_an_open_wish_inside_its_wait_is_still_cooling(self):
        d = discipline_on([wish()], COOLS - timedelta(days=1))
        assert (d.still_cooling, d.ready_to_decide) == (1, 0)

    def test_the_wait_is_over_on_its_end_date(self):
        # The same boundary a purchase or a drop reads: ending on the day the
        # period ends counts as having waited.
        d = discipline_on([wish()], COOLS)
        assert (d.still_cooling, d.ready_to_decide) == (0, 1)

    def test_a_wish_with_no_period_is_ready(self):
        d = discipline_on([wish(cooling_until=None)], ADDED)
        assert d.ready_to_decide == 1

    def test_the_two_partition_the_open_wishes(self):
        today = ADDED + timedelta(days=40)
        d = discipline_on(
            [
                wish(),
                wish(cooling_until=today + timedelta(days=5)),
                wish(cooling_until=None),
                wish(status="done", done_at=COOLS),
            ],
            today,
        )
        assert d.still_open == 3
        assert d.ready_to_decide == 2
        assert d.still_cooling == 1
        assert d.ready_to_decide + d.still_cooling == d.still_open


class TestIsCooling:
    def test_before_the_end_date(self):
        assert is_cooling(COOLS, COOLS - timedelta(days=1))

    def test_not_on_or_after_it(self):
        assert not is_cooling(COOLS, COOLS)
        assert not is_cooling(COOLS, COOLS + timedelta(days=1))

    def test_no_period_is_never_cooling(self):
        assert not is_cooling(None, ADDED)
