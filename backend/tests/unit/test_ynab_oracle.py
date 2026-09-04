"""integrations.ynab.oracle — YNAB's rules, one case each."""

from datetime import date
from decimal import Decimal

from igab.domain.dates import add_months
from igab.integrations.ynab.models import (
    YNABBudget,
    YNABPlanRow,
    YNABSplitLeg,
    YNABTransaction,
    anchor_month,
    plan_boundary,
)
from igab.integrations.ynab.oracle import (
    anchored_expected,
    export_consistency,
    subset_sums,
    ynab_rta,
)

JUL, AUG, SEP = date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)
D = Decimal


def txn(account, day, amount, group=None, category=None, splits=(), cleared="cleared"):
    return YNABTransaction(
        account_name=account,
        date=day,
        payee="x",
        category_group=group,
        category=category,
        memo=None,
        amount=D(amount),
        cleared=cleared,
        splits=list(splits),
    )


def months(first, count):
    """`count` consecutive month starts — a real export lists every month
    between its first and its last, which is what makes the clamp safe."""
    return [add_months(first, i) for i in range(count)]


def inflow(account, day, amount):
    return txn(account, day, amount, "Inflow", "Ready to Assign")


def plan(month, group, category, assigned="0", available=None, activity=None):
    return YNABPlanRow(
        month=month,
        category_group=group,
        category=category,
        assigned=D(assigned),
        activity=None if activity is None else D(activity),
        available=None if available is None else D(available),
    )


def budget(transactions=(), plan_rows=()):
    return YNABBudget(transactions=list(transactions), plan_rows=list(plan_rows))


class TestInflow:
    def test_counts_inflow_through_the_month_only(self):
        b = budget(
            [
                inflow("Checking", date(2026, 8, 3), "1000"),
                inflow("Checking", date(2026, 9, 1), "500"),
            ]
        )
        assert ynab_rta(b, AUG).inflow == D("1000")
        assert ynab_rta(b, SEP).inflow == D("1500")

    def test_a_split_leg_filed_as_inflow_counts(self):
        legs = [
            YNABSplitLeg("Inflow", "Ready to Assign", None, D("200")),
            YNABSplitLeg("Bills", "Fees", None, D("-20")),
        ]
        b = budget([txn("Checking", date(2026, 8, 3), "180", splits=legs)])
        assert ynab_rta(b, AUG).inflow == D("200")

    def test_a_skipped_account_is_out_of_scope(self):
        b = budget(
            [inflow("Checking", date(2026, 8, 3), "1000"), inflow("Old", date(2026, 8, 3), "5")]
        )
        assert ynab_rta(b, AUG, accounts={"checking"}).inflow == D("1000")
        assert ynab_rta(b, AUG).inflow == D("1005")

    def test_a_starting_balance_is_an_inflow_like_any_other(self):
        b = budget([inflow("Checking", date(2026, 7, 1), "2500")])
        assert ynab_rta(b, AUG).inflow == D("2500")


class TestAssigned:
    def test_every_month_counts_including_future_ones(self):
        b = budget(
            plan_rows=[plan(JUL, "Bills", "Rent", "1200"), plan(SEP, "Bills", "Rent", "1200")]
        )
        assert ynab_rta(b, AUG).assigned == D("2400")

    def test_card_payment_reserves_are_counted_and_reported(self):
        b = budget(
            plan_rows=[
                plan(AUG, "Bills", "Rent", "1200"),
                plan(AUG, "Credit Card Payments", "Visa", "300"),
            ]
        )
        o = ynab_rta(b, AUG)
        assert o.assigned == D("1500")
        assert o.credit_card_payment_assigned == D("300")


