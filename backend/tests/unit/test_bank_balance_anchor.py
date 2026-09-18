"""The opening anchor's one assertable claim.

The anchor is the row that makes drift zero, so the drift indicator can never
check it afterwards. What it CAN be checked against is the account's own kind:
anchoring sets the ledger to the reported balance, and a liability that ends
up holding money is impossible however the figures got there.

The cases that are deliberately NOT refused matter as much as the ones that
are — two earlier spellings of this rule tested the gap's sign and the gap's
magnitude, and each would have refused the ordinary first sync that the whole
feature exists to perform.
"""

from decimal import Decimal

from igab.domain.bank_balance import anchor_verdict, describe_refused_anchor

ASSET = {"is_liability": False}
DEBT = {"is_liability": True}


class TestAgreement:
    def test_agreement_needs_no_anchor(self):
        v = anchor_verdict(Decimal("-2690.00"), Decimal("-2690.00"), **DEBT)
        assert v.reason == "agrees"
        assert not v.should_write
        assert not v.refused

    def test_agreement_is_not_a_refusal(self):
        """`agrees` is the ordinary no-op of a healthy account and must never
        reach the sync log as a fault."""
        assert not anchor_verdict(Decimal("100"), Decimal("100"), **ASSET).refused


class TestOrdinaryAnchorsAreWritten:
    def test_an_empty_ledger_anchors_anything(self):
        assert anchor_verdict(Decimal("-2690.00"), Decimal("0"), **DEBT).should_write
        assert anchor_verdict(Decimal("11325.82"), Decimal("0"), **ASSET).should_write

    def test_a_gap_far_larger_than_the_register_is_ordinary(self):
        """A card carried in with three months of history: one sync window of
        rows against a full balance. Pre-window history is routinely many
        times the register, so the gap's size carries no signal."""
        v = anchor_verdict(Decimal("-2690.00"), Decimal("-200.00"), **DEBT)
        assert v.should_write
        assert v.gap == Decimal("-2490.00")

    def test_a_gap_opposite_in_sign_to_the_register_is_ordinary(self):
        """A checking account whose 90-day window happens to net negative
        while the balance is healthily positive. Refusing this would break
        the anchor on ordinary cash accounts."""
        v = anchor_verdict(Decimal("2400.00"), Decimal("-100.00"), **ASSET)
        assert v.should_write
        assert v.gap == Decimal("2500.00")

    def test_an_overpaid_card_may_anchor_negative(self):
        """A liability reported at a credit balance is unusual but possible,
        and the rule only refuses a POSITIVE reported balance."""
        assert anchor_verdict(Decimal("-40.00"), Decimal("0"), **DEBT).should_write


class TestTheOneRefusal:
    def test_a_liability_that_would_end_up_holding_money_is_refused(self):
        """The Anchor That Doubled, in one line: a lender-frame feed reports
        +2,690 on a card. Anchoring would leave the register holding 2,690,
        and a card cannot hold money."""
        v = anchor_verdict(Decimal("2690.00"), Decimal("-200.00"), **DEBT)
        assert v.reason == "holds_money"
        assert v.refused
        assert not v.should_write

    def test_the_same_figures_on_an_asset_are_fine(self):
        """The rule is about the account's kind, not the arithmetic."""
        assert anchor_verdict(Decimal("2690.00"), Decimal("-200.00"), **ASSET).should_write

    def test_a_refusal_names_both_figures_and_what_to_do(self):
        v = anchor_verdict(Decimal("2690.00"), Decimal("-200.00"), **DEBT)
        line = describe_refused_anchor("Sapphire Visa", v, Decimal("2690.00"), Decimal("-200.00"))
        assert "Sapphire Visa" in line
        assert "2,690.00" in line
        assert "-200.00" in line
        assert "reconcile" in line.lower()
