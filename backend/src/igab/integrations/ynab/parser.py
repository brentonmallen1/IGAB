import csv
import io
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from igab.integrations.ynab.models import YNABBudget, YNABBudgetEntry, YNABTransaction

_CLEARED_MAP = {
    "Uncleared": "uncleared",
    "Cleared": "cleared",
    "Reconciled": "reconciled",
}

_MONTH_ABBREVS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _parse_currency(val: str) -> Decimal:
    cleaned = val.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(val: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_month(val: str) -> date | None:
    """Parse 'Jul 2020' → date(2020, 7, 1)."""
    parts = val.strip().split()
    if len(parts) != 2:
        return None
    month_num = _MONTH_ABBREVS.get(parts[0])
    if month_num is None:
        return None
    try:
        year = int(parts[1])
    except ValueError:
        return None
    return date(year, month_num, 1)


class YNABParser:
    def parse_zip(self, path: Path) -> YNABBudget:
        with zipfile.ZipFile(path) as zf:
            register_content: str | None = None
            plan_content: str | None = None
            for name in zf.namelist():
                lower = name.lower()
                if lower.endswith("- register.csv"):
                    with zf.open(name) as f:
                        register_content = f.read().decode("utf-8-sig")
                elif lower.endswith("- plan.csv"):
                    with zf.open(name) as f:
                        plan_content = f.read().decode("utf-8-sig")

        if register_content is None:
            raise ValueError(
                "Register CSV not found in ZIP (expected a file ending in '- Register.csv')"
            )

        transactions = self.parse_register_csv(register_content)
        budget_entries = self.parse_plan_csv(plan_content) if plan_content else []
        return YNABBudget(transactions=transactions, budget_entries=budget_entries)

    def parse_register_csv(self, content: str) -> list[YNABTransaction]:
        reader = csv.DictReader(io.StringIO(content))
        transactions: list[YNABTransaction] = []
        for row in reader:
            account = row.get("Account", "").strip()
            payee = row.get("Payee", "").strip()
            raw_date = row.get("Date", "").strip()
            category_group = row.get("Category Group", "").strip() or None
            category = row.get("Category", "").strip() or None
            memo = row.get("Memo", "").strip() or None
            raw_outflow = row.get("Outflow", "").strip()
            raw_inflow = row.get("Inflow", "").strip()
            cleared_raw = row.get("Cleared", "Uncleared").strip()

            if not account or not raw_date:
                continue

            txn_date = _parse_date(raw_date)
            if txn_date is None:
                continue

            outflow = _parse_currency(raw_outflow) if raw_outflow else Decimal("0")
            inflow = _parse_currency(raw_inflow) if raw_inflow else Decimal("0")
            amount = inflow - outflow

            cleared = _CLEARED_MAP.get(cleared_raw, "uncleared")

            transactions.append(
                YNABTransaction(
                    account_name=account,
                    date=txn_date,
                    payee=payee,
                    category_group=category_group,
                    category=category,
                    memo=memo,
                    amount=amount,
                    cleared=cleared,
                )
            )

        return transactions

    def parse_plan_csv(self, content: str) -> list[YNABBudgetEntry]:
        reader = csv.DictReader(io.StringIO(content))
        entries: list[YNABBudgetEntry] = []
        for row in reader:
            raw_month = row.get("Month", "").strip()
            category_group = row.get("Category Group", "").strip()
            category = row.get("Category", "").strip()
            raw_assigned = row.get("Assigned", "").strip()

            if not raw_month or not category_group or not category:
                continue

            month = _parse_month(raw_month)
            if month is None:
                continue

            assigned = _parse_currency(raw_assigned) if raw_assigned else Decimal("0")
            if assigned == 0:
                continue

            entries.append(
                YNABBudgetEntry(
                    month=month,
                    category_group=category_group,
                    category=category,
                    assigned=assigned,
                )
            )

        return entries
