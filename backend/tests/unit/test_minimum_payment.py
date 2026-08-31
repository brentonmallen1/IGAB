"""What a card asks for this month.

The rule is the whole feature, and it is pure, so every case here is a line.
The one that matters most is the last in each class: a rule that cannot be
evaluated must produce nothing rather than a confident zero, because a zero
flows into a projection and a blank does not.
"""

from decimal import Decimal

import pytest

from igab.domain.minimum_payment import (
    FIXED,
    PERCENT_OF_BALANCE,
    MinimumPaymentRule,
    as_rule,
    fixed,
)


def rule(**kwargs) -> MinimumPaymentRule:
    return MinimumPaymentRule(**kwargs)


class TestAFixedRule:
    def test_asks_for_its_amount(self):
        assert fixed(Decimal("35.00")).due(Decimal("1000.00")) == Decimal("35.00")

    def test_asks_for_its_amount_even_against_a_smaller_balance(self):
        """`due` is the scheduling answer, and the gap is real money: in a
        cascade the unused $23 rolls on to the next debt this month."""
        assert fixed(Decimal("35.00")).due(Decimal("12.00")) == Decimal("35.00")

    def test_but_the_issuer_bills_only_what_is_owed(self):
        assert fixed(Decimal("35.00")).billed(Decimal("12.00")) == Decimal("12.00")

    def test_billed_covers_the_months_interest_too(self):
        """Clearing a $12 balance that charged $0.50 costs $12.50 — clamping
        to the balance alone would leave the interest unpaid forever."""
        assert fixed(Decimal("35.00")).billed(Decimal("12.00"), Decimal("0.50")) == Decimal("12.50")

    def test_a_cleared_balance_asks_for_nothing(self):
        assert fixed(Decimal("35.00")).due(Decimal("0")) == Decimal("0")
        assert fixed(Decimal("35.00")).billed(Decimal("0")) == Decimal("0")

    def test_a_credit_balance_asks_for_nothing(self):
        assert fixed(Decimal("35.00")).due(Decimal("-20.00")) == Decimal("0")

    def test_no_amount_is_not_a_rule(self):
        assert not fixed(None).usable
        assert fixed(None).due(Decimal("1000.00")) == Decimal("0")

    def test_a_zero_amount_is_not_a_rule_either(self):
        assert not fixed(Decimal("0")).usable


class TestAPercentageRule:
    def test_takes_its_slice_of_the_balance(self):
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2"), floor=Decimal("35"))
        assert r.due(Decimal("4000.00")) == Decimal("80.00")

    def test_the_floor_wins_when_the_slice_is_smaller(self):
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2"), floor=Decimal("35"))
        assert r.due(Decimal("1000.00")) == Decimal("35.00")

    def test_the_issuer_bills_no_more_than_is_owed(self):
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2"), floor=Decimal("35"))
        assert r.billed(Decimal("12.00")) == Decimal("12.00")
        assert r.due(Decimal("12.00")) == Decimal("35.00")

    def test_it_falls_as_the_balance_does(self):
        """The reason a rule beats a stored number: the same card asks for
        less every month, so a projection built on one figure is optimistic."""
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2"), floor=Decimal("35"))
        amounts = [r.due(Decimal(b)) for b in ("5000.00", "4000.00", "3000.00")]
        assert amounts == [Decimal("100.00"), Decimal("80.00"), Decimal("60.00")]
        assert amounts == sorted(amounts, reverse=True)

    def test_plus_interest_adds_the_months_charge(self):
        r = rule(
            kind=PERCENT_OF_BALANCE,
            percent=Decimal("1"),
            floor=Decimal("25"),
            plus_interest=True,
        )
        # 1% of 4000 = 40, plus 62.50 of interest.
        assert r.due(Decimal("4000.00"), Decimal("62.50")) == Decimal("102.50")

    def test_plus_interest_is_off_unless_asked_for(self):
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("1"), floor=Decimal("25"))
        assert r.due(Decimal("4000.00"), Decimal("62.50")) == Decimal("40.00")

    def test_a_percent_with_no_floor_is_not_a_rule(self):
        """Not merely imprecise — under it the debt never ends. Incomplete, so
        the UI asks for the floor rather than drawing a curve to infinity."""
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2"))
        assert not r.usable
        assert r.due(Decimal("4000.00")) == Decimal("0")

    def test_a_floor_with_no_percent_is_not_a_rule(self):
        assert not rule(kind=PERCENT_OF_BALANCE, floor=Decimal("35")).usable

    def test_the_result_is_whole_cents(self):
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2.5"), floor=Decimal("35"))
        due = r.due(Decimal("1337.77"))
        assert due == due.quantize(Decimal("0.01"))


class TestAnUnknownKind:
    def test_is_not_usable(self):
        assert not rule(kind="whatever", amount=Decimal("50")).usable

    def test_asks_for_nothing(self):
        assert rule(kind="whatever", amount=Decimal("50")).due(Decimal("1000")) == Decimal("0")


class TestSeenAsARule:
    def test_a_scalar_becomes_a_fixed_rule(self):
        """What lets the amortization loop take either without growing a
        second schedule beside the first."""
        assert as_rule(Decimal("120.00")) == fixed(Decimal("120.00"))
        assert as_rule(Decimal("120.00")).kind == FIXED

    def test_a_rule_is_left_alone(self):
        r = rule(kind=PERCENT_OF_BALANCE, percent=Decimal("2"), floor=Decimal("35"))
        assert as_rule(r) is r

    @pytest.mark.parametrize("amount", [Decimal("0"), Decimal("1"), Decimal("999.99")])
    def test_a_scalar_rule_answers_with_the_scalar(self, amount):
        assert as_rule(amount).due(Decimal("100000.00")) == amount
