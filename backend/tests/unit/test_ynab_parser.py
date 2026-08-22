import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from igab.integrations.ynab.parser import YNABParser, _parse_currency, _parse_date, _parse_month

REGISTER_CSV = """\
"Account","Flag","Date","Payee","Category Group/Category","Category Group","Category","Memo","Outflow","Inflow","Cleared"
"Checking","","04/15/2026","Walmart","Food: Groceries","Food","Groceries","weekly shop",$45.00,$0.00,"Reconciled"
"Checking","","04/15/2026","Payroll","Inflow: Ready to Assign","Inflow","Ready to Assign","",$0.00,$3000.00,"Cleared"
"Checking","","04/16/2026","Transfer : Savings","","","","",$200.00,$0.00,"Reconciled"
"Savings","","04/16/2026","Transfer : Checking","","","","",$0.00,$200.00,"Reconciled"
"""

PLAN_CSV = """\
"Month","Category Group/Category","Category Group","Category","Assigned","Activity","Available"
"Apr 2026","Food: Groceries","Food","Groceries",$500.00,-$45.00,$455.00
"Apr 2026","Food: Restaurants","Food","Restaurants",$100.00,$0.00,$100.00
"Mar 2026","Food: Groceries","Food","Groceries",$500.00,-$489.00,$11.00
"""


def _make_zip(tmp_path: Path, register: str, plan: str | None = None) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Budget Export - Register.csv", register)
        if plan is not None:
            zf.writestr("Budget Export - Plan.csv", plan)
    buf.seek(0)
    path = tmp_path / "test_ynab_export.zip"
    path.write_bytes(buf.read())
    return path


class TestParseCurrency:
    def test_dollar_sign(self):
        assert _parse_currency("$45.00") == Decimal("45.00")

    def test_negative(self):
        assert _parse_currency("-$45.00") == Decimal("-45.00")

    def test_commas(self):
        assert _parse_currency("$1,234.56") == Decimal("1234.56")

    def test_zero(self):
        assert _parse_currency("$0.00") == Decimal("0")

    def test_invalid(self):
        assert _parse_currency("N/A") == Decimal("0")


class TestParseDate:
    def test_mm_dd_yyyy(self):
        assert _parse_date("04/15/2026") == date(2026, 4, 15)

    def test_iso(self):
        assert _parse_date("2026-04-15") == date(2026, 4, 15)

    def test_invalid(self):
        assert _parse_date("not-a-date") is None


class TestParseMonth:
    def test_valid(self):
        assert _parse_month("Apr 2026") == date(2026, 4, 1)

    def test_all_months(self):
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for i, abbr in enumerate(months, start=1):
            assert _parse_month(f"{abbr} 2025") == date(2025, i, 1)

    def test_invalid(self):
        assert _parse_month("April 2026") is None


