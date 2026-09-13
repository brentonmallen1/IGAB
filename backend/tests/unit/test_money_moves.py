"""The parts of the money explorer that decide nothing themselves.

Classes come from the classifier and budget terms are pinned against the real
budget in `tests/integration/test_money_moves_agreement.py`. What is left is
wiring, tested here: which leg carries the category, how legs are signed, and
that the report families are the reports' own class tuples.
"""

from decimal import Decimal

import pytest

from igab.domain.activity_class import (
    COST_OF_LIVING_CLASSES,
    SPENDING_CLASSES,
    ActivityClass,
    ActivityReason,
)
from igab.domain.money_moves import (
    SHAPES,
    AccountShape,
    CategoryKind,
    Direction,
    LegRole,
    Move,
    MoveKind,
    ReportFamily,
    category_role,
    explain_move,
    figures,
    leg_facts,
    legs,
    report_families,
)

D = Decimal
CASH = AccountShape(False, True)
CARD = AccountShape(True, True)
BROKERAGE = AccountShape(False, False, True)
CAR = AccountShape(False, False, False)
LOAN = AccountShape(True, False)


def transfer(frm, to, category=CategoryKind.NONE):
    return Move(MoveKind.TRANSFER, frm, D("1000"), category, to_account=to)


class TestWhichLegCarriesTheCategory:
    def test_the_on_budget_side_of_a_boundary_transfer(self):
        assert category_role(transfer(CASH, BROKERAGE)) is LegRole.FROM
        assert category_role(transfer(CAR, CASH)) is LegRole.TO

    @pytest.mark.parametrize(("frm", "to"), [(CASH, CASH), (CASH, CARD), (BROKERAGE, LOAN)])
    def test_neither_side_when_both_are_on_the_same_side(self, frm, to):
        assert category_role(transfer(frm, to)) is None

    def test_a_plain_transaction_only_on_budget(self):
        on = Move(MoveKind.TRANSACTION, CASH, D("5"), direction=Direction.OUT)
        off = Move(MoveKind.TRANSACTION, BROKERAGE, D("5"), direction=Direction.IN)
        assert category_role(on) is LegRole.ACCOUNT
        assert category_role(off) is None

    def test_a_category_nowhere_allowed_is_dropped_and_reported(self):
        move = transfer(CASH, CASH, CategoryKind.ORDINARY)
        assert all(leg.category is CategoryKind.NONE for leg in legs(move))
        classes = [(ActivityClass.TRANSFER_INTERNAL, ActivityReason.INTERNAL_TRANSFER)] * 2
        assert explain_move(move, classes).category_applied is False


class TestLegs:
    def test_a_transfer_leaves_one_account_and_arrives_in_the_other(self):
        out, arrive = legs(transfer(CASH, CAR, CategoryKind.ORDINARY))
        assert (out.amount, arrive.amount) == (D("-1000"), D("1000"))
        assert (out.category, arrive.category) == (CategoryKind.ORDINARY, CategoryKind.NONE)
        assert (out.counterpart, arrive.counterpart) == (CAR, CASH)

    def test_facts_for_a_plain_row_coalesce_as_the_column_readers_do(self):
        (leg,) = legs(Move(MoveKind.TRANSACTION, CASH, D("1"), direction=Direction.IN))
        facts = leg_facts(leg)
        assert not facts.transfer_leg and not facts.tracked_counterpart
        assert facts.counterpart_is_liability is False
        assert facts.counterpart_counts_as_savings is True

    def test_facts_carry_the_counterparts_savings_flag(self):
        out, _ = legs(transfer(CASH, CAR))
        assert (
            leg_facts(out).tracked_counterpart and not leg_facts(out).counterpart_counts_as_savings
        )

    def test_tag_kinds_set_their_own_input_only(self):
        (leg,) = legs(
            Move(MoveKind.TRANSACTION, CASH, D("1"), CategoryKind.SAVINGS, direction=Direction.OUT)
        )
        facts = leg_facts(leg)
        assert facts.tagged_savings and facts.categorized
        assert not facts.tagged_debt and not facts.in_system_group

    def test_a_move_refuses_a_shape_that_does_not_fit_its_kind(self):
        with pytest.raises(ValueError):
            Move(MoveKind.TRANSFER, CASH, D("1"))
        with pytest.raises(ValueError):
            Move(MoveKind.TRANSACTION, CASH, D("1"))
        with pytest.raises(ValueError):
            Move(MoveKind.TRANSACTION, CASH, D("0"), direction=Direction.IN)


class TestReportFamiliesAreTheReportsTuples:
    def test_spending_and_cost_of_living(self):
        for cls in ActivityClass:
            assert (ReportFamily.SPENDING in report_families(cls)) == (cls in SPENDING_CLASSES)
            assert (ReportFamily.COST_OF_LIVING in report_families(cls)) == (
                cls in COST_OF_LIVING_CLASSES
            )

    def test_a_transfer_between_budget_accounts_counts_nowhere(self):
        assert report_families(ActivityClass.TRANSFER_INTERNAL) == []

    def test_an_off_budget_leg_counts_nowhere_whatever_its_class(self):
        move = transfer(CASH, BROKERAGE)
        explained = explain_move(
            move,
            [
                (ActivityClass.SAVINGS, ActivityReason.TRANSFER_TO_TRACKED_ASSET),
                (ActivityClass.SAVINGS, ActivityReason.TRANSFER_TO_TRACKED_ASSET),
            ],
        )
        assert explained.legs[0].counted_in and explained.legs[1].counted_in == []
        assert explained.class_totals == {"savings": D("-1000")}
        assert explained.net_worth_delta == 0


class TestPlannedSpendByTag:
    def _explain(self, category, cls, direction=Direction.OUT):
        move = Move(MoveKind.TRANSACTION, CASH, D("250"), category, direction=direction)
        return explain_move(move, [(cls, ActivityReason.TAGGED_SAVINGS)]).legs[0]

    def test_a_savings_tagged_outflow_is_spent_against_the_plan(self):
        assert self._explain(CategoryKind.SAVINGS, ActivityClass.SAVINGS).planned_spend_by_tag

    def test_not_a_refund_and_not_other_tags(self):
        assert not self._explain(
            CategoryKind.SAVINGS, ActivityClass.SAVINGS, Direction.IN
        ).planned_spend_by_tag
        assert not self._explain(
            CategoryKind.DEBT_PRINCIPAL, ActivityClass.DEBT_PRINCIPAL
        ).planned_spend_by_tag


def test_figures_read_the_class_buckets():
    f = figures({"income": D("6000"), "spending": D("-2550"), "debt_principal": D("-900")})
    assert (f.income, f.spending, f.cost_of_living, f.debt_principal) == (
        D("6000"),
        D("2550"),
        D("3450"),
        D("900"),
    )
    assert f.savings_rate == 0.0 and f.savings_rate_with_debt == 0.15


def test_every_account_shape_is_explained_once():
    keys = {(s.is_liability, s.on_budget, s.counts_as_savings) for s in SHAPES}
    assert len(keys) == len(SHAPES) == 5
