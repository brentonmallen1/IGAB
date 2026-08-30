"""Writing the shape :mod:`parser` reads.

Every function here is the inverse of one in ``parser.py``, and lives beside
it for that reason: a date format written in one file and parsed in another
drifts the first time someone "fixes" one of them. The round-trip is pinned by
a test that feeds these back through the parser's own readers rather than by
comparing format strings by eye.

The format itself is not ours — it is YNAB's, documented in
``notes/YNAB-schema-and-relationships.md``, and the reason an IGAB export can
be fed straight back into ``POST /budgets/import-ynab`` with no new import
code. The three awkward parts are handled the way the parser expects them:

- **Transfers** are a payee named ``Transfer : <other account>``.
- **Splits** are flattened to one row per leg, marked ``Split (n/m) memo``.
- **Cleared** is per row, from a three-word vocabulary.
"""

import csv
import io
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

_MONTH_NAMES = (
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
)

#: The inverse of parser._CLEARED_MAP. Written out rather than derived from it,
#: because that map is many-to-one in principle and a reversal would pick an
#: arbitrary spelling; the round-trip test holds the two together.
CLEARED_LABELS: Mapping[str, str] = {
    "uncleared": "Uncleared",
    "cleared": "Cleared",
    "reconciled": "Reconciled",
}

REGISTER_COLUMNS = (
    "Account",
    "Flag",
    "Date",
    "Payee",
    "Category Group/Category",
    "Category Group",
    "Category",
    "Memo",
    "Outflow",
    "Inflow",
    "Cleared",
)

PLAN_COLUMNS = (
    "Month",
    "Category Group/Category",
    "Category Group",
    "Category",
    "Assigned",
    "Activity",
    "Available",
)

ACCOUNT_COLUMNS = (
    "Account",
    "Type",
    "Classification",
    "On Budget",
    "Closed",
    "Note",
)


def format_date(value: date) -> str:
    """``MM/DD/YYYY`` — the first format ``parser._parse_date`` tries."""
    return value.strftime("%m/%d/%Y")


def format_month(value: date) -> str:
    """``Mon YYYY`` — what ``parser._parse_month`` reads."""
    return f"{_MONTH_NAMES[value.month - 1]} {value.year}"


def format_cleared(state: str) -> str:
    return CLEARED_LABELS.get(state, "Uncleared")


def transfer_payee(account_name: str) -> str:
    """How the register names the other side of a transfer."""
    return f"Transfer : {account_name}"


def split_memo(index: int, total: int, memo: str | None) -> str:
    """``Split (n/m) memo`` — the marker ``_reassemble_splits`` reads back."""
    return f"Split ({index}/{total}) {memo or ''}".rstrip()


def group_category(group: str | None, category: str | None) -> str:
    """The combined column YNAB writes beside the split ones."""
    if not group or not category:
        return ""
    return f"{group}: {category}"


def write_csv(columns: Sequence[str], rows: Iterable[Mapping[str, str]]) -> str:
    """A CSV member, with the header the parser looks for.

    ``\\r\\n`` and quote-minimal, which is what a spreadsheet expects and what
    ``csv.DictReader`` reads back unchanged.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()