class TestWriteOffs:
    def test_cash_overspending_in_an_earlier_month_is_written_off(self):
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Checking", date(2026, 7, 9), "-150", "Bills", "Gas"),
            ],
            [plan(JUL, "Bills", "Gas", "100", "-50")],
        )
        o = ynab_rta(b, AUG)
        assert o.cash_overspending_written_off == D("50")
        assert o.rta == D("850")

    def test_the_current_months_overspending_is_not_written_off_yet(self):
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Checking", date(2026, 7, 9), "-150", "Bills", "Gas"),
            ],
            [plan(JUL, "Bills", "Gas", "100", "-50")],
        )
        assert ynab_rta(b, JUL).cash_overspending_written_off == D("0")
        assert ynab_rta(b, JUL).rta == D("900")

    def test_only_the_cash_share_of_a_mixed_overspend_is_written_off(self):
        """80 overspent, 50 of it on the card: YNAB writes off the 30 that was
        cash and leaves 50 riding on the card."""
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Visa", date(2026, 7, 5), "-50", "Everyday", "Groceries"),
                txn("Checking", date(2026, 7, 6), "-130", "Everyday", "Groceries"),
            ],
            [plan(JUL, "Everyday", "Groceries", "100", "-80")],
        )
        o = ynab_rta(b, AUG, credit_card_accounts={"Visa"})
        assert o.cash_overspending_written_off == D("30")


class TestCardAdjustment:
    def test_reset_credit_overspending_no_longer_separates_ynab_and_igab(self):
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Visa", date(2026, 7, 5), "-350", "Everyday", "Groceries"),
                # The payment pair, named the way an export names it — an
                # unmarked leg would read as an unfiled cash row.
                YNABTransaction(
                    "Checking",
                    date(2026, 7, 25),
                    "Transfer : Visa",
                    None,
                    None,
                    None,
                    D("-300"),
                    "cleared",
                ),
                YNABTransaction(
                    "Visa",
                    date(2026, 7, 25),
                    "Transfer : Checking",
                    None,
                    None,
                    None,
                    D("300"),
                    "cleared",
                ),
            ],
            [
                plan(JUL, "Everyday", "Groceries", "300", "-50"),
                plan(AUG, "Everyday", "Groceries", "0", "0"),
                plan(JUL, "Credit Card Payments", "Visa", "0", "0"),
                plan(AUG, "Credit Card Payments", "Visa", "0", "0"),
            ],
        )
        o = ynab_rta(b, AUG, credit_card_accounts={"Visa"})
        assert o.rta == D("700")  # 1000 − 300, nothing written off (credit)
        assert o.card_balances == D("-50")
        # Still computed — it is what the card section shows as Uncovered —
        # but IGAB follows the same rule now, so it explains no gap.
        assert o.uncovered_card_debt == D("50")
        assert o.expected_igab == D("700")

    def test_while_the_overspent_month_is_open_the_two_agree(self):
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Visa", date(2026, 7, 5), "-350", "Everyday", "Groceries"),
            ],
            [plan(JUL, "Everyday", "Groceries", "300", "-50")],
        )
        o = ynab_rta(b, JUL, credit_card_accounts={"Visa"})
        assert o.uncovered_current == D("50")
        assert o.uncovered_card_debt == D("300")  # −(−350) − 0 − 50: the covered part, still unpaid
        assert o.expected_igab == o.rta


class TestAvailable:
    def test_reports_ynabs_available_per_envelope_under_igabs_names(self):
        b = budget(
            plan_rows=[
                plan(AUG, "Bills", "Rent", "1200", "0"),
                plan(AUG, "Credit Card Payments", "Visa", "0", "40"),
                plan(JUL, "Bills", "Rent", "1200", "0"),
            ]
        )
        o = ynab_rta(b, AUG)
        assert o.available == {("Bills", "Rent"): D("0")}
        assert o.ccp_available == D("40")


