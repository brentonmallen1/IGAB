import csv
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from igab.domain.money import parse_csv_amount
from igab.integrations.ynab.models import (
    YNABBudget,
    YNABBudgetEntry,
    YNABPlanRow,
    YNABSplitLeg,
    YNABTransaction,
)

_CLEARED_MAP = {
    "Uncleared": "uncleared",
    "Cleared": "cleared",
    "Reconciled": "reconciled",
}

# YNAB register exports flatten split transactions: each leg becomes its own
# CSV row whose memo is prefixed "Split (i/n) <leg memo>".
_SPLIT_MEMO_RE = re.compile(r"^Split \((\d+)/(\d+)\)\s*(.*)$")

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
    """Parse a YNAB money string, or raise.

    Routed through `parse_csv_amount`, the documented single entry point for
    turning imported text into money — the CSV importer has always used it.
    This used to hand back `Decimal("0")` on anything it could not read, which
    imported the transaction anyway with zero money: the row count looked
    right and the balance was quietly wrong. `domain/money.py` exists to stop
    exactly that ("a single NaN poisons every SUM the app runs"), and this
    path went around it — no `validate_money`, so Infinity, NaN and 10^14
    magnitudes all passed, and "1,50" became 150 where the shared parser
    rejects it as an ambiguous European decimal.

    Raises ValueError; callers skip the row and record why.
    """
    return parse_csv_amount(val)


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


def _reassemble_splits(
    rows: list[tuple[YNABTransaction, tuple[int, int, str] | None]],
) -> list[YNABTransaction]:
    """Regroup flattened YNAB split legs into single transactions.

    A run is grouped only when it is complete and unambiguous: markers
    (1/n)…(n/n) on consecutive rows sharing account, date, payee, and cleared
    state. Anything irregular — interrupted, truncated, out of order, or a
    lone memo that merely resembles a marker — falls back to flat rows, so a
    malformed export degrades to today's behavior instead of losing data.

    The grouped transaction carries the sum of the legs (the amount the bank
    statement shows) with no category; per-leg category/amount/memo live in
    `splits`, marker prefix stripped.
    """
    out: list[YNABTransaction] = []
    i = 0
    while i < len(rows):
        txn, marker = rows[i]
        if marker is None or marker[0] != 1 or marker[1] < 2:
            out.append(txn)
            i += 1
            continue

        n = marker[1]
        run = rows[i : i + n]
        is_complete_run = len(run) == n and all(
            m is not None
            and m[0] == pos + 1
            and m[1] == n
            and t.account_name == txn.account_name
            and t.date == txn.date
            and t.payee == txn.payee
            and t.cleared == txn.cleared
            for pos, (t, m) in enumerate(run)
        )
        if not is_complete_run:
            out.append(txn)
            i += 1
            continue

        legs = [
            YNABSplitLeg(
                category_group=t.category_group,
                category=t.category,
                memo=(m[2] or None) if m else None,
                amount=t.amount,
            )
            for t, m in run
        ]
        out.append(
            YNABTransaction(
                account_name=txn.account_name,
                date=txn.date,
                payee=txn.payee,
                category_group=None,
                category=None,
                memo=None,
                amount=sum((leg.amount for leg in legs), Decimal("0")),
                cleared=txn.cleared,
                splits=legs,
            )
        )
        i += n

    return out


class YNABParser:
    def __init__(self) -> None:
        #: Rows dropped because their amount could not be read. Surfaced to the
        #: user through ImportResult.errors rather than swallowed.
        self.errors: list[str] = []

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
        plan_rows = self.parse_plan_rows(plan_content) if plan_content else []
        return YNABBudget(
            transactions=transactions,
            budget_entries=_assigned_entries(plan_rows),
            plan_rows=plan_rows,
            errors=list(self.errors),
        )

    def parse_register_csv(self, content: str) -> list[YNABTransaction]:
        reader = csv.DictReader(io.StringIO(content))
        rows: list[tuple[YNABTransaction, tuple[int, int, str] | None]] = []
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

            try:
                outflow = _parse_currency(raw_outflow) if raw_outflow else Decimal("0")
                inflow = _parse_currency(raw_inflow) if raw_inflow else Decimal("0")
            except ValueError as e:
                # Skipping loses one row and says so. Importing a zero loses
                # the money and says nothing, which is worse: the count still
                # reconciles and only the balance is wrong.
                self.errors.append(f"{account} {raw_date}: {e}")
                continue
            amount = inflow - outflow

            cleared = _CLEARED_MAP.get(cleared_raw, "uncleared")

            marker: tuple[int, int, str] | None = None
            if memo:
                m = _SPLIT_MEMO_RE.match(memo)
                if m:
                    marker = (int(m.group(1)), int(m.group(2)), m.group(3).strip())

            rows.append(
                (
                    YNABTransaction(
                        account_name=account,
                        date=txn_date,
                        payee=payee,
                        category_group=category_group,
                        category=category,
                        memo=memo,
                        amount=amount,
                        cleared=cleared,
                    ),
                    marker,
                )
            )

        return _reassemble_splits(rows)

    def parse_plan_csv(self, content: str) -> list[YNABBudgetEntry]:
        """The assignments to import: every plan row with a non-zero Assigned."""
        return _assigned_entries(self.parse_plan_rows(content))

    def parse_plan_rows(self, content: str) -> list[YNABPlanRow]:
        """Every Plan.csv row, in file order.

        The order is load-bearing: YNAB writes the plan in the arrangement
        the user sees on screen, so it is how an import learns the layout.
        A row whose Assigned cannot be read is dropped and reported, as
        before; an unreadable Activity or Available only blanks that figure.
        """
        reader = csv.DictReader(io.StringIO(content))
        rows: list[YNABPlanRow] = []
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

            try:
                assigned = _parse_currency(raw_assigned) if raw_assigned else Decimal("0")
            except ValueError as e:
                self.errors.append(f"{category_group}/{category} {raw_month}: {e}")
                continue

            rows.append(
                YNABPlanRow(
                    month=month,
                    category_group=category_group,
                    category=category,
                    assigned=assigned,
                    activity=_optional_currency(row.get("Activity", "")),
                    available=_optional_currency(row.get("Available", "")),
                )
            )

        return rows


def _optional_currency(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return _parse_currency(raw)
    except ValueError:
        return None


def _assigned_entries(rows: list[YNABPlanRow]) -> list[YNABBudgetEntry]:
    return [
        YNABBudgetEntry(
            month=row.month,
            category_group=row.category_group,
            category=row.category,
            assigned=row.assigned,
        )
        for row in rows
        if row.assigned != 0
    ]
