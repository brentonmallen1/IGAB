import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from igab.integrations.ynab.parser import YNABParser, _parse_currency, _parse_date, _parse_month

# ruff: noqa: E501 — these are YNAB export rows, verbatim. A wrapped
# fixture is no longer the file the parser has to read.
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


def _make_zip(
    tmp_path: Path,
    register: str,
    plan: str | None = None,
    plan_member: str = "Budget Export - Plan.csv",
) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Budget Export - Register.csv", register)
        if plan is not None:
            zf.writestr(plan_member, plan)
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

    def test_an_unreadable_amount_raises_instead_of_becoming_zero(self):
        """This test used to assert the opposite, pinning the bug in place.

        Returning Decimal("0") imported the transaction anyway with no money
        in it: the row count still reconciled and only the balance was wrong,
        which is the hardest kind of error to notice and the worst kind to
        have in a ledger. Callers now skip the row and say which one."""
        with pytest.raises(ValueError):
            _parse_currency("N/A")

    def test_an_ambiguous_european_decimal_is_rejected_not_guessed(self):
        """ "1,50" is either one-fifty or one hundred and fifty. The old
        parser stripped the comma and returned 150 — a hundredfold error, in
        silence. The shared parser refuses to guess."""
        with pytest.raises(ValueError):
            _parse_currency("1,50")

    def test_non_finite_and_absurd_magnitudes_are_rejected(self):
        """What `domain/money.py` exists for: "a single NaN poisons every SUM
        the app runs". This path went around validate_money entirely."""
        for bad in ("NaN", "Infinity", "99999999999999"):
            with pytest.raises(ValueError):
                _parse_currency(bad)

    def test_european_thousands_still_parse(self):
        # Both separators present: the rightmost is the decimal point.
        assert _parse_currency("1.234,56") == Decimal("1234.56")

    def test_parenthesised_negatives_parse(self):
        assert _parse_currency("($45.00)") == Decimal("-45.00")


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
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
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

    def test_parse_plan_rows_keeps_every_row_in_file_order(self):
        """The plan's row order is YNAB's display order — the layout an
        import restores — and Activity/Available are kept as YNAB's answers."""
        rows = self.parser.parse_plan_rows(PLAN_CSV)
        assert [(r.month, r.category) for r in rows] == [
            (date(2026, 4, 1), "Groceries"),
            (date(2026, 4, 1), "Restaurants"),
            (date(2026, 3, 1), "Groceries"),
        ]
        assert rows[0].activity == Decimal("-45.00")
        assert rows[0].available == Decimal("455.00")

    def test_a_zero_assigned_row_is_a_plan_row_but_not_an_entry(self):
        content = PLAN_CSV + '"Apr 2026","Food: Snacks","Food","Snacks",$0.00,,\n'
        rows = self.parser.parse_plan_rows(content)
        assert rows[-1].category == "Snacks"
        assert rows[-1].assigned == Decimal("0")
        assert rows[-1].activity is None
        assert rows[-1].available is None
        assert [e.category for e in self.parser.parse_plan_csv(content)] == [
            "Groceries",
            "Restaurants",
            "Groceries",
        ]

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


class TestAnUnreadableAmountIsReportedNotInvented:
    """A dropped row is visible in the counts. A row imported with a silently
    invented zero is not: the count reconciles and only the balance is wrong.

    This is the failure `domain/money.py` was written to prevent, and the YNAB
    path went around it — the CSV path has always used `parse_csv_amount`.
    """

    def test_a_bad_register_row_is_skipped_and_recorded(self):
        parser = YNABParser()
        register = SPLIT_HEADER + _reg_row(outflow="N/A") + _reg_row(outflow="$12.00")

        txns = parser.parse_register_csv(register)

        assert len(txns) == 1, "the readable row still imports"
        assert txns[0].amount == Decimal("-12.00")
        assert len(parser.errors) == 1
        assert "Checking" in parser.errors[0]

    def test_a_bad_plan_row_is_skipped_and_recorded(self):
        parser = YNABParser()
        plan = (
            '"Month","Category Group/Category","Category Group","Category",'
            '"Assigned","Activity","Available"\n'
            '"Apr 2026","Food: Groceries","Food","Groceries",N/A,$0.00,$0.00\n'
            '"Apr 2026","Food: Restaurants","Food","Restaurants",$100.00,$0.00,$100.00\n'
        )

        entries = parser.parse_plan_csv(plan)

        assert len(entries) == 1
        assert entries[0].category == "Restaurants"
        assert len(parser.errors) == 1

    def test_the_errors_reach_the_parsed_budget(self, tmp_path: Path):
        parser = YNABParser()
        path = _make_zip(tmp_path, SPLIT_HEADER + _reg_row(outflow="N/A"), PLAN_CSV)

        budget = parser.parse_zip(path)

        assert budget.transactions == []
        assert budget.errors == ["Checking 06/18/2026: cannot parse amount 'N/A'"]

    def test_a_clean_export_reports_nothing(self, tmp_path: Path):
        parser = YNABParser()
        path = _make_zip(tmp_path, REGISTER_CSV, PLAN_CSV)

        budget = parser.parse_zip(path)

        assert budget.errors == []