class TestPendingRows:
    def test_an_envelopes_uncleared_rows_this_month_are_reported_beside_its_available(self):
        """YNAB ships an unapproved import in the register but counts it in
        the plan only once approved; the register only says "uncleared"."""
        b = budget(
            [
                txn(
                    "Checking", date(2026, 8, 14), "-249.78", "Bills", "Loans", cleared="uncleared"
                ),
                txn("Checking", date(2026, 8, 10), "-40", "Bills", "Loans"),
                txn("Checking", date(2026, 7, 30), "-5", "Bills", "Loans", cleared="uncleared"),
            ],
            [plan(AUG, "Bills", "Loans", "457", "417")],
        )
        o = ynab_rta(b, AUG)
        assert o.uncleared == {("Bills", "Loans"): [D("-249.78")]}

    def test_subset_sums_offer_every_combination_of_a_few_rows(self):
        """An envelope with an unapproved import AND a hand-entered uncleared
        row differs from YNAB by the import alone."""
        sums = subset_sums([D("-194.55"), D("46.96")])
        assert sums == {D("-194.55"), D("46.96"), D("-147.59")}


class TestUncategorized:
    def test_uncategorized_rows_on_budget_accounts_are_the_third_difference(self):
        """YNAB keeps an unfiled row out of the plan; IGAB takes it out of
        Ready to Assign until it is filed. A tracking account's unfiled rows
        are net-worth movement and count for neither."""
        b = budget(
            [
                inflow("Checking", date(2026, 8, 1), "1000"),
                txn("Checking", date(2026, 8, 3), "-40"),
                txn("Brokerage", date(2026, 8, 4), "-999"),
            ]
        )
        o = ynab_rta(b, AUG, tracking_accounts={"Brokerage"})
        assert o.rta == D("1000")
        assert o.uncategorized_net == D("-40")
        assert o.expected_igab == D("960")

    def test_a_transfer_leg_without_a_category_is_not_uncategorized_money(self):
        b = budget(
            [
                inflow("Checking", date(2026, 8, 1), "1000"),
                YNABTransaction(
                    "Checking",
                    date(2026, 8, 3),
                    "Transfer : Savings",
                    None,
                    None,
                    None,
                    D("-200"),
                    "cleared",
                ),
                YNABTransaction(
                    "Savings",
                    date(2026, 8, 3),
                    "Transfer : Checking",
                    None,
                    None,
                    None,
                    D("200"),
                    "cleared",
                ),
            ]
        )
        assert ynab_rta(b, AUG).uncategorized_net == D("0")


