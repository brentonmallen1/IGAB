"""`unsettled`: has this ended wish left its envelope standing?

The rule behind the prompt. Pure, so every branch is one line — the wired
version (balances, archiving, the money move) is in
tests/integration/test_wishlist_settle.py.
"""

from decimal import Decimal

import pytest

from igab.guide.wishlist import could_be_unsettled, unsettled


def _ask(**over) -> bool:
    facts = {
        "status": "dropped",
        "owns_envelope": True,
        "envelope_live": True,
        "available": Decimal("400.00"),
        "has_goal": True,
    }
    return unsettled(**{**facts, **over})


class TestNothingToSettle:
    def test_an_open_wish_is_still_being_saved_for(self):
        assert _ask(status="open") is False

    def test_a_shared_envelope_is_not_the_wishs_to_settle(self):
        assert _ask(owns_envelope=False) is False

    def test_an_archived_or_deleted_envelope_is_settled_by_definition(self):
        """Archiving refuses while a balance remains, so there is nothing
        left to decide about one that got archived."""
        assert _ask(envelope_live=False) is False

    def test_an_empty_envelope_with_no_goal_is_finished(self):
        assert _ask(available=Decimal("0"), has_goal=False) is False


class TestUnfinishedBusiness:
    @pytest.mark.parametrize("status", ["dropped", "done"])
    def test_either_ending_leaves_money_behind(self, status):
        assert _ask(status=status) is True

    def test_an_empty_envelope_still_carrying_the_goal(self):
        """The goal was the wish's cost. Left alone, the budget page goes on
        asking for money towards something already decided against."""
        assert _ask(available=Decimal("0"), has_goal=True) is True

    def test_an_overspent_envelope_counts(self):
        """A hole is as unfinished as a surplus — more so, because archiving
        it as-is is what loses track of real money."""
        assert _ask(available=Decimal("-60.00"), has_goal=False) is True

    def test_money_with_no_goal_counts(self):
        assert _ask(has_goal=False) is True


class TestTheMoneyFreeHalf:
    """`could_be_unsettled` skips the balance query. It must never skip a
    wish `unsettled` would have said yes to — the two are one rule."""

    @pytest.mark.parametrize("status", ["open", "done", "dropped"])
    @pytest.mark.parametrize("owns", [True, False])
    @pytest.mark.parametrize("live", [True, False])
    @pytest.mark.parametrize("available", [Decimal("-60"), Decimal("0"), Decimal("400")])
    @pytest.mark.parametrize("has_goal", [True, False])
    def test_it_never_skips_unfinished_business(self, status, owns, live, available, has_goal):
        cheap = could_be_unsettled(status=status, owns_envelope=owns, envelope_live=live)
        full = unsettled(
            status=status,
            owns_envelope=owns,
            envelope_live=live,
            available=available,
            has_goal=has_goal,
        )
        assert cheap or not full