#: The same plan under the spelling YNAB used before "Budgeted" became
#: "Assigned" and Budget.csv became Plan.csv.
LEGACY_PLAN_CSV = PLAN_CSV.replace('"Assigned"', '"Budgeted"')


class TestOlderExportsStillCarryTheirAssignments:
    """An export naming the member Budget.csv, or its column Budgeted, used
    to import with zero assignments and no error — indistinguishable from a
    budget nobody had ever funded. Each spelling is read on its own, because
    a file may have been renamed without its header changing."""

    def setup_method(self):
        self.parser = YNABParser()

    def _entries(self, path: Path):
        return {
            (e.category, e.month): e.assigned for e in self.parser.parse_zip(path).budget_entries
        }

    def test_the_modern_spelling_is_the_baseline(self, tmp_path: Path):
        entries = self._entries(_make_zip(tmp_path, REGISTER_CSV, PLAN_CSV))
        assert entries[("Groceries", date(2026, 4, 1))] == Decimal("500.00")
        assert len(entries) == 3

    def test_the_old_member_name_reads_the_same(self, tmp_path: Path):
        path = _make_zip(tmp_path, REGISTER_CSV, PLAN_CSV, "Budget Export - Budget.csv")
        assert self._entries(path) == self._entries(_make_zip(tmp_path, REGISTER_CSV, PLAN_CSV))

    def test_the_old_column_name_reads_the_same(self, tmp_path: Path):
        path = _make_zip(tmp_path, REGISTER_CSV, LEGACY_PLAN_CSV)
        assert self._entries(path) == self._entries(_make_zip(tmp_path, REGISTER_CSV, PLAN_CSV))

    def test_both_old_spellings_together_read_the_same(self, tmp_path: Path):
        path = _make_zip(tmp_path, REGISTER_CSV, LEGACY_PLAN_CSV, "Budget Export - Budget.csv")
        assert self._entries(path) == self._entries(_make_zip(tmp_path, REGISTER_CSV, PLAN_CSV))

    def test_an_unknown_column_is_absent_not_zero(self, tmp_path: Path):
        """A header IGAB does not know must not silently read as $0 — that is
        the failure this class exists to stop, and it has to stay loud."""
        path = _make_zip(tmp_path, REGISTER_CSV, PLAN_CSV.replace('"Assigned"', '"Allocated"'))
        budget = self.parser.parse_zip(path)
        assert budget.budget_entries == []

    def test_a_register_only_zip_imports_but_says_so(self, tmp_path: Path):
        budget = self.parser.parse_zip(_make_zip(tmp_path, REGISTER_CSV))
        assert len(budget.transactions) == 4
        assert budget.budget_entries == []
        assert any("no monthly assignments" in e for e in budget.errors)

    def test_a_zip_with_a_plan_reports_nothing(self, tmp_path: Path):
        assert self.parser.parse_zip(_make_zip(tmp_path, REGISTER_CSV, PLAN_CSV)).errors == []


class TestADroppedRowIsReportedNotSilent:
    """The two drops that used to say nothing: a row missing its account or
    date, and a row whose date cannot be read. Same rule as the unreadable
    amount above — a dropped row must be visible in the errors, because a
    balance that is quietly short of one row reconciles with nothing."""

    def test_a_missing_date_with_money_is_reported(self):
        parser = YNABParser()
        register = SPLIT_HEADER + _reg_row(date_="", outflow="$12.00") + _reg_row()

        txns = parser.parse_register_csv(register)

        assert len(txns) == 1
        assert len(parser.errors) == 1
        assert "missing date" in parser.errors[0]

    def test_a_missing_account_with_money_is_reported(self):
        parser = YNABParser()
        register = SPLIT_HEADER + _reg_row(account="", inflow="$40.00") + _reg_row()

        txns = parser.parse_register_csv(register)

        assert len(txns) == 1
        assert len(parser.errors) == 1
        assert "missing account" in parser.errors[0]

    def test_an_unreadable_date_is_reported(self):
        parser = YNABParser()
        register = SPLIT_HEADER + _reg_row(date_="tomorrow-ish") + _reg_row()

        txns = parser.parse_register_csv(register)

        assert len(txns) == 1
        assert len(parser.errors) == 1
        assert "unreadable date" in parser.errors[0]
        assert "tomorrow-ish" in parser.errors[0]

    def test_a_fully_blank_line_is_noise_not_a_drop(self):
        """Trailing blank lines are spreadsheet artifacts; reporting each one
        would bury the real drops in noise."""
        parser = YNABParser()
        register = SPLIT_HEADER + _reg_row() + '"","","","","","","","",,,""\n'

        txns = parser.parse_register_csv(register)

        assert len(txns) == 1
        assert parser.errors == []
