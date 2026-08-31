"""domain/cards.py — the credit split of a month's overspending, one case each.

The scenarios mirror the YNAB oracle's rules (integrations/ynab/oracle.py):
cash overspending is written off from Ready to Assign at the month boundary,
credit overspending rides on the card. These are the branch-level pins; the
whole-identity walk (swipe is TBA-neutral, overspend lands as uncovered debt,
assigning covers it) lives in tests/integration/test_credit_cards.py, and the
reconciliation invariant over generated histories in
TestReservationInvariant below — the check "The Unreleased Reservation"
showed the suite was missing, and which "The Refused Repayment" then showed
had been qualified out of usefulness.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from igab.domain.cards import (
    CardReserve,
    allocate_capped,
    card_funding,
    card_reserve,
    credit_floored_by_month,
    release_split,
    reserve_discrepancy,
)
from igab.domain.carryover import available_at, monthly_end_balances, sum_through

JAN, FEB, MAR, APR = (date(2026, m, 1) for m in (1, 2, 3, 4))
D = Decimal
AMEX, VISA = "amex-partner", "visa"  # sorted: amex first — allocation order


def funding(assignments, activity, outflows, category="groceries", card_categories=None):
    """`card_funding` for one category, spelled the way the scenarios read."""
    return card_funding(
        {category: assignments}, {category: activity}, {category: outflows}, card_categories or {}
    )


def reserve_of(cf, card, payments=None, assignments=None):
    """One card's reserve out of a walk, for tests that only care about the
    total. `assignments` is for the pre-`card_categories` scenarios, where the
    walk never saw them."""
    reserve = card_reserve(cf, card, payments or {})
    if assignments:
        reserve = replace(reserve, assignments=assignments)
    return reserve


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


class TestAllocateCapped:
    def test_one_card_takes_it_all(self):
        assert allocate_capped(D("50"), {VISA: D("150")}) == {VISA: D("50")}

    def test_greedy_in_sorted_order_capped_at_each_outflow(self):
        # 60 to place; amex sorts first and can hold 40, visa takes the rest.
        assert allocate_capped(D("60"), {VISA: D("100"), AMEX: D("40")}) == {
            AMEX: D("40"),
            VISA: D("20"),
        }

    def test_zero_allocates_nothing(self):
        assert allocate_capped(D("0"), {VISA: D("100")}) == {}


class TestReleaseSplit:
    """The three layers a card inflow passes through. Replaces `cap_releases`,
    which had only two answers — release, or refuse — and refusing is what cost
    a real budget a five-figure phantom overspend ("The Refused Repayment")."""

    def test_a_release_discharges_uncovered_before_reserved_cash(self):
        # 40 riding, 60 reserved, a 100 refund: the debt goes first.
        assert release_split(D("100"), D("40"), D("60")) == (D("40"), D("60"), D("0"))

    def test_a_release_inside_the_uncovered_layer_touches_no_reserve(self):
        assert release_split(D("30"), D("40"), D("60")) == (D("30"), D("0"), D("0"))

    def test_a_release_beyond_both_layers_becomes_a_residual(self):
        # Nothing refused: the excess reduces the reserve past zero, which is a
        # real position — the card is holding budget money.
        assert release_split(D("100"), D("10"), D("20")) == (D("10"), D("20"), D("70"))

    def test_a_negative_reserve_never_releases_more_reserve(self):
        assert release_split(D("50"), D("0"), D("-30")) == (D("0"), D("0"), D("50"))

    def test_a_release_of_nothing_splits_into_nothing(self):
        assert release_split(D("0"), D("40"), D("60")) == (D("0"), D("0"), D("0"))

    def test_the_parts_always_sum_to_the_release(self):
        for release, ridden, reserved in [
            (D("100"), D("40"), D("60")),
            (D("7.53"), D("0"), D("0")),
            (D("100"), D("10"), D("-20")),
            (D("0.01"), D("1000"), D("1000")),
        ]:
            assert sum(release_split(release, ridden, reserved)) == release


class TestCardFunding:
    def test_the_funded_swipe_scenario(self):
        # Assigned 150, spent 150 on the card: everything funds the card's
        # set-aside, nothing rides — the swipe is Ready-to-Assign-neutral.
        cf = funding({JAN: D("150")}, {JAN: D("-150")}, {VISA: {JAN: D("150")}})
        assert cf.funded_by_card == {VISA: {JAN: D("150")}}
        assert cf.floored_by_category == {}

    def test_the_overspent_swipe_scenario(self):
        # Assigned 100, spent 150 on the card: 100 funds, 50 rides.
        cf = funding({JAN: D("100")}, {JAN: D("-150")}, {VISA: {JAN: D("150")}})
        assert cf.funded_by_card == {VISA: {JAN: D("100")}}
        assert cf.floored_by_category == {"groceries": {JAN: D("50")}}

    def test_the_wholly_unfunded_swipe_funds_nothing(self):
        # Nothing assigned: the whole 150 rides as uncovered debt.
        cf = funding({}, {JAN: D("-150")}, {VISA: {JAN: D("150")}})
        assert cf.funded_by_card == {}
        assert cf.floored_by_category == {"groceries": {JAN: D("150")}}

    def test_two_categories_fund_one_card(self):
        cf = card_funding(
            {"groceries": {JAN: D("100")}, "fuel": {JAN: D("40")}},
            {"groceries": {JAN: D("-100")}, "fuel": {JAN: D("-40")}},
            {"groceries": {VISA: {JAN: D("100")}}, "fuel": {VISA: {JAN: D("40")}}},
            {},
        )
        assert cf.funded_by_card == {VISA: {JAN: D("140")}}
        assert cf.floored_by_category == {}

    def test_one_category_overspent_across_two_cards(self):
        # Overspent 60, spent 40 on amex and 100 on visa: the ride is placed
        # greedily (amex holds 40, visa the remaining 20) and each card's
        # envelope receives only what was actually covered on it.
        cf = funding(
            {JAN: D("80")}, {JAN: D("-140")}, {VISA: {JAN: D("100")}, AMEX: {JAN: D("40")}}
        )
        assert cf.floored_by_category == {"groceries": {JAN: D("60")}}
        assert cf.funded_by_card == {VISA: {JAN: D("80")}}

    def test_a_category_with_no_card_spending_contributes_nothing(self):
        cf = card_funding({"rent": {JAN: D("1200")}}, {"rent": {JAN: D("-1200")}}, {}, {})
        assert cf.funded_by_card == {} and cf.floored_by_category == {}
        # And no series either — a category with no card activity keeps the one
        # the ordinary simulation already gave it.
        assert cf.end_balances == {}

    def test_a_cross_month_refund_releases_its_reservation(self):
        # The Unreleased Reservation, minimal: January's funded purchase
        # reserves 100; February's refund of it releases the 100. The card's
        # balance returned to zero and now so does its envelope.
        cf = funding(
            {JAN: D("100")},
            {JAN: D("-100"), FEB: D("100")},
            {VISA: {JAN: D("100"), FEB: D("-100")}},
        )
        assert cf.funded_by_card == {VISA: {JAN: D("100"), FEB: D("-100")}}
        assert cf.floored_by_category == {}
        # Nothing rode, so nothing was discharged: the refund is the envelope's.
        assert cf.repaid_by_category == {}
        assert cf.end_balances == {"groceries": {JAN: D("0"), FEB: D("100")}}

    def test_a_partly_ridden_purchase_refunded_returns_only_the_funded_part(self):
        # 100 spent with 60 assigned: 60 reserved, 40 rides as uncovered. A full
        # refund next month discharges the 40 and releases the 60 — so the
        # envelope gets back exactly what it put in, not the whole 100.
        cf = funding(
            {JAN: D("60")},
            {JAN: D("-100"), FEB: D("100")},
            {VISA: {JAN: D("100"), FEB: D("-100")}},
        )
        assert cf.funded_by_card == {VISA: {JAN: D("60"), FEB: D("-60")}}
        assert cf.floored_by_category == {"groceries": {JAN: D("40")}}
        assert cf.repaid_by_category == {"groceries": {FEB: D("40")}}
        assert cf.end_balances == {"groceries": {JAN: D("-40"), FEB: D("60")}}

    def test_a_release_stays_on_the_card_that_reserved(self):
        # Groceries reserved on both cards in January; February's refund on
        # visa releases only visa's reservation — amex keeps its own.
        cf = funding(
            {JAN: D("140")},
            {JAN: D("-140"), FEB: D("100")},
            {VISA: {JAN: D("100"), FEB: D("-100")}, AMEX: {JAN: D("40")}},
        )
        assert cf.funded_by_card == {VISA: {JAN: D("100"), FEB: D("-100")}, AMEX: {JAN: D("40")}}
        assert cf.floored_by_category == {}

    def test_a_refund_posting_before_its_purchase_is_absorbed_when_it_lands(self):
        # Replaces `test_a_pre_reservation_inflow_is_discarded`, which asserted
        # the defect: the refund was written off forever and the envelope stayed
        # 100 short. The reserve now goes negative and February's purchase
        # absorbs it, with no memory of a refusal to redeem.
        cf = funding(
            {FEB: D("100")},
            {JAN: D("100"), FEB: D("-100")},
            {VISA: {JAN: D("-100"), FEB: D("100")}},
        )
        assert cf.funded_by_card == {VISA: {JAN: D("-100"), FEB: D("100")}}
        assert cf.residual_by_card == {VISA: {JAN: D("100")}}
        assert cf.floored_by_category == {}
        # Set-aside back to zero against a zero balance. Before: 100 reserved
        # against a card that owed nothing.
        assert reserve_of(cf, VISA).set_aside(FEB) == D("0")

    def test_a_repayment_beyond_lifetime_exposure_becomes_a_negative_reserve(self):
        # The second cardholder / reimbursement case: the category spent its
        # money in cash, and 50 arrives on the card filed to it. Nothing was
        # ever riding there, so the whole 50 is a residual.
        cf = funding({JAN: D("100")}, {JAN: D("-100"), FEB: D("50")}, {VISA: {FEB: D("-50")}})
        assert cf.residual_by_card == {VISA: {FEB: D("50")}}
        assert cf.repaid_by_category == {}
        # The envelope keeps it — no cash arrived, but the card is now holding
        # 50 of this envelope's money, which the negative reserve says.
        assert cf.end_balances == {"groceries": {JAN: D("0"), FEB: D("50")}}
        assert reserve_of(cf, VISA).set_aside(FEB) == D("-50")

    def test_a_release_on_one_card_never_touches_another_cards_reserve(self):
        # Spent on both, refund lands on amex only. Visa's reserve must not move
        # — its balance did not.
        cf = funding(
            {JAN: D("140")},
            {JAN: D("-140"), FEB: D("100")},
            {VISA: {JAN: D("100")}, AMEX: {JAN: D("40"), FEB: D("-100")}},
        )
        assert reserve_of(cf, VISA).set_aside(FEB) == D("100")
        assert reserve_of(cf, AMEX).set_aside(FEB) == D("-60")
        assert cf.residual_by_card == {AMEX: {FEB: D("60")}}

    def test_a_month_that_charges_one_card_and_refunds_another_is_split(self):
        # The acyclicity claim, made concrete: the amex inflow is settled from
        # exposure carried in, before the month's end balance decides what rides
        # on visa. Neither reads the other.
        cf = funding({}, {JAN: D("-30")}, {VISA: {JAN: D("50")}, AMEX: {JAN: D("-20")}})
        assert cf.floored_by_category == {"groceries": {JAN: D("30")}}
        assert cf.floored_by_card == {VISA: {JAN: D("30")}}
        assert cf.residual_by_card == {AMEX: {JAN: D("20")}}

    def test_the_repaid_adjustment_never_exceeds_the_inflow_that_caused_it(self):
        # The bound that makes a correction incapable of creating red: at worst
        # it returns the month to what it would have been with no refund at all.
        cf = funding(
            {},
            {JAN: D("-100"), FEB: D("30")},
            {VISA: {JAN: D("100"), FEB: D("-30")}},
        )
        assert cf.repaid_by_category == {"groceries": {FEB: D("30")}}
        assert cf.end_balances["groceries"][FEB] == D("0")

    def test_nothing_is_ever_refused(self):
        # The property the whole rewrite exists for: every cent of every inflow
        # is discharged, released, or carried as a residual.
        cf = funding(
            {JAN: D("60"), MAR: D("10")},
            {JAN: D("-100"), FEB: D("140"), MAR: D("-20")},
            {VISA: {JAN: D("100"), FEB: D("-140"), MAR: D("20")}},
        )
        inflows = D("140")
        discharged = sum(cf.repaid_by_category.get("groceries", {}).values(), D("0"))
        residual = sum(cf.residual_by_card.get(VISA, {}).values(), D("0"))
        released = -sum(v for v in cf.funded_by_card[VISA].values() if v < 0) - residual
        assert discharged + released + residual == inflows


class TestTheAdjustedSeries:
    """`end_balances` — the slot that replaced `truncated`, and the one the old
    tuple never had. Its predecessor shipped with no coverage at all because
    every caller unpacked it as `_`."""

    def test_the_end_balances_slot_is_what_available_reads(self):
        # With nothing discharged it is the ordinary simulation, to the cent.
        assignments, activity = {JAN: D("150")}, {JAN: D("-150"), FEB: D("-20")}
        cf = funding(assignments, activity, {VISA: {JAN: D("150")}})
        assert cf.end_balances["groceries"] == monthly_end_balances(assignments, activity)

    def test_the_end_balances_slot_floors_a_repaid_month_at_the_boundary(self):
        # The ratchet, at unit level. January rides 100, February repays it,
        # March overspends 100 in cash. The correction belongs to February and
        # must not survive into March, let alone every month after it.
        cf = funding(
            {},
            {JAN: D("-100"), FEB: D("100"), MAR: D("-100")},
            {VISA: {JAN: D("100"), FEB: D("-100")}},
        )
        series = cf.end_balances["groceries"]
        assert series == {JAN: D("-100"), FEB: D("0"), MAR: D("-100")}
        # And April, which has no data of its own, reads zero — not the
        # cumulative refusal the old code subtracted forever.
        assert available_at(series, APR) == D("0")

    def test_the_residual_slot_is_reported_per_card_per_month(self):
        cf = funding(
            {},
            {JAN: D("40"), FEB: D("60")},
            {VISA: {JAN: D("-40")}, AMEX: {FEB: D("-60")}},
        )
        assert cf.residual_by_card == {VISA: {JAN: D("40")}, AMEX: {FEB: D("60")}}


class TestTheReserveIsFiveLegs:
    def test_sums_every_leg_through_the_month(self):
        reserve = CardReserve(
            assignments={JAN: D("50")},
            reservations={JAN: D("100"), FEB: D("20")},
            released={FEB: D("30")},
            residual={FEB: D("5")},
            payments={FEB: D("15")},
        )
        assert reserve.set_aside(JAN) == D("150")
        assert reserve.set_aside(FEB) == D("120")

    def test_months_after_the_viewed_one_are_out(self):
        reserve = CardReserve(assignments={FEB: D("50")}, reservations={JAN: D("100")})
        assert reserve.set_aside(JAN) == D("100")

    def test_an_overpaid_month_carries_its_negative_forward(self):
        # Defect B's pin: paying 100 against a 60 reserve is a 40 credit
        # balance on the card, carried — not floored away at the boundary,
        # which ratcheted the set-aside upward by every overpaid month.
        reserve = CardReserve(reservations={JAN: D("60")}, payments={JAN: D("100")})
        assert reserve.set_aside(FEB) == D("-40")
        assert reserve.set_aside(JAN) == D("-40")

    def test_payments_subtract_from_the_months_they_fall_in(self):
        reserve = CardReserve(reservations={JAN: D("100")}, payments={JAN: D("60"), FEB: D("40")})
        assert reserve.set_aside(JAN) == D("40")
        assert reserve.set_aside(FEB) == D("0")

    def test_the_legs_come_out_of_the_walk_without_being_re_summed(self):
        cf = funding({JAN: D("100")}, {JAN: D("-150")}, {VISA: {JAN: D("150")}})
        reserve = card_reserve(cf, VISA, {FEB: D("40")})
        assert reserve.reservations == {JAN: D("100")}
        assert reserve.payments == {FEB: D("40")}
        assert reserve.set_aside(FEB) == D("60")


def discrepancy(
    set_aside, balance, assigned="0", covered="0", payments="0", residual="0", unclaimed="0"
):
    """`reserve_discrepancy` with the terms named, so a seven-argument call
    says which bound it is exercising."""
    return reserve_discrepancy(
        D(set_aside), D(balance), D(assigned), D(covered), D(payments), D(residual), D(unclaimed)
    )


class TestReserveDiscrepancy:
    """The honest invariant's three bounds. The equation itself is an algebraic
    identity, so it catches nothing; these are what the old form's "for a card
    with no assignments and no inflows that predate their reservations" was
    quietly excusing."""

    def test_a_healthy_card_reports_nothing(self):
        # 60 reserved against 100 owed: 40 uncovered, everything in bounds.
        assert discrepancy("60", "-100") == D("0")

    def test_a_reserve_that_outlived_its_debt_is_named(self):
        # The pre-fix numbers from the refund-before-purchase case: 100 reserved
        # against a card that owes nothing, with no assignment behind it.
        assert discrepancy("100", "0") == D("100")

    def test_a_reserve_raised_by_assignment_is_allowed(self):
        # T1: the same shape, but someone deliberately put the money there.
        assert discrepancy("100", "0", assigned="100") == D("0")

    def test_a_negative_reserve_needs_a_payment_or_a_residual(self):
        # T2. An overpayment explains it; nothing does not.
        assert discrepancy("-50", "50", residual="50") == D("0")
        assert discrepancy("-50", "50") == D("50")

    def test_a_reserve_moved_back_out_is_not_a_violation(self):
        """The Watchman's Arithmetic, finding one. `assigned` is a signed
        lifetime total: moving more money back out of a card's payment envelope
        than was ever put in makes it negative, and an unfloored `L - R` then
        reported that shortfall as drift on a card with nothing over-reserved.
        A four-figure false alarm on a real budget, louder than the one genuine
        finding on the same page."""
        # Nothing over-reserved (0 against 100 owed), so T1 has nothing to
        # account for — yet it reported 100 before the floor.
        assert discrepancy("0", "-100", assigned="-100") == D("0")

    def test_a_negative_assignment_does_not_cancel_a_real_credit(self):
        """Why the floor is per-term and not on the sum. 50 over-reserved with
        a 50 outside credit behind it is explained; a lifetime assignment total
        of -100 must contribute no capacity, not negative capacity that eats
        the credit's. Flooring `assigned + unclaimed_rows` together reports
        50 here — a fresh false positive in place of the old one."""
        assert discrepancy("50", "0", assigned="-100", unclaimed="50") == D("0")
        # And the floor may not weaken a genuine catch: same shape, no credit.
        assert discrepancy("50", "0", assigned="-100") == D("50")

    def test_a_card_credit_is_always_someones(self):
        # T3, and the case the pre-fix code got wrong: a 50 credit sat on the
        # card with the reserve at zero — belonging to nobody.
        assert discrepancy("0", "50") == D("50")
        # A partner's payment explains it.
        assert discrepancy("0", "50", unclaimed="50") == D("0")


class TestReservationInvariant:
    """The reserve identity at every month, over generated histories, with **no
    exclusions** — direct assignments, plain third-party deposits and inflows
    that predate their reservations all included.

    Three defects were drift between the accumulated series (set_aside) and the
    directly-computed truth (the card's balance): the per-month clamp leaked on
    every cross-month refund, the boundary floor on every overpaid month, and
    the release cap on every repayment of ridden debt. The first two were caught
    here; the third was not, because the docstring excused exactly the histories
    that produce it. This walk no longer excuses anything.
    """

    def _check(self, assignments, events, card_assignments=None):
        """events: (month, kind, category, amount[, card]) with kind in
        {"spend", "refund", "pay", "deposit"}; amounts positive. Walks month by
        month asserting the identity after every month."""
        events = [e if len(e) == 5 else (*e, VISA) for e in events]
        months = sorted({m for m, *_ in events})
        categories = sorted({c for _, _, c, _, _ in events if c is not None})
        card_assignments = card_assignments or {}
        for upto in months:
            in_scope = [e for e in events if e[0] <= upto]
            activity: dict[str, dict[date, Decimal]] = {c: {} for c in categories}
            outflows: dict[str, dict[str, dict[date, Decimal]]] = {}
            payments: dict[str, dict[date, Decimal]] = {}
            deposits: dict[str, Decimal] = {}
            balances: dict[str, Decimal] = {}
            for m, kind, cat, amount, card in in_scope:
                balances.setdefault(card, D("0"))
                if kind in ("spend", "refund"):
                    sign = D("-1") if kind == "spend" else D("1")
                    balances[card] += sign * amount
                    activity[cat][m] = activity[cat].get(m, D("0")) + sign * amount
                    per = outflows.setdefault(cat, {}).setdefault(card, {})
                    per[m] = per.get(m, D("0")) - sign * amount
                elif kind == "pay":
                    balances[card] += amount
                    payments.setdefault(card, {})[m] = (
                        payments.setdefault(card, {}).get(m, D("0")) + amount
                    )
                elif kind == "deposit":
                    # A third party paying the card: touches no envelope.
                    balances[card] += amount
                    deposits[card] = deposits.get(card, D("0")) + amount
            outflows = {
                c: {
                    card: {m: v for m, v in series.items() if v != 0}
                    for card, series in by_card.items()
                }
                for c, by_card in outflows.items()
            }
            # Card assignments go through the walk, which is the whole point:
            # they retire riding debt before they reserve.
            card_categories = {card: f"card-{card}" for card in card_assignments}
            cf = card_funding(
                assignments | {f"card-{c}": a for c, a in card_assignments.items()},
                activity,
                outflows,
                card_categories,
            )
            for card, balance in balances.items():
                reserve = card_reserve(cf, card, payments.get(card, {}))
                set_aside = reserve.set_aside(upto)
                discrepancy = reserve_discrepancy(
                    set_aside,
                    balance,
                    sum((v for m, v in reserve.assignments.items() if m <= upto), D("0")),
                    sum(
                        (v for m, v in cf.covered_by_card.get(card, {}).items() if m <= upto),
                        D("0"),
                    ),
                    sum((v for m, v in payments.get(card, {}).items() if m <= upto), D("0")),
                    sum(
                        (v for m, v in cf.residual_by_card.get(card, {}).items() if m <= upto),
                        D("0"),
                    ),
                    deposits.get(card, D("0")),
                )
                assert discrepancy == D("0"), (
                    f"through {upto} on {card}: set_aside={set_aside} "
                    f"balance={balance} discrepancy={discrepancy}"
                )

    def test_the_minimal_reproduction(self):
        # January: funded purchase. February: its refund. Balance returns to
        # zero; before the first fix the envelope kept the 100 forever.
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
        # envelope reads -50 — the identity still balances to the cent.
        self._check(
            {"g": {JAN: D("100")}},
            [(JAN, "spend", "g", D("100")), (FEB, "pay", None, D("150"))],
        )

    def test_the_refused_repayment(self):
        # The case the old docstring excused: nothing assigned, so the whole
        # charge rides; next month's repayment of it was refused, and both the
        # envelope and the card were left wrong by the same amount.
        self._check(
            {},
            [(JAN, "spend", "g", D("100")), (FEB, "refund", "g", D("100"))],
        )

    def test_assignments_to_the_card_show_up_as_over_reserve_and_nothing_else(self):
        # T1, over a walk: money deliberately put on the card ahead of the debt.
        self._check(
            {"g": {JAN: D("100")}},
            [(JAN, "spend", "g", D("100")), (FEB, "pay", None, D("100"))],
            card_assignments={VISA: {JAN: D("250")}},
        )

    def test_an_inflow_before_any_reservation_shows_up_as_short_reserve(self):
        # T2: the refund-before-purchase shape, walked month by month.
        self._check(
            {"g": {FEB: D("100")}},
            [(JAN, "refund", "g", D("100")), (FEB, "spend", "g", D("100"))],
        )

    def test_a_card_credit_is_always_someones(self):
        # T3: a partner pays the card outright. It touches no envelope, and the
        # credit balance it leaves is theirs, not a drifted reserve.
        self._check(
            {"g": {JAN: D("100")}},
            [(JAN, "spend", "g", D("100")), (FEB, "deposit", None, D("400"))],
        )

    def test_the_ordinary_texture_of_a_real_ledger(self):
        # Multi-month, multi-category, multi-card: partial refunds in later
        # months, payments out of step with spending, overspending riding along,
        # a refund landing on the card that did not carry the purchase, and a
        # refund arriving before the purchase it offsets.
        self._check(
            {"g": {JAN: D("200"), FEB: D("200"), MAR: D("200")}, "f": {JAN: D("50")}},
            [
                (JAN, "spend", "g", D("180"), VISA),
                (JAN, "spend", "f", D("80"), VISA),  # 30 rides as uncovered
                (JAN, "refund", "g", D("25"), AMEX),  # before anything on amex
                (FEB, "refund", "g", D("40"), VISA),
                (FEB, "spend", "g", D("220"), VISA),
                (FEB, "pay", None, D("150"), VISA),
                (FEB, "spend", "g", D("60"), AMEX),
                (MAR, "refund", "f", D("60"), VISA),  # releases 50, 10 pays debt
                (MAR, "spend", "g", D("90"), VISA),
                (MAR, "pay", None, D("300"), VISA),
                (MAR, "deposit", None, D("15"), AMEX),
            ],
        )


class TestTheRiddenAmountIsAttributedToTheCardThatCarriedIt:
    """`floored_by_card` — the same red as `floored_by_category`, split by card.

    Two cards are paid separately, so "which one is this riding on" is a real
    question. The split is exact rather than apportioned, and that is what
    makes it safe to show: `month_floored` is capped at the month's *net*
    outflow, while the allocation pool is the cards that netted to spending —
    which sums to at least the net. So the greedy walk always exhausts the
    amount and the per-card figures sum to the per-category one.
    """

    def test_one_card_carries_the_whole_ride(self) -> None:
        cf = funding({JAN: D("20")}, {JAN: D("-70")}, {VISA: {JAN: D("70")}})

        assert cf.floored_by_category == {"groceries": {JAN: D("50")}}
        assert cf.floored_by_card == {VISA: {JAN: D("50")}}

    def test_two_cards_split_it_and_the_parts_sum_to_the_whole(self) -> None:
        cf = funding({JAN: D("10")}, {JAN: D("-100")}, {VISA: {JAN: D("60")}, AMEX: {JAN: D("40")}})

        assert cf.floored_by_category == {"groceries": {JAN: D("90")}}
        assert sum(v[JAN] for v in cf.floored_by_card.values()) == D("90")
        # Each card carries at most what was actually swiped on it.
        assert cf.floored_by_card[AMEX][JAN] <= D("40")
        assert cf.floored_by_card[VISA][JAN] <= D("60")

    def test_a_card_that_netted_to_a_refund_carries_nothing(self) -> None:
        """The pool is the cards with positive net that month. A card whose
        month nets to an inflow reduced its own debt; it cannot also be
        carrying someone else's overspending."""
        cf = funding({}, {JAN: D("-30")}, {VISA: {JAN: D("50")}, AMEX: {JAN: D("-20")}})

        assert cf.floored_by_category == {"groceries": {JAN: D("30")}}
        assert cf.floored_by_card == {VISA: {JAN: D("30")}}

    def test_a_month_with_nothing_ridden_names_no_card(self) -> None:
        cf = funding({JAN: D("70")}, {JAN: D("-50")}, {VISA: {JAN: D("50")}})

        assert cf.floored_by_category == {}
        assert cf.floored_by_card == {}


class TestAnAssignmentRetiresRidingDebt:
    """ "Two Ledgers, One Debt": an assignment to a card's payment category is
    the other way money meets uncovered debt, and until 2026-08-30 it did not
    go through the door that handles the first way.

    `release_split` sends an *inflow* through the ride first. An assignment
    went straight into the reserve, so nothing ever retired it: on a card
    always paid in full the reserve converged on what the card owed **plus
    every dollar ever assigned to it**, for the life of the budget.
    """

    def visa(self, spending, card_assignments, activity=None, outflows=None):
        """A walk with one spending category and one card whose payment
        category is `card-visa`."""
        return card_funding(
            {"groceries": spending, "card-visa": card_assignments},
            {"groceries": activity or {}},
            {"groceries": outflows or {}},
            {VISA: "card-visa"},
        )

    def test_an_assignment_retires_the_ride_and_still_reserves_in_full(self):
        # Jan: 100 spent on the card with nothing assigned — 100 rides.
        # Feb: 100 assigned to the card's envelope.
        cf = self.visa(
            {}, {FEB: D("100")}, activity={JAN: D("-100")}, outflows={VISA: {JAN: D("100")}}
        )
        assert cf.covered_by_card == {VISA: {FEB: D("100")}}
        assert cf.covered_by_category == {"groceries": {FEB: D("100")}}
        # A conversion, not a diversion: the whole assignment still reserves.
        # Reserving only the remainder would make the assignment a visible
        # no-op and stop Ready to Assign falling by money just committed.
        assert card_reserve(cf, VISA, {}).set_aside(FEB) == D("100")

    def test_a_refund_after_a_covering_assignment_releases_instead_of_discharging(self):
        """The headline. With the ride retired, March's refund hands the money
        back to the envelope instead of vanishing into a discharge."""
        cf = self.visa(
            {},
            {FEB: D("100")},
            activity={JAN: D("-100"), MAR: D("100")},
            outflows={VISA: {JAN: D("100"), MAR: D("-100")}},
        )
        assert cf.repaid_by_category == {}, "the debt was already covered by cash"
        assert cf.residual_by_card == {VISA: {MAR: D("100")}}
        # Reserve back to zero, and the envelope is 100 up.
        assert card_reserve(cf, VISA, {}).set_aside(MAR) == D("0")
        assert cf.end_balances["groceries"][MAR] == D("100")

    def test_a_refund_with_no_covering_assignment_still_discharges(self):
        """The control: unchanged where no assignment exists."""
        cf = self.visa(
            {},
            {},
            activity={JAN: D("-100"), MAR: D("100")},
            outflows={VISA: {JAN: D("100"), MAR: D("-100")}},
        )
        assert cf.repaid_by_category == {"groceries": {MAR: D("100")}}
        assert cf.end_balances["groceries"][MAR] == D("0")

    def test_an_assignment_covers_this_months_own_ride_without_erasing_the_red(self):
        """Step 5 runs after the charges, because the user assigns against the
        Uncovered figure on the page in front of them.

        `floored_by_category` is NOT retracted: it is the historical record the
        month's own visible red is paired with, and `uncovered_current`
        subtracts it from Ready to Assign. Retracting it would charge Ready to
        Assign twice for one shortfall."""
        cf = self.visa(
            {}, {JAN: D("100")}, activity={JAN: D("-100")}, outflows={VISA: {JAN: D("100")}}
        )
        assert cf.covered_by_card == {VISA: {JAN: D("100")}}
        assert cf.floored_by_category == {"groceries": {JAN: D("100")}}

    def test_a_refund_beats_an_assignment_to_the_ride_within_one_month(self):
        """Named rather than silent: inflows settle before assignments, because
        an inflow must settle before the month's end balance is taken. The
        goods came back, so the assignment is surplus reserve the user can see
        and move."""
        cf = self.visa(
            {},
            {FEB: D("100")},
            activity={JAN: D("-100"), FEB: D("100")},
            outflows={VISA: {JAN: D("100"), FEB: D("-100")}},
        )
        assert cf.repaid_by_category == {"groceries": {FEB: D("100")}}
        assert cf.covered_by_card == {}
        assert card_reserve(cf, VISA, {}).set_aside(FEB) == D("100")

    def test_an_assignment_beyond_the_ride_covers_only_the_ride(self):
        cf = self.visa(
            {}, {FEB: D("200")}, activity={JAN: D("-50")}, outflows={VISA: {JAN: D("50")}}
        )
        assert cf.covered_by_card == {VISA: {FEB: D("50")}}
        assert card_reserve(cf, VISA, {}).set_aside(FEB) == D("200")

    def test_an_assignment_only_retires_debt_on_its_own_card(self):
        """The per-card scoping the module docstring refuses to pool."""
        cf = card_funding(
            {"groceries": {}, "card-visa": {FEB: D("500")}},
            {"groceries": {JAN: D("-150")}},
            {"groceries": {VISA: {JAN: D("100")}, AMEX: {JAN: D("50")}}},
            {VISA: "card-visa"},
        )
        assert cf.covered_by_card == {VISA: {FEB: D("100")}}
        assert sum_through(cf.riding_by_card[AMEX], FEB) == D("50")

    def test_a_negative_assignment_does_not_re_ride_debt(self):
        """Moving money back out has no non-arbitrary category to charge, and
        the spending it funded was funded. The reserve simply falls."""
        cf = self.visa(
            {JAN: D("100")},
            {FEB: D("-40")},
            activity={JAN: D("-100")},
            outflows={VISA: {JAN: D("100")}},
        )
        assert cf.covered_by_card == {}
        assert cf.floored_by_category == {}
        assert card_reserve(cf, VISA, {}).set_aside(FEB) == D("60")

    def test_a_partial_cover_is_split_across_categories_in_sorted_order(self):
        """`allocate_capped`, the same allocator that places a ride across
        cards — greedy in sorted-key order, exact, no proportional rounding."""
        cf = card_funding(
            {"card-visa": {FEB: D("70")}},
            {"apples": {JAN: D("-50")}, "bananas": {JAN: D("-60")}},
            {"apples": {VISA: {JAN: D("50")}}, "bananas": {VISA: {JAN: D("60")}}},
            {VISA: "card-visa"},
        )
        assert cf.covered_by_category == {"apples": {FEB: D("50")}, "bananas": {FEB: D("20")}}

    def test_an_assignment_cannot_reach_a_ride_from_a_later_month(self):
        """Month-major and forward-only: at month m, `ridden` holds only rides
        from months <= m."""
        cf = self.visa(
            {}, {JAN: D("100")}, activity={FEB: D("-100")}, outflows={VISA: {FEB: D("100")}}
        )
        assert cf.covered_by_card == {}
        assert sum_through(cf.riding_by_card[VISA], FEB) == D("100")

    def test_a_card_assignment_in_a_month_no_category_touches_is_still_walked(self):
        """The union-of-months loop. A per-category walk never visits March at
        all, so the assignment would never have been seen."""
        cf = self.visa(
            {}, {MAR: D("100")}, activity={JAN: D("-100")}, outflows={VISA: {JAN: D("100")}}
        )
        assert cf.covered_by_card == {VISA: {MAR: D("100")}}
        assert cf.assignments_by_card == {VISA: {MAR: D("100")}}

    def test_the_walk_is_unchanged_when_no_card_category_is_assigned(self):
        """The regression fence: with `card_categories` empty, every figure is
        what it was before step 5 existed."""
        args = (
            {"groceries": {JAN: D("100")}},
            {"groceries": {JAN: D("-150"), FEB: D("50")}},
            {"groceries": {VISA: {JAN: D("150"), FEB: D("-50")}}},
        )
        assert card_funding(*args, {}) == card_funding(*args, {})
        cf = card_funding(*args, {})
        assert cf.floored_by_category == {"groceries": {JAN: D("50")}}
        assert cf.repaid_by_category == {"groceries": {FEB: D("50")}}
        assert cf.covered_by_card == {} and cf.assignments_by_card == {}


class TestTheClosedForm:
    """`set_aside - owed == (assignments - covered) + unclaimed - riding`.

    Exact on every card of a real imported budget, which is what made it a
    precise statement of the defect: with `covered` always zero, the first term
    was the entire lifetime of assignments and the reserve could never
    converge on what the card owed.
    """

    def check(self, cf, card, payments, spends, unclaimed=D("0")):
        reserve = card_reserve(cf, card, payments)
        upto = APR
        set_aside = reserve.set_aside(upto)
        owed = spends - sum(payments.values(), D("0")) - unclaimed
        assignments = sum_through(reserve.assignments, upto)
        covered = sum_through(cf.covered_by_card.get(card, {}), upto)
        riding = sum_through(cf.riding_by_card.get(card, {}), upto)
        assert set_aside - owed == assignments - covered + unclaimed - riding, (
            f"set_aside={set_aside} owed={owed} assignments={assignments} "
            f"covered={covered} riding={riding}"
        )

    def test_holds_on_a_card_paid_in_full_with_an_assignment_parked_on_it(self):
        # The defect's own scenario: charge, pay, assign, repeat.
        cf = card_funding(
            {"groceries": {JAN: D("100"), MAR: D("100")}, "card-visa": {FEB: D("250")}},
            {"groceries": {JAN: D("-100"), MAR: D("-100")}},
            {"groceries": {VISA: {JAN: D("100"), MAR: D("100")}}},
            {VISA: "card-visa"},
        )
        self.check(cf, VISA, {FEB: D("100"), APR: D("100")}, spends=D("200"))

    def test_holds_when_an_assignment_covers_a_ride(self):
        cf = card_funding(
            {"card-visa": {FEB: D("100")}},
            {"groceries": {JAN: D("-100")}},
            {"groceries": {VISA: {JAN: D("100")}}},
            {VISA: "card-visa"},
        )
        self.check(cf, VISA, {}, spends=D("100"))

    def test_holds_when_money_is_moved_back_out_of_the_envelope(self):
        cf = card_funding(
            {"groceries": {JAN: D("100")}, "card-visa": {FEB: D("-40")}},
            {"groceries": {JAN: D("-100")}},
            {"groceries": {VISA: {JAN: D("100")}}},
            {VISA: "card-visa"},
        )
        self.check(cf, VISA, {}, spends=D("100"))


class TestT1NoLongerExcusesTheDriftItCaused:
    def test_an_assignment_that_already_did_its_job_stops_explaining_a_reserve(self):
        """The defect's signature. 100 reserved against a card owing nothing,
        with a 100 assignment behind it that has already retired a ride —
        spent, so it explains the debt it covered, not the reserve left over."""
        assert discrepancy("100", "0", assigned="100", covered="100") == D("100")

    def test_an_assignment_still_parked_does_explain_it(self):
        """A card someone is deliberately pre-funding is a legitimate state,
        which is why the bound is not simply clamped by what is owed."""
        assert discrepancy("100", "0", assigned="100") == D("0")

    def test_a_cover_larger_than_the_assignment_cannot_manufacture_capacity(self):
        """`assigned - covered` is ONE term inside `_allowance`, so it floors
        at zero on its own rather than going negative and eating another
        term's capacity."""
        assert discrepancy("50", "0", covered="100", unclaimed="50") == D("0")

    def test_an_unclaimed_charge_is_counted_in_the_sign_it_arrived_in(self):
        """The predicate carried `amount > 0` until 2026-08-30, so T1's left
        side moved by the NET of unclaimed rows while its allowance moved by
        the POSITIVE half — and on a real card the bound cleared by a margin
        equal, to the cent, to the rows it could not see."""
        # A net-negative unclaimed total (an unfiled charge) buys no capacity.
        assert discrepancy("100", "0", unclaimed="-30") == D("100")
