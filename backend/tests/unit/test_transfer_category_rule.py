"""The transfer category rule, exhaustively.

One rule, one home (domain/transfers.py), previously hand-written three ways:
transfer create asked it pair-wise, the edit planner leg-wise, the importer
over two concrete rows — and the repair pass, which needed it most, not at
all. The three phrasings agreed (this table is the proof they still do); the
missing fourth is pinned in test_transfer_repair.py.
"""

from igab.domain.transfers import (
    leg_may_carry_category,
    linking_breaks_category_rule,
    pair_may_carry_category,
)


class TestLegMayCarryCategory:
    def test_on_budget_leg_with_off_budget_partner_may(self):
        assert leg_may_carry_category(True, False) is True

    def test_on_budget_leg_with_on_budget_partner_may_not(self):
        # Internal movement; a category would count it as spending.
        assert leg_may_carry_category(True, True) is False

    def test_off_budget_leg_never_may(self):
        assert leg_may_carry_category(False, True) is False
        assert leg_may_carry_category(False, False) is False


class TestPairMayCarryCategory:
    def test_exactly_one_side_on_budget(self):
        assert pair_may_carry_category(True, False) is True
        assert pair_may_carry_category(False, True) is True

    def test_same_membership_may_not(self):
        assert pair_may_carry_category(True, True) is False
        assert pair_may_carry_category(False, False) is False


class TestLinkingBreaksCategoryRule:
    def test_uncategorized_pair_always_links(self):
        for a_on in (True, False):
            for b_on in (True, False):
                assert linking_breaks_category_rule(False, a_on, False, b_on) is False

    def test_both_categorized_never_links(self):
        for a_on in (True, False):
            for b_on in (True, False):
                assert linking_breaks_category_rule(True, a_on, True, b_on) is True

    def test_category_on_the_legal_side(self):
        assert linking_breaks_category_rule(True, True, False, False) is False
        assert linking_breaks_category_rule(False, False, True, True) is False

    def test_category_on_the_off_budget_side(self):
        assert linking_breaks_category_rule(True, False, False, True) is True
        assert linking_breaks_category_rule(False, True, True, False) is True

    def test_categorized_on_on_pair(self):
        assert linking_breaks_category_rule(True, True, False, True) is True
        assert linking_breaks_category_rule(False, True, True, True) is True