class TestExportConsistency:
    """Does the file agree with itself? Parity compares IGAB's recomputed
    Available against the column YNAB shipped, so a file whose own numbers
    contradict each other makes that comparison meaningless — and the report
    has to be able to say so instead of blaming the import."""

    def test_a_faithful_export_is_consistent(self):
        b = budget(
            [txn("Checking", date(2026, 7, 9), "-30", "Everyday", "Groceries")],
            [
                plan(JUL, "Everyday", "Groceries", assigned="100", activity="-30", available="70"),
                plan(AUG, "Everyday", "Groceries", assigned="50", activity="0", available="120"),
            ],
        )
        c = export_consistency(b)
        assert c.carryover_rows_violating == 0
        assert c.activity_cells_disagreeing == 0
        assert c.self_consistent

    def test_the_earliest_month_seeds_the_walk_rather_than_being_checked(self):
        """A category's first exported month has nothing to carry from. It is
        not evidence of anything, so it is not counted either way."""
        b = budget(
            plan_rows=[
                plan(JUL, "Everyday", "Groceries", assigned="0", activity="0", available="900"),
                plan(AUG, "Everyday", "Groceries", assigned="0", activity="0", available="900"),
            ]
        )
        c = export_consistency(b)
        assert c.carryover_rows_checked == 1
        assert c.carryover_rows_violating == 0

    def test_a_perturbed_available_is_a_carryover_violation(self):
        b = budget(
            plan_rows=[
                plan(JUL, "Everyday", "Groceries", assigned="100", activity="-30", available="70"),
                plan(AUG, "Everyday", "Groceries", assigned="50", activity="0", available="118.88"),
            ]
        )
        c = export_consistency(b)
        assert (c.carryover_rows_violating, c.carryover_rows_checked) == (1, 1)
        assert not c.self_consistent

    def test_cash_overspending_reset_to_zero_holds(self):
        """YNAB takes a negative month-end out of Ready to Assign and starts
        the next month at zero. That is YNAB behaving, not a broken file."""
        b = budget(
            plan_rows=[
                plan(
                    JUL, "Everyday", "Groceries", assigned="100", activity="-150", available="-50"
                ),
                plan(AUG, "Everyday", "Groceries", assigned="0", activity="0", available="0"),
            ]
        )
        assert export_consistency(b).carryover_rows_violating == 0

    def test_credit_overspending_riding_forward_holds(self):
        """The other half of the rule: overspending on a card stays negative
        rather than being written off, so available == expected."""
        b = budget(
            plan_rows=[
                plan(
                    JUL, "Everyday", "Groceries", assigned="100", activity="-150", available="-50"
                ),
                plan(AUG, "Everyday", "Groceries", assigned="0", activity="-10", available="-60"),
            ]
        )
        assert export_consistency(b).carryover_rows_violating == 0

    def test_activity_is_checked_against_the_register_shipped_beside_it(self):
        b = budget(
            [txn("Checking", date(2026, 7, 9), "-30", "Everyday", "Groceries")],
            [plan(JUL, "Everyday", "Groceries", assigned="100", activity="-31", available="69")],
        )
        c = export_consistency(b)
        assert (c.activity_cells_disagreeing, c.activity_cells_checked) == (1, 1)
        assert not c.self_consistent

    def test_split_legs_count_toward_the_register_side(self):
        legs = [
            YNABSplitLeg("Everyday", "Groceries", None, D("-30")),
            YNABSplitLeg("Everyday", "Fuel", None, D("-20")),
        ]
        b = budget(
            [txn("Checking", date(2026, 7, 9), "-50", splits=legs)],
            [
                plan(JUL, "Everyday", "Groceries", activity="-30", available="-30"),
                plan(JUL, "Everyday", "Fuel", activity="-20", available="-20"),
            ],
        )
        assert export_consistency(b).activity_cells_disagreeing == 0

    def test_card_payment_categories_are_left_out_of_both_checks(self):
        """YNAB generates their activity internally and never ships a register
        row for them, so counting them would fire on every healthy export."""
        b = budget(
            plan_rows=[
                plan(JUL, "Credit Card Payments", "Visa", activity="-500", available="500"),
                plan(AUG, "Credit Card Payments", "Visa", activity="-500", available="999"),
            ]
        )
        c = export_consistency(b)
        assert (c.carryover_rows_checked, c.activity_cells_checked) == (0, 0)
        assert c.self_consistent

    def test_a_register_only_export_checks_nothing_and_is_not_thereby_suspect(self):
        b = budget([txn("Checking", date(2026, 7, 9), "-30", "Everyday", "Groceries")])
        c = export_consistency(b)
        assert (c.carryover_rows_checked, c.activity_cells_checked) == (0, 0)
        assert c.self_consistent

    def test_a_blank_advisory_column_is_not_evidence_either_way(self):
        """`activity`/`available` are None when YNAB left the cell blank or it
        could not be read. Neither check may invent a zero for them."""
        b = budget(plan_rows=[plan(JUL, "Everyday", "Groceries", assigned="100")])
        c = export_consistency(b)
        assert (c.carryover_rows_checked, c.activity_cells_checked) == (0, 0)

    def test_every_account_is_in_scope(self):
        """Consistency is a property of the file. The plan reflects the whole
        budget, so skipping an account at import cannot make the file
        disagree with itself — and this check takes no account argument."""
        b = budget(
            [txn("Brokerage", date(2026, 7, 9), "-30", "Savings", "Vanguard")],
            [plan(JUL, "Savings", "Vanguard", activity="-30", available="-30")],
        )
        assert export_consistency(b).activity_cells_disagreeing == 0


