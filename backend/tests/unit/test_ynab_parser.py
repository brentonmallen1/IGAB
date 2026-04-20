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


def _make_zip(register: str, plan: str | None = None) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Budget Export - Register.csv", register)
        if plan is not None:
            zf.writestr("Budget Export - Plan.csv", plan)
    buf.seek(0)
    path = Path("/tmp/test_ynab_export.zip")
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

    def test_parse_zip(self):
        path = _make_zip(REGISTER_CSV, PLAN_CSV)
        budget = self.parser.parse_zip(path)
        assert len(budget.transactions) == 4
        assert len(budget.budget_entries) == 3

    def test_parse_zip_without_plan(self):
        path = _make_zip(REGISTER_CSV)
        budget = self.parser.parse_zip(path)
        assert len(budget.transactions) == 4
        assert budget.budget_entries == []

    def test_parse_zip_missing_register_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("something.txt", "data")
        buf.seek(0)
        path = Path("/tmp/test_no_register.zip")
        path.write_bytes(buf.read())
        with pytest.raises(ValueError, match="Register CSV not found"):
            self.parser.parse_zip(path)
