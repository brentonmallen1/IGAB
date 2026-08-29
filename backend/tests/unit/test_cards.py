"""domain/cards.py — the credit split of a month's overspending, one case each.

The scenarios mirror the YNAB oracle's rules (integrations/ynab/oracle.py):
cash overspending is written off from Ready to Assign at the month boundary,
credit overspending rides on the card. These are the branch-level pins; the
whole-identity walk (swipe is TBA-neutral, overspend lands as uncovered debt,
assigning covers it) lives in tests/integration/test_credit_cards.py, and the
reconciliation invariant over generated histories in
TestReservationInvariant below — the check "The Unreleased Reservation"
showed the suite was missing.
"""

from datetime import date
from decimal import Decimal

from igab.domain.cards import (
    allocate_across_cards,
    cap_releases,
    card_funding,
    credit_floored_by_month,
    set_aside_through,
    synthetic_activity,
)
from igab.domain.carryover import monthly_end_balances

JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
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

    def test_a_net_inflow_month_carries_no_shortfall_onto_a_card(self):
        # Overspent 50 in a month whose card activity netted to a refund:
        # nothing rode onto the card, the whole 50 is cash overspending.
        assert credit_floored_by_month({JAN: D("-50")}, {JAN: D("-30")}) == {}


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


class TestCapReleases:
    def test_positive_deltas_pass_through(self):
        assert cap_releases({JAN: D("100"), FEB: D("40")})[0] == {JAN: D("100"), FEB: D("40")}

    def test_a_release_in_a_later_month_passes_whole(self):
        # The defect's minimal reproduction: January reserves 100, February's
        # refund releases it — the per-month clamp used to discard this and
        # the reservation stayed forever.
        assert cap_releases({JAN: D("100"), FEB: D("-100")})[0] == {JAN: D("100"), FEB: D("-100")}

    def test_a_release_is_capped_at_what_was_reserved(self):
        # Reserved 60 (the other 40 rode as uncovered debt); a 100 refund
        # releases the 60 and the rest pays down Uncovered via the balance.
        assert cap_releases({JAN: D("60"), FEB: D("-100")})[0] == {JAN: D("60"), FEB: D("-60")}

    def test_an_inflow_before_any_reservation_is_discarded(self):
        # A refund of pre-history spending: no reservation exists to release.
        assert cap_releases({JAN: D("-100"), FEB: D("40")})[0] == {FEB: D("40")}

    def test_releases_accumulate_across_months(self):
        # 100 reserved, released 60 then 60 more: the second release finds
        # only 40 left.
        assert cap_releases({JAN: D("100"), FEB: D("-60"), MAR: D("-60")})[0] == {
            JAN: D("100"),
            FEB: D("-60"),
            MAR: D("-40"),
        }