class TestNetCardMovement:
    """The oracle nets a month's card charges against its refunds, because
    `credit_floored_by_month` does. Accumulating only the negative legs made
    the two disagree on any month that had both — independently of any defect
    in the engine, and before this was fixed nothing compared them."""

    def _budget(self):
        return budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Visa", date(2026, 7, 5), "-100", "Everyday", "Groceries"),
                txn("Visa", date(2026, 7, 20), "80", "Everyday", "Groceries"),
            ],
            [
                plan(JUL, "Everyday", "Groceries", "0", "-50"),
                plan(AUG, "Everyday", "Groceries", "0", "0"),
                plan(JUL, "Credit Card Payments", "Visa", "0", "0"),
                plan(AUG, "Credit Card Payments", "Visa", "0", "0"),
            ],
        )

    def test_a_month_with_a_charge_and_a_refund_writes_off_the_net(self):
        # Net card spending is 20, so of the 50 shortfall only 20 rode; 30 is
        # cash overspending. Read gross (100), the whole 50 looked credit-funded
        # and nothing was written off — a 30 gap against IGAB.
        o = ynab_rta(self._budget(), AUG, credit_card_accounts={"Visa"})
        assert o.cash_overspending_written_off == D("30")
        assert o.rta == D("970")

    def test_the_open_month_uncovers_only_the_net(self):
        o = ynab_rta(self._budget(), JUL, credit_card_accounts={"Visa"})
        assert o.uncovered_current == D("20")

    def test_a_month_that_nets_to_a_refund_rides_nothing(self):
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Visa", date(2026, 7, 5), "-40", "Everyday", "Groceries"),
                txn("Visa", date(2026, 7, 20), "90", "Everyday", "Groceries"),
            ],
            [plan(JUL, "Everyday", "Groceries", "0", "-50")],
        )
        o = ynab_rta(b, JUL, credit_card_accounts={"Visa"})
        assert o.uncovered_current == D("0")


class TestParityExplanations:
    """A difference the parity check can account for is not a defect. Both
    kinds are bounded and named at the definition, per the repo's rule that
    deliberate divergence is fine but silence is not."""

    def test_an_uncleared_row_explains_its_own_gap(self):
        from igab.integrations.ynab.parity import ParityDifference

        d = ParityDifference("Everyday: Groceries", D("80"), D("100"), pending=D("-20"))
        assert d.explained

    def test_a_repaid_card_debt_explains_the_gap_it_causes(self):
        """YNAB releases a card refund from the CCP reserve uncapped and hands
        the whole thing back to the envelope; IGAB routes the part that met
        debt nobody reserved cash for to the card, so its Available is lower by
        exactly that. The two still agree on Ready to Assign."""
        from igab.integrations.ynab.parity import ParityDifference

        d = ParityDifference(
            "Everyday: Groceries", D("0"), D("100"), repaid_uncovered_debt=D("100")
        )
        assert d.explained

    def test_a_gap_the_repayment_does_not_account_for_is_still_a_difference(self):
        from igab.integrations.ynab.parity import ParityDifference

        d = ParityDifference(
            "Everyday: Groceries", D("0"), D("175"), repaid_uncovered_debt=D("100")
        )
        assert not d.explained

    def test_a_matching_envelope_is_not_explained_away(self):
        from igab.integrations.ynab.parity import ParityDifference

        assert not ParityDifference("Everyday: Groceries", D("100"), D("100")).explained


