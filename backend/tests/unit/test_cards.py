"""domain/cards.py — the credit split of a month's overspending, one case each.

The scenarios mirror the YNAB oracle's rules (integrations/ynab/oracle.py):
cash overspending is written off from Ready to Assign at the month boundary,
credit overspending rides on the card. These are the branch-level pins; the
whole-identity walk (swipe is TBA-neutral, overspend lands as uncovered debt,
assigning covers it) lives in tests/integration/test_credit_cards.py.
"""

from datetime import date
from decimal import Decimal

from igab.domain.cards import (
    allocate_across_cards,
    card_funding,
    credit_floored_by_month,
    funded_credit_by_month,
)
from igab.domain.carryover import monthly_end_balances

JAN, FEB = date(2026, 1, 1), date(2026, 2, 1)
D = Decimal
AMEX, VISA = "amex-partner", "visa"  # sorted: amex first — allocation order


class TestCreditFlooredByMonth:
    def test_a_funded_month_floors_nothing(self):
        assert credit_floored_by_month({JAN: D("0")}, {JAN: D("150")}) == {}
        assert credit_floored_by_month({JAN: D("25")}, {JAN: D("150")}) == {}

    def test_cash_overspending_floors_nothing(self):
        # Ended negative with no card spending: all of it is written off from
        # Ready to Assign, exactly today's behavior.
        assert credit_floored_by_month({JAN: D("-50")}, {}) == {}

    def test_credit_overspending_rides_up_to_the_card_outflow(self):
        assert credit_floored_by_month({JAN: D("-50")}, {JAN: D("150")}) == {JAN: D("50")}

    def test_mixed_funding_splits_at_the_outflow(self):
        # Overspent 50 with only 20 on cards: 20 rides, 30 is written off.
        assert credit_floored_by_month({JAN: D("-50")}, {JAN: D("20")}) == {JAN: D("20")}

    def test_each_month_is_split_on_its_own(self):
        balances = {JAN: D("-50"), FEB: D("-10")}
        outflows = {JAN: D("20"), FEB: D("40")}
        assert credit_floored_by_month(balances, outflows) == {JAN: D("20"), FEB: D("10")}


class TestFundedCreditByMonth:
    def test_fully_funded_spending_flows_through_whole(self):
        assert funded_credit_by_month({JAN: D("0")}, {JAN: D("150")}) == {JAN: D("150")}

    def test_the_floored_part_never_reaches_the_set_aside(self):
        assert funded_credit_by_month({JAN: D("-50")}, {JAN: D("150")}) == {JAN: D("100")}

    def test_wholly_unfunded_spending_funds_nothing(self):
        assert funded_credit_by_month({JAN: D("-150")}, {JAN: D("150")}) == {}


class TestAllocateAcrossCards:
    def test_one_card_takes_it_all(self):
        assert allocate_across_cards(D("50"), {VISA: D("150")}) == {VISA: D("50")}

    def test_greedy_in_sorted_order_capped_at_each_outflow(self):
        # 60 to place; amex sorts first and can hold 40, visa takes the rest.
        assert allocate_across_cards(D("60"), {VISA: D("100"), AMEX: D("40")}) == {
            AMEX: D("40"),
            VISA: D("20"),
        }

    def test_zero_allocates_nothing(self):
        assert allocate_across_cards(D("0"), {VISA: D("100")}) == {}


class TestCardFunding:
    def test_the_funded_swipe_scenario(self):
        # Assigned 150, spent 150 on the card: everything funds the card's
        # set-aside, nothing rides — the swipe is Ready-to-Assign-neutral.
        ends = {"groceries": monthly_end_balances({JAN: D("150")}, {JAN: D("-150")})}
        funded, floored = card_funding(ends, {"groceries": {VISA: {JAN: D("150")}}})
        assert funded == {VISA: {JAN: D("150")}}
        assert floored == {}

    def test_the_overspent_swipe_scenario(self):
        # Assigned 100, spent 150 on the card: 100 funds, 50 rides.
        ends = {"groceries": monthly_end_balances({JAN: D("100")}, {JAN: D("-150")})}
        funded, floored = card_funding(ends, {"groceries": {VISA: {JAN: D("150")}}})
        assert funded == {VISA: {JAN: D("100")}}
        assert floored == {"groceries": {JAN: D("50")}}

    def test_two_categories_fund_one_card(self):
        ends = {
            "groceries": monthly_end_balances({JAN: D("100")}, {JAN: D("-100")}),
            "fuel": monthly_end_balances({JAN: D("40")}, {JAN: D("-40")}),
        }
        funded, floored = card_funding(
            ends,
            {"groceries": {VISA: {JAN: D("100")}}, "fuel": {VISA: {JAN: D("40")}}},
        )
        assert funded == {VISA: {JAN: D("140")}}
        assert floored == {}

    def test_one_category_overspent_across_two_cards(self):
        # Overspent 60, spent 40 on amex and 100 on visa: the ride is placed
        # greedily (amex holds 40, visa the remaining 20) and each card's
        # envelope receives only what was actually covered on it.
        ends = {"groceries": monthly_end_balances({JAN: D("80")}, {JAN: D("-140")})}
        funded, floored = card_funding(
            ends, {"groceries": {VISA: {JAN: D("100")}, AMEX: {JAN: D("40")}}}
        )
        assert floored == {"groceries": {JAN: D("60")}}
        assert funded == {VISA: {JAN: D("80")}}

    def test_a_category_with_no_card_spending_contributes_nothing(self):
        ends = {"rent": monthly_end_balances({JAN: D("1200")}, {JAN: D("-1200")})}
        funded, floored = card_funding(ends, {})
        assert funded == {} and floored == {}