class TestCardFunding:
    def test_the_funded_swipe_scenario(self):
        # Assigned 150, spent 150 on the card: everything funds the card's
        # set-aside, nothing rides — the swipe is Ready-to-Assign-neutral.
        ends = {"groceries": monthly_end_balances({JAN: D("150")}, {JAN: D("-150")})}
        funded, floored, _ = card_funding(ends, {"groceries": {VISA: {JAN: D("150")}}})
        assert funded == {VISA: {JAN: D("150")}}
        assert floored == {}

    def test_the_overspent_swipe_scenario(self):
        # Assigned 100, spent 150 on the card: 100 funds, 50 rides.
        ends = {"groceries": monthly_end_balances({JAN: D("100")}, {JAN: D("-150")})}
        funded, floored, _ = card_funding(ends, {"groceries": {VISA: {JAN: D("150")}}})
        assert funded == {VISA: {JAN: D("100")}}
        assert floored == {"groceries": {JAN: D("50")}}

    def test_the_wholly_unfunded_swipe_funds_nothing(self):
        # Nothing assigned: the whole 150 rides as uncovered debt.
        ends = {"groceries": monthly_end_balances({}, {JAN: D("-150")})}
        funded, floored, _ = card_funding(ends, {"groceries": {VISA: {JAN: D("150")}}})
        assert funded == {}
        assert floored == {"groceries": {JAN: D("150")}}

    def test_two_categories_fund_one_card(self):
        ends = {
            "groceries": monthly_end_balances({JAN: D("100")}, {JAN: D("-100")}),
            "fuel": monthly_end_balances({JAN: D("40")}, {JAN: D("-40")}),
        }
        funded, floored, _ = card_funding(
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
        funded, floored, _ = card_funding(
            ends, {"groceries": {VISA: {JAN: D("100")}, AMEX: {JAN: D("40")}}}
        )
        assert floored == {"groceries": {JAN: D("60")}}
        assert funded == {VISA: {JAN: D("80")}}

    def test_a_category_with_no_card_spending_contributes_nothing(self):
        ends = {"rent": monthly_end_balances({JAN: D("1200")}, {JAN: D("-1200")})}
        funded, floored, _ = card_funding(ends, {})
        assert funded == {} and floored == {}

    def test_a_cross_month_refund_releases_its_reservation(self):
        # The Unreleased Reservation, minimal: January's funded purchase
        # reserves 100; February's refund of it releases the 100. The card's
        # balance returned to zero and now so does its envelope.
        ends = {
            "groceries": monthly_end_balances({JAN: D("100")}, {JAN: D("-100"), FEB: D("100")})
        }
        funded, floored, _ = card_funding(
            ends, {"groceries": {VISA: {JAN: D("100"), FEB: D("-100")}}}
        )
        assert funded == {VISA: {JAN: D("100"), FEB: D("-100")}}
        assert floored == {}

    def test_a_refund_of_ridden_spending_releases_only_the_funded_part(self):
        # 100 spent with 60 assigned: 60 reserved, 40 rides as uncovered.
        # A full refund next month releases the 60; the other 40 already paid
        # down the uncovered debt through the card's balance.
        ends = {
            "groceries": monthly_end_balances({JAN: D("60")}, {JAN: D("-100"), FEB: D("100")})
        }
        funded, floored, _ = card_funding(
            ends, {"groceries": {VISA: {JAN: D("100"), FEB: D("-100")}}}
        )
        assert funded == {VISA: {JAN: D("60"), FEB: D("-60")}}
        assert floored == {"groceries": {JAN: D("40")}}

    def test_a_release_stays_on_the_card_that_reserved(self):
        # Groceries reserved on both cards in January; February's refund on
        # visa releases only visa's reservation — amex keeps its own.
        ends = {
            "groceries": monthly_end_balances(
                {JAN: D("140")}, {JAN: D("-140"), FEB: D("100")}
            )
        }
        funded, floored, _ = card_funding(
            ends,
            {"groceries": {VISA: {JAN: D("100"), FEB: D("-100")}, AMEX: {JAN: D("40")}}},
        )
        assert funded == {VISA: {JAN: D("100"), FEB: D("-100")}, AMEX: {JAN: D("40")}}
        assert floored == {}

    def test_a_pre_reservation_inflow_is_discarded(self):
        # A refund of pre-history spending in January, a funded purchase in
        # February: the inflow has no reservation behind it and pays down
        # the balance (Uncovered) instead of going negative here.
        ends = {
            "groceries": monthly_end_balances({FEB: D("40")}, {JAN: D("100"), FEB: D("-40")})
        }
        funded, floored, _ = card_funding(
            ends, {"groceries": {VISA: {JAN: D("-100"), FEB: D("40")}}}
        )
        assert funded == {VISA: {FEB: D("40")}}
        assert floored == {}


class TestSetAsideThrough:
    def test_sums_assignments_and_synthetic_through_the_month(self):
        assert set_aside_through({JAN: D("50")}, {JAN: D("100"), FEB: D("-30")}, FEB) == D("120")

    def test_months_after_the_viewed_one_are_out(self):
        assert set_aside_through({FEB: D("50")}, {JAN: D("100")}, JAN) == D("100")

    def test_an_overpaid_month_carries_its_negative_forward(self):
        # Defect B's pin: paying 100 against a 60 reserve is a 40 credit
        # balance on the card, carried — not floored away at the boundary,
        # which ratcheted the set-aside upward by every overpaid month.
        synthetic = {JAN: D("-40")}  # funded 60, paid 100
        assert set_aside_through({}, synthetic, FEB) == D("-40")
        assert set_aside_through({}, synthetic, JAN) == D("-40")


class TestSyntheticActivity:
    def test_payments_subtract_from_funded_months(self):
        assert synthetic_activity({JAN: D("100")}, {JAN: D("60"), FEB: D("40")}) == {
            JAN: D("40"),
            FEB: D("-40"),
        }


class TestReservationInvariant:
    """set_aside + uncovered == −balance, at every month, for any history of
    categorized card spending, cross-month refunds, and cash-counterpart
    payments (no direct assignments, no plain deposits, no inflows that
    predate their reservations — each of those moves exactly one side, by
    design, and is pinned in its own test above or in the integration walk).

    Both defects were drift between the accumulated series (set_aside) and
    the directly-computed truth (the card's balance): the per-month clamp
    leaked on every cross-month refund, the boundary floor on every overpaid
    month. This walk compares the two, so it catches the class, not the
    instance.
    """

    def _check(self, assignments, events):
        """events: list of (month, kind, category, amount) with kind in
        {"spend", "refund", "pay"}; amounts positive. Walks month by month
        asserting the identity after every month."""
        months = sorted({m for m, *_ in events})
        categories = sorted({c for _, kind, c, _ in events if c is not None})
        balance = D("0")
        for upto in months:
            in_scope = [e for e in events if e[0] <= upto]
            activity: dict[str, dict[date, Decimal]] = {c: {} for c in categories}
            outflows: dict[str, dict[str, dict[date, Decimal]]] = {}
            payments: dict[date, Decimal] = {}
            balance = D("0")
            for m, kind, cat, amount in in_scope:
                if kind == "spend":
                    balance -= amount
                    activity[cat][m] = activity[cat].get(m, D("0")) - amount
                    per = outflows.setdefault(cat, {}).setdefault(VISA, {})
                    per[m] = per.get(m, D("0")) + amount
                elif kind == "refund":
                    balance += amount
                    activity[cat][m] = activity[cat].get(m, D("0")) + amount
                    per = outflows.setdefault(cat, {}).setdefault(VISA, {})
                    per[m] = per.get(m, D("0")) - amount
                elif kind == "pay":
                    balance += amount
                    payments[m] = payments.get(m, D("0")) + amount
            ends = {
                c: monthly_end_balances(assignments.get(c, {}), activity[c])
                for c in categories
            }
            outflows = {
                c: {
                    card: {m: v for m, v in series.items() if v != 0}
                    for card, series in by_card.items()
                }
                for c, by_card in outflows.items()
            }
            funded, _floored, _ = card_funding(ends, outflows)
            synthetic = synthetic_activity(funded.get(VISA, {}), payments)
            set_aside = set_aside_through({}, synthetic, upto)
            uncovered = max(D("0"), -balance - max(D("0"), set_aside))
            assert set_aside + uncovered == -balance, (
                f"through {upto}: set_aside={set_aside} uncovered={uncovered} "
                f"balance={balance}"
            )

    def test_the_minimal_reproduction(self):
        # January: funded purchase. February: its refund. Balance returns to
        # zero; before the fix the envelope kept the 100 forever.
        self._check(
            {"g": {JAN: D("100")}},
            [(JAN, "spend", "g", D("100")), (FEB, "refund", "g", D("100"))],
        )

    def test_an_overspent_purchase_refunded_later(self):
        self._check(
            {"g": {JAN: D("60")}},
            [(JAN, "spend", "g", D("100")), (FEB, "refund", "g", D("100"))],
        )

    def test_a_payment_landing_after_the_spending_it_covers(self):
        self._check(
            {"g": {JAN: D("100")}},
            [(JAN, "spend", "g", D("100")), (FEB, "pay", None, D("100"))],
        )

    def test_an_overpayment_is_a_credit_balance(self):
        # Pay 150 against 100 reserved: the card holds a 50 credit and the
        # envelope reads −50 — the identity still balances to the cent.
        self._check(
            {"g": {JAN: D("100")}},
            [(JAN, "spend", "g", D("100")), (FEB, "pay", None, D("150"))],
        )

    def test_the_ordinary_texture_of_a_real_ledger(self):
        # Multi-month, multi-category: partial refunds in later months,
        # payments out of step with spending, overspending riding along.
        self._check(
            {"g": {JAN: D("200"), FEB: D("200"), MAR: D("200")}, "f": {JAN: D("50")}},
            [
                (JAN, "spend", "g", D("180")),
                (JAN, "spend", "f", D("80")),  # 30 rides as uncovered
                (FEB, "refund", "g", D("40")),
                (FEB, "spend", "g", D("220")),
                (FEB, "pay", None, D("150")),
                (MAR, "refund", "f", D("60")),  # releases 50, 10 pays down debt
                (MAR, "spend", "g", D("90")),
                (MAR, "pay", None, D("300")),
            ],
        )