class TestPlanBoundary:
    """One spelling of the anchor boundary — the last plan month at or
    before today, and always a month the export actually carries."""

    def test_no_plan_no_boundary(self):
        assert plan_boundary([], date(2026, 9, 3)) is None

    def test_clamped_by_today_for_future_assignment_months(self):
        rows = [plan(m, "g", "c", "5") for m in months(date(2026, 6, 1), 6)]
        assert plan_boundary(rows, date(2026, 9, 3)) == date(2026, 9, 1)

    def test_an_old_export_boundaries_at_its_own_last_month(self):
        rows = [plan(date(2026, 3, 1), "g", "c"), plan(date(2026, 5, 1), "g", "c")]
        assert plan_boundary(rows, date(2026, 9, 3)) == date(2026, 5, 1)

    def test_a_gap_before_today_falls_back_to_a_month_the_export_has(self):
        """Budgeted ahead into December, nothing planned since June: the
        obvious spelling, min(today, max(month)), names September — a month
        no plan row mentions. `_seed_arrangement` then matches nothing and
        every group lands at sort_order 0, and the anchor seed reads an empty
        month."""
        rows = [plan(date(2026, 6, 1), "g", "c"), plan(date(2026, 12, 1), "g", "c")]
        assert plan_boundary(rows, date(2026, 9, 3)) == date(2026, 6, 1)

    def test_an_export_entirely_in_the_future_uses_its_first_month(self):
        """A budget that starts next month has no past to clamp to; the
        earliest month it carries is the only honest layout."""
        rows = [plan(date(2026, 10, 1), "g", "c"), plan(date(2026, 11, 1), "g", "c")]
        assert plan_boundary(rows, date(2026, 9, 3)) == date(2026, 10, 1)


class TestAnchorMonth:
    """The boundary the anchor itself can use: B, but only when B−1 is in
    the export. The preview screen and `_write_anchor` ask this same
    question, so the screen never promises an anchor the import declines."""

    def test_none_without_a_plan(self):
        assert anchor_month([], date(2026, 9, 3)) is None

    def test_none_when_the_export_begins_at_the_boundary(self):
        """A budget younger than one complete YNAB month has no position to
        anchor on."""
        rows = [plan(date(2026, 9, 1), "g", "c")]
        assert anchor_month(rows, date(2026, 9, 3)) is None

    def test_the_boundary_when_the_month_before_it_is_present(self):
        rows = [plan(date(2026, 8, 1), "g", "c"), plan(date(2026, 9, 1), "g", "c")]
        assert anchor_month(rows, date(2026, 9, 3)) == date(2026, 9, 1)

    def test_none_when_the_boundary_month_stands_alone_after_a_gap(self):
        """June and December, today September: the boundary is June, whose
        previous month the file never mentions. Anchoring there would seed
        every envelope from nothing."""
        rows = [plan(date(2026, 6, 1), "g", "c"), plan(date(2026, 12, 1), "g", "c")]
        assert anchor_month(rows, date(2026, 9, 3)) is None


class TestAnchoredExpected:
    """The cash form of the Ready to Assign rule, for anchored budgets."""

    def _b(self):
        return budget(
            [
                inflow("Checking", date(2026, 7, 3), "1000"),
                txn("Checking", date(2026, 7, 10), "-200", "Everyday", "Groceries"),
                txn("Sapphire Visa", date(2026, 7, 12), "-50", "Everyday", "Groceries"),
            ],
            [
                plan(date(2026, 7, 1), "Everyday", "Groceries", "300", available="50"),
                plan(
                    date(2026, 7, 1),
                    "Credit Card Payments",
                    "Sapphire Visa",
                    "0",
                    available="50",
                ),
                plan(date(2026, 8, 1), "Everyday", "Groceries", "25", available="75"),
            ],
        )

    def test_matches_the_history_form_plus_uncategorized_on_a_coherent_file(self):
        """The F1 equivalence: on a file whose own numbers cohere, the cash
        form and the history form describe the same budget — offset only by
        uncategorized rows, which sit inside cash here and outside the plan
        there."""
        o = ynab_rta(self._b(), date(2026, 7, 1), credit_card_accounts={"Sapphire Visa"})
        assert anchored_expected(o) == o.rta + o.uncategorized_net

    def test_card_balances_split_sums_to_the_total(self):
        o = ynab_rta(self._b(), date(2026, 7, 1), credit_card_accounts={"Sapphire Visa"})
        assert sum(o.card_balances_by_card.values(), D("0")) == o.card_balances
        assert o.card_balances_by_card == {"sapphire visa": D("-50")}

    def test_assigned_after_counts_only_later_months(self):
        o = ynab_rta(self._b(), date(2026, 7, 1), credit_card_accounts={"Sapphire Visa"})
        assert o.assigned_after == D("25")
        assert o.cash_balance == D("800")
