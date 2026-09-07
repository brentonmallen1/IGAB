"""A register row dated after the import's today is an upcoming
transaction, not history.

YNAB exports a scheduled transaction as its next dated instance with no
cadence. Imported as a posted row it moved Ready to Assign for money that
had not left, and the parity oracle — which bounded rows by month end only
— counted it too, blaming IGAB for a gap the file carried.
"""

from datetime import date
from decimal import Decimal

from igab.api.v1.imports import build_ynab_preview
from igab.integrations.ynab.models import (
    YNABBudget,
    YNABSplitLeg,
    YNABTransaction,
    hold_out_future,
)
from igab.integrations.ynab.oracle import export_consistency, ynab_rta

TODAY = date(2026, 9, 6)


def txn(when: date, amount: str = "-50.00", *, account="Checking", splits=()) -> YNABTransaction:
    return YNABTransaction(
        account_name=account,
        date=when,
        payee="Oakwood Property Mgmt",
        category_group="Bills",
        category="Rent",
        memo=None,
        amount=Decimal(amount),
        cleared="uncleared",
        splits=list(splits),
    )


class TestHoldOut:
    def test_a_row_dated_after_today_is_held_out(self):
        b = hold_out_future(YNABBudget(transactions=[txn(date(2026, 9, 7))]), TODAY)
        assert b.transactions == []
        assert [t.date for t in b.held_out] == [date(2026, 9, 7)]

    def test_a_row_dated_today_is_not(self):
        b = hold_out_future(YNABBudget(transactions=[txn(TODAY)]), TODAY)
        assert [t.date for t in b.transactions] == [TODAY]
        assert b.held_out == []

    def test_a_future_split_is_held_out_whole(self):
        legs = [
            YNABSplitLeg("Everyday", "Groceries", None, Decimal("-40.00")),
            YNABSplitLeg("Everyday", "Household", None, Decimal("-20.00")),
        ]
        b = hold_out_future(
            YNABBudget(transactions=[txn(date(2026, 10, 1), "-60.00", splits=legs)]), TODAY
        )
        assert b.transactions == []
        [held] = b.held_out
        assert len(held.splits) == 2 and held.amount == Decimal("-60.00")

    def test_hold_out_preserves_order_of_the_rest(self):
        rows = [txn(date(2026, 9, 3)), txn(date(2026, 9, 9)), txn(date(2026, 9, 1))]
        b = hold_out_future(YNABBudget(transactions=rows), TODAY)
        assert [t.date for t in b.transactions] == [date(2026, 9, 3), date(2026, 9, 1)]

    def test_hold_out_is_a_pure_function_of_today(self):
        rows = [txn(date(2026, 9, 3)), txn(date(2026, 9, 9))]
        early = hold_out_future(YNABBudget(transactions=list(rows)), date(2026, 9, 2))
        late = hold_out_future(YNABBudget(transactions=list(rows)), date(2026, 9, 30))
        assert len(early.held_out) == 2
        assert late.held_out == []


class TestPreviewCounts:
    def test_future_rows_are_counted_separately_and_not_in_transaction_count(self):
        b = hold_out_future(
            YNABBudget(transactions=[txn(date(2026, 9, 3)), txn(date(2026, 9, 9))]), TODAY
        )
        preview = build_ynab_preview(b, remembered={})
        assert preview.transaction_count == 1
        assert preview.held_out_future_count == 1
        [account] = preview.accounts
        assert account.transaction_count == 1
        assert account.implied_balance == Decimal("-50.00")

    def test_an_account_seen_only_in_the_future_still_appears_for_mapping(self):
        b = hold_out_future(
            YNABBudget(
                transactions=[txn(date(2026, 9, 3)), txn(date(2026, 9, 9), account="New Card")]
            ),
            TODAY,
        )
        preview = build_ynab_preview(b, remembered={})
        by_name = {a.name: a for a in preview.accounts}
        assert set(by_name) == {"Checking", "New Card"}
        assert by_name["New Card"].transaction_count == 0
        assert by_name["New Card"].implied_balance == Decimal("0")
        assert by_name["New Card"].last_activity == date(2026, 9, 9)


class TestOracleNeverSeesAHeldOutRow:
    def test_a_future_row_in_the_boundary_month_is_not_in_inflow_or_cash(self):
        """The oracle bounds by month end: a paycheck dated 25 Sep counted
        into September's figure when the import ran on the 6th, and YNAB
        shows it nowhere until the 25th."""
        paycheck = YNABTransaction(
            account_name="Checking",
            date=date(2026, 9, 25),
            payee="Northwind Payserv",
            category_group="Inflow",
            category="Ready to Assign",
            memo=None,
            amount=Decimal("3000.00"),
            cleared="uncleared",
        )
        posted = YNABTransaction(
            account_name="Checking",
            date=date(2026, 9, 1),
            payee="Northwind Payserv",
            category_group="Inflow",
            category="Ready to Assign",
            memo=None,
            amount=Decimal("1000.00"),
            cleared="cleared",
        )
        b = hold_out_future(YNABBudget(transactions=[posted, paycheck]), TODAY)
        o = ynab_rta(b, date(2026, 9, 1))
        assert o.inflow == Decimal("1000.00")
        assert o.cash_balance == Decimal("1000.00")

    def test_export_consistency_does_not_count_a_held_out_row_as_register_activity(self):
        from igab.integrations.ynab.models import YNABPlanRow

        b = hold_out_future(
            YNABBudget(
                transactions=[txn(date(2026, 9, 3)), txn(date(2026, 9, 9))],
                plan_rows=[
                    YNABPlanRow(
                        month=date(2026, 9, 1),
                        category_group="Bills",
                        category="Rent",
                        assigned=Decimal("100.00"),
                        activity=Decimal("-50.00"),
                        available=Decimal("50.00"),
                    )
                ],
            ),
            TODAY,
        )
        consistency = export_consistency(b)
        assert consistency.activity_cells_checked == 1
        assert consistency.activity_cells_disagreeing == 0
