"""domain.transfers.pair_legs: which two synced rows are one movement.

A bank feed reports each account separately, so both legs of a transfer arrive
with ordinary payees and nothing links them. Every test here is a shape that
cost real money, or a shape that must never be paired on a guess.
"""

import uuid
from datetime import date
from decimal import Decimal as D

import pytest

from igab.domain.transfers import PairableLeg, pair_legs

CHECKING = uuid.uuid4()
CARD = uuid.uuid4()
SAVINGS = uuid.uuid4()
LOAN = uuid.uuid4()

JAN5 = date(2026, 1, 5)


def leg(
    account,
    amount,
    *,
    on_date=JAN5,
    on_budget=True,
    categorized=False,
    guess=False,
) -> PairableLeg:
    return PairableLeg(
        id=uuid.uuid4(),
        account_id=account,
        on_budget=on_budget,
        date=on_date,
        amount=D(amount),
        categorized=categorized,
        category_is_a_guess=guess,
    )


class TestTheShapesThatCostMoney:
    def test_a_card_payment_pairs(self) -> None:
        """The $4,600 case: checking out, card in, neither linked."""
        out = leg(CHECKING, "-4600")
        inn = leg(CARD, "4600")
        confident, review = pair_legs([out, inn], window_days=5)
        assert not review
        assert [(p.outflow_id, p.inflow_id) for p in confident] == [(out.id, inn.id)]

    def test_an_on_budget_savings_transfer_pairs(self) -> None:
        """Unpaired, this one *invents* $1,000 of Ready to Assign."""
        out = leg(CHECKING, "-1000")
        inn = leg(SAVINGS, "1000")
        confident, _ = pair_legs([out, inn], window_days=5)
        assert len(confident) == 1

    def test_an_off_budget_loan_payment_pairs_and_keeps_its_category(self) -> None:
        """A mortgage payment is budgeted on the checking side. The off-budget
        partner means that category is allowed to stay, so nothing is cleared."""
        out = leg(CHECKING, "-1200", categorized=True)
        inn = leg(LOAN, "1200", on_budget=False)
        confident, review = pair_legs([out, inn], window_days=5)
        assert not review
        assert confident[0].clears_categories == ()


class TestMutualUniqueness:
    def test_two_identical_movements_in_one_window_are_never_guessed(self) -> None:
        """Two $500 moves, two accounts, same week: four possible pairings and
        no basis to prefer one. Guessing would link the wrong two and look
        authoritative doing it."""
        legs = [
            leg(CHECKING, "-500", on_date=date(2026, 1, 5)),
            leg(CHECKING, "-500", on_date=date(2026, 1, 6)),
            leg(SAVINGS, "500", on_date=date(2026, 1, 5)),
            leg(SAVINGS, "500", on_date=date(2026, 1, 6)),
        ]
        confident, review = pair_legs(legs, window_days=5)
        assert confident == []
        assert review

    def test_one_outflow_two_possible_partners_goes_to_review(self) -> None:
        out = leg(CHECKING, "-500")
        legs = [out, leg(SAVINGS, "500"), leg(CARD, "500")]
        confident, review = pair_legs(legs, window_days=5)
        assert confident == []
        assert len(review) == 2

    def test_a_leg_is_used_once(self) -> None:
        legs = [leg(CHECKING, "-100"), leg(SAVINGS, "100"), leg(CARD, "-100")]
        confident, _ = pair_legs(legs, window_days=5)
        assert len(confident) <= 1


class TestWhatDisqualifies:
    def test_same_account_is_not_a_transfer(self) -> None:
        legs = [leg(CHECKING, "-100"), leg(CHECKING, "100")]
        assert pair_legs(legs, window_days=5) == ([], [])

    def test_a_near_miss_amount_is_a_different_question(self) -> None:
        """`domain/matching.py` scores approximate sameness. A transfer is one
        movement of one sum; 99.99 against 100.00 is not it."""
        legs = [leg(CHECKING, "-100.00"), leg(SAVINGS, "99.99")]
        assert pair_legs(legs, window_days=5) == ([], [])

    def test_outside_the_window_does_not_pair(self) -> None:
        legs = [
            leg(CHECKING, "-100", on_date=date(2026, 1, 1)),
            leg(SAVINGS, "100", on_date=date(2026, 1, 20)),
        ]
        assert pair_legs(legs, window_days=5) == ([], [])

    @pytest.mark.parametrize("days", [0, 5])
    def test_the_window_is_inclusive_at_its_edge(self, days: int) -> None:
        legs = [
            leg(CHECKING, "-100", on_date=date(2026, 1, 1)),
            leg(SAVINGS, "100", on_date=date(2026, 1, 1 + days)),
        ]
        confident, _ = pair_legs(legs, window_days=days)
        assert len(confident) == 1

    def test_two_inflows_do_not_pair(self) -> None:
        assert pair_legs([leg(CHECKING, "100"), leg(SAVINGS, "100")], window_days=5) == ([], [])


class TestCategoriesAreClearedOnlyWhenTheyAreGuesses:
    """Linking two on-budget legs must clear both categories — an internal
    movement is not spending. Whether that may happen unattended depends on who
    put the category there."""

    def test_a_syncs_own_guess_is_cleared_and_the_pair_links(self) -> None:
        out = leg(CHECKING, "-4600", categorized=True, guess=True)
        inn = leg(CARD, "4600", categorized=True, guess=True)
        confident, review = pair_legs([out, inn], window_days=5)
        assert not review
        assert set(confident[0].clears_categories) == {out.id, inn.id}

    def test_a_persons_category_is_never_cleared_unattended(self) -> None:
        out = leg(CHECKING, "-4600", categorized=True, guess=False)
        inn = leg(CARD, "4600", categorized=True, guess=True)
        confident, review = pair_legs([out, inn], window_days=5)
        assert confident == []
        assert review[0].clears_categories  # named, so review can show the price

    def test_an_uncategorized_pair_clears_nothing(self) -> None:
        confident, _ = pair_legs([leg(CHECKING, "-50"), leg(CARD, "50")], window_days=5)
        assert confident[0].clears_categories == ()
