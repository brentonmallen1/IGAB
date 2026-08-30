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

from datetime import date
from decimal import Decimal

from igab.domain.cards import (
    allocate_across_cards,
    card_funding,
    credit_floored_by_month,
    release_split,
    reserve_discrepancy,
    set_aside_through,
    synthetic_activity,
)
from igab.domain.carryover import available_at, monthly_end_balances

JAN, FEB, MAR, APR = (date(2026, m, 1) for m in (1, 2, 3, 4))
D = Decimal
AMEX, VISA = "amex-partner", "visa"  # sorted: amex first — allocation order


def funding(assignments, activity, outflows, category="groceries"):
    """`card_funding` for one category, spelled the way the scenarios read."""
    return card_funding({category: assignments}, {category: activity}, {category: outflows})


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
        cf = card_funding({"rent": {JAN: D("1200")}}, {"rent": {JAN: D("-1200")}}, {})
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
        assert set_aside_through({}, cf.funded_by_card[VISA], FEB) == D("0")

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
        assert set_aside_through({}, cf.funded_by_card[VISA], FEB) == D("-50")

    def test_a_release_on_one_card_never_touches_another_cards_reserve(self):
        # Spent on both, refund lands on amex only. Visa's reserve must not move
        # — its balance did not.
        cf = funding(
            {JAN: D("140")},
            {JAN: D("-140"), FEB: D("100")},
            {VISA: {JAN: D("100")}, AMEX: {JAN: D("40"), FEB: D("-100")}},
        )
        assert set_aside_through({}, cf.funded_by_card[VISA], FEB) == D("100")
        assert set_aside_through({}, cf.funded_by_card[AMEX], FEB) == D("-60")
        assert cf.residual_by_card == {AMEX: {FEB: D("60")}}

    def test_a_month_that_charges_one_card_and_refunds_another_is_split(self):
        # The acyclicity claim, made concrete: the amex inflow is settled from
        # exposure carried in, before the month's end balance decides what rides
        # on visa. Neither reads the other.
        cf = funding(
            {}, {JAN: D("-30")}, {VISA: {JAN: D("50")}, AMEX: {JAN: D("-20")}}
        )
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


class TestReserveDiscrepancy:
    """The honest invariant's three bounds. The equation itself is an algebraic
    identity, so it catches nothing; these are what the old form's "for a card
    with no assignments and no inflows that predate their reservations" was
    quietly excusing."""

    def test_a_healthy_card_reports_nothing(self):
        # 60 reserved against 100 owed: 40 uncovered, everything in bounds.
        assert reserve_discrepancy(D("60"), D("-100"), D("0"), D("0"), D("0"), D("0")) == D("0")

    def test_a_reserve_that_outlived_its_debt_is_named(self):
        # The pre-fix numbers from the refund-before-purchase case: 100 reserved
        # against a card that owes nothing, with no assignment behind it.
        assert reserve_discrepancy(D("100"), D("0"), D("0"), D("0"), D("0"), D("0")) == D("100")

    def test_a_reserve_raised_by_assignment_is_allowed(self):
        # T1: the same shape, but someone deliberately put the money there.
        assert reserve_discrepancy(D("100"), D("0"), D("100"), D("0"), D("0"), D("0")) == D("0")

    def test_a_negative_reserve_needs_a_payment_or_a_residual(self):
        # T2. An overpayment explains it; nothing does not.
        assert reserve_discrepancy(D("-50"), D("50"), D("0"), D("0"), D("50"), D("0")) == D("0")
        assert reserve_discrepancy(D("-50"), D("50"), D("0"), D("0"), D("0"), D("0")) == D("50")

    def test_a_card_credit_is_always_someones(self):
        # T3, and the case the pre-fix code got wrong: a 50 credit sat on the
        # card with the reserve at zero — belonging to nobody.
        assert reserve_discrepancy(D("0"), D("50"), D("0"), D("0"), D("0"), D("0")) == D("50")
        # A partner's payment explains it.
        assert reserve_discrepancy(D("0"), D("50"), D("0"), D("0"), D("0"), D("50")) == D("0")


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
            cf = card_funding(assignments, activity, outflows)
            for card, balance in balances.items():
                synthetic = synthetic_activity(
                    cf.funded_by_card.get(card, {}), payments.get(card, {})
                )
                assigned_here = card_assignments.get(card, {})
                set_aside = set_aside_through(assigned_here, synthetic, upto)
                discrepancy = reserve_discrepancy(
                    set_aside,
                    balance,
                    sum((v for m, v in assigned_here.items() if m <= upto), D("0")),
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
        cf = funding(
            {JAN: D("10")}, {JAN: D("-100")}, {VISA: {JAN: D("60")}, AMEX: {JAN: D("40")}}
        )

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