class TestYNABParser:
    def setup_method(self):
        self.parser = YNABParser()

    def test_parse_register_transactions(self):
        txns = self.parser.parse_register_csv(REGISTER_CSV)
        assert len(txns) == 4

        walmart = txns[0]
        assert walmart.account_name == "Checking"
        assert walmart.date == date(2026, 4, 15)
        assert walmart.payee == "Walmart"
        assert walmart.category_group == "Food"
        assert walmart.category == "Groceries"
        assert walmart.memo == "weekly shop"
        assert walmart.amount == Decimal("-45.00")
        assert walmart.cleared == "reconciled"

    def test_parse_inflow(self):
        txns = self.parser.parse_register_csv(REGISTER_CSV)
        payroll = txns[1]
        assert payroll.amount == Decimal("3000.00")

    def test_parse_transfer(self):
        txns = self.parser.parse_register_csv(REGISTER_CSV)
        transfer_out = txns[2]
        assert transfer_out.payee == "Transfer : Savings"
        assert transfer_out.amount == Decimal("-200.00")

    def test_parse_plan_csv(self):
        entries = self.parser.parse_plan_csv(PLAN_CSV)
        assert len(entries) == 3

        apr = entries[0]
        assert apr.month == date(2026, 4, 1)
        assert apr.category_group == "Food"
        assert apr.category == "Groceries"
        assert apr.assigned == Decimal("500.00")

    def test_parse_zip(self, tmp_path: Path):
        path = _make_zip(tmp_path, REGISTER_CSV, PLAN_CSV)
        budget = self.parser.parse_zip(path)
        assert len(budget.transactions) == 4
        assert len(budget.budget_entries) == 3

    def test_parse_zip_without_plan(self, tmp_path: Path):
        path = _make_zip(tmp_path, REGISTER_CSV)
        budget = self.parser.parse_zip(path)
        assert len(budget.transactions) == 4
        assert budget.budget_entries == []

    def test_parse_zip_missing_register_raises(self, tmp_path: Path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("something.txt", "data")
        buf.seek(0)
        path = tmp_path / "test_no_register.zip"
        path.write_bytes(buf.read())
        with pytest.raises(ValueError, match="Register CSV not found"):
            self.parser.parse_zip(path)


SPLIT_HEADER = (
    '"Account","Flag","Date","Payee","Category Group/Category",'
    '"Category Group","Category","Memo","Outflow","Inflow","Cleared"\n'
)


def _reg_row(
    *,
    account: str = "Checking",
    date_: str = "06/18/2026",
    payee: str = "BJs Wholesale",
    group: str = "Everyday",
    category: str = "Groceries",
    memo: str = "",
    outflow: str = "$0.00",
    inflow: str = "$0.00",
    cleared: str = "Reconciled",
) -> str:
    gc = f"{group}: {category}" if group and category else ""
    return (
        f'"{account}","","{date_}","{payee}","{gc}","{group}","{category}",'
        f'"{memo}",{outflow},{inflow},"{cleared}"\n'
    )


class TestSplitReassembly:
    """YNAB register exports flatten split transactions into per-leg rows
    memo-tagged 'Split (i/n)'. Complete consecutive runs are reassembled into
    one transaction (amount = the bank total the sync matcher must see);
    anything irregular falls back to flat rows so a malformed export can
    never lose data."""

    def setup_method(self):
        self.parser = YNABParser()

    def _parse(self, *rows: str):
        return self.parser.parse_register_csv(SPLIT_HEADER + "".join(rows))

    def test_complete_run_grouped_into_one_transaction(self):
        txns = self._parse(
            _reg_row(memo="Split (1/3) ", outflow="$63.97", category="Groceries"),
            _reg_row(memo="Split (2/3) ", outflow="$25.00", category="Pets"),
            _reg_row(memo="Split (3/3) paper towels", outflow="$90.93", category="Household"),
        )
        assert len(txns) == 1
        parent = txns[0]
        assert parent.amount == Decimal("-179.90")
        assert parent.category_group is None
        assert parent.category is None
        assert parent.memo is None
        assert parent.cleared == "reconciled"
        assert parent.payee == "BJs Wholesale"
        assert [leg.amount for leg in parent.splits] == [
            Decimal("-63.97"),
            Decimal("-25.00"),
            Decimal("-90.93"),
        ]
        assert [leg.category for leg in parent.splits] == ["Groceries", "Pets", "Household"]
        assert [leg.memo for leg in parent.splits] == [None, None, "paper towels"]

    def test_zero_amount_leg_preserved(self):
        """Real exports contain $0.00 legs (a category line zeroed out)."""
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$58.15"),
            _reg_row(memo="Split (2/2) ", outflow="$0.00", category="Pets"),
        )
        assert len(txns) == 1
        assert txns[0].amount == Decimal("-58.15")
        assert txns[0].splits[1].amount == Decimal("0.00")

    def test_mixed_sign_legs_sum_to_net(self):
        """A refund leg inside a split: the grouped amount is the net."""
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$100.00"),
            _reg_row(memo="Split (2/2) rebate", inflow="$15.00"),
        )
        assert len(txns) == 1
        assert txns[0].amount == Decimal("-85.00")

    def test_adjacent_runs_same_day_and_payee_stay_separate(self):
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$10.00"),
            _reg_row(memo="Split (2/2) ", outflow="$20.00"),
            _reg_row(memo="Split (1/2) ", outflow="$30.00"),
            _reg_row(memo="Split (2/2) ", outflow="$40.00"),
        )
        assert [t.amount for t in txns] == [Decimal("-30.00"), Decimal("-70.00")]
        assert all(len(t.splits) == 2 for t in txns)

    def test_truncated_run_falls_back_to_flat_rows(self):
        txns = self._parse(
            _reg_row(memo="Split (1/3) ", outflow="$10.00"),
            _reg_row(memo="Split (2/3) ", outflow="$20.00"),
        )
        assert len(txns) == 2
        assert all(not t.splits for t in txns)
        assert txns[0].memo == "Split (1/3)"
        assert txns[0].amount == Decimal("-10.00")

    def test_interrupted_run_falls_back_to_flat_rows(self):
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$10.00"),
            _reg_row(payee="Gas Station", memo="fill up", outflow="$35.00"),
            _reg_row(memo="Split (2/2) ", outflow="$20.00"),
        )
        assert len(txns) == 3
        assert all(not t.splits for t in txns)

    def test_orphan_mid_run_marker_stays_flat(self):
        txns = self._parse(_reg_row(memo="Split (2/3) ", outflow="$20.00"))
        assert len(txns) == 1
        assert not txns[0].splits
        assert txns[0].memo == "Split (2/3)"

    def test_mismatched_n_breaks_run(self):
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$10.00"),
            _reg_row(memo="Split (2/3) ", outflow="$20.00"),
        )
        assert len(txns) == 2
        assert all(not t.splits for t in txns)

    def test_payee_change_breaks_run(self):
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$10.00", payee="BJs Wholesale"),
            _reg_row(memo="Split (2/2) ", outflow="$20.00", payee="BJ's Wholesale"),
        )
        assert len(txns) == 2
        assert all(not t.splits for t in txns)

    def test_date_change_breaks_run(self):
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$10.00", date_="06/18/2026"),
            _reg_row(memo="Split (2/2) ", outflow="$20.00", date_="06/19/2026"),
        )
        assert len(txns) == 2
        assert all(not t.splits for t in txns)

    def test_cleared_change_breaks_run(self):
        txns = self._parse(
            _reg_row(memo="Split (1/2) ", outflow="$10.00", cleared="Reconciled"),
            _reg_row(memo="Split (2/2) ", outflow="$20.00", cleared="Cleared"),
        )
        assert len(txns) == 2
        assert all(not t.splits for t in txns)

    def test_single_leg_marker_not_grouped(self):
        """'Split (1/1)' is a degenerate marker — leave the row untouched."""
        txns = self._parse(_reg_row(memo="Split (1/1) lone", outflow="$10.00"))
        assert len(txns) == 1
        assert not txns[0].splits
        assert txns[0].memo == "Split (1/1) lone"

    def test_flat_rows_around_a_run_preserved_in_order(self):
        txns = self._parse(
            _reg_row(payee="Coffee", memo="latte", outflow="$5.00"),
            _reg_row(memo="Split (1/2) ", outflow="$10.00"),
            _reg_row(memo="Split (2/2) ", outflow="$20.00"),
            _reg_row(payee="Bakery", memo="", outflow="$7.00"),
        )
        assert [t.payee for t in txns] == ["Coffee", "BJs Wholesale", "Bakery"]
        assert txns[1].splits and txns[1].amount == Decimal("-30.00")

    def test_memo_merely_resembling_marker_is_untouched(self):
        txns = self._parse(
            _reg_row(memo="Split (tentative) with Alex", outflow="$10.00"),
        )
        assert len(txns) == 1
        assert not txns[0].splits
        assert txns[0].memo == "Split (tentative) with Alex"
