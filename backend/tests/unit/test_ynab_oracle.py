"""integrations.ynab.oracle — YNAB's rules, one case each."""

from datetime import date
from decimal import Decimal

from igab.integrations.ynab.models import (
    YNABBudget,
    YNABPlanRow,
    YNABSplitLeg,
    YNABTransaction,
)
from igab.integrations.ynab.oracle import subset_sums, ynab_rta

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


def inflow(account, day, amount):
    return txn(account, day, amount, "Inflow", "Ready to Assign")


def plan(month, group, category, assigned="0", available=None):
    return YNABPlanRow(
        month=month,
        category_group=group,
        category=category,
        assigned=D(assigned),
        activity=None,
        available=None if available is None else D(available),
    )


def budget(transactions=(), plan_rows=()):
    return YNABBudget(transactions=list(transactions), plan_rows=list(plan_rows))


class TestInflow:
    def test_counts_inflow_through_the_month_only(self):
        b = budget([inflow("Checking", date(2026, 8, 3), "1000"), inflow("Checking", date(2026, 9, 1), "500")])
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
        b = budget([inflow("Checking", date(2026, 8, 3), "1000"), inflow("Old", date(2026, 8, 3), "5")])
        assert ynab_rta(b, AUG, accounts={"checking"}).inflow == D("1000")
        assert ynab_rta(b, AUG).inflow == D("1005")

    def test_a_starting_balance_is_an_inflow_like_any_other(self):
        b = budget([inflow("Checking", date(2026, 7, 1), "2500")])
        assert ynab_rta(b, AUG).inflow == D("2500")


class TestAssigned:
    def test_every_month_counts_including_future_ones(self):
        b = budget(plan_rows=[plan(JUL, "Bills", "Rent", "1200"), plan(SEP, "Bills", "Rent", "1200")])
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
            [inflow("Checking", date(2026, 7, 1), "1000"), txn("Checking", date(2026, 7, 9), "-150", "Bills", "Gas")],
            [plan(JUL, "Bills", "Gas", "100", "-50")],
        )
        o = ynab_rta(b, AUG)
        assert o.cash_overspending_written_off == D("50")
        assert o.rta == D("850")

    def test_the_current_months_overspending_is_not_written_off_yet(self):
        b = budget(
            [inflow("Checking", date(2026, 7, 1), "1000"), txn("Checking", date(2026, 7, 9), "-150", "Bills", "Gas")],
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
    def test_reset_credit_overspending_is_the_gap_between_ynab_and_igab(self):
        b = budget(
            [
                inflow("Checking", date(2026, 7, 1), "1000"),
                txn("Visa", date(2026, 7, 5), "-350", "Everyday", "Groceries"),
                txn("Checking", date(2026, 7, 25), "-300"),  # card payment leg
                txn("Visa", date(2026, 7, 25), "300"),
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
        assert o.uncovered_card_debt == D("50")
        assert o.expected_igab == D("650")

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
        assert o.expected_igab == o.rta - D("300")


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
                txn("Checking", date(2026, 8, 14), "-249.78", "Bills", "Loans", cleared="uncleared"),
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
                YNABTransaction("Checking", date(2026, 8, 3), "Transfer : Savings", None, None, None, D("-200"), "cleared"),
                YNABTransaction("Savings", date(2026, 8, 3), "Transfer : Checking", None, None, None, D("200"), "cleared"),
            ]
        )
        assert ynab_rta(b, AUG).uncategorized_net == D("0")
