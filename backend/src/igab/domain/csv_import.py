"""Reading one account's own CSV export.

The shape of the thing: a bank hands you a file of that account's
transactions, you point it at that account, and the overlap with last
month's export is skipped. So the interesting work is not the insert — it is
saying, before anything lands, what the file was understood to contain.

Pure on purpose. Preview and commit must reach the same answer about the same
file, and the only way to guarantee that is for both to call this. The
endpoint keeps the I/O: reading the upload, resolving payees, writing rows.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from igab.domain.money import parse_csv_amount

#: Tried in order against the first column that parses cleanly. Day-first and
#: month-first both appear, and no file says which it is — so the order here
#: is a guess that the preview shows the user before anything is written.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
)

#: Header names seen in the wild, per field. Matched case- and
#: punctuation-insensitively, longest first so "transaction date" wins over
#: "date" where a file has both.
HEADER_HINTS: dict[str, tuple[str, ...]] = {
    "date": ("transaction date", "posted date", "post date", "date posted", "date"),
    "payee": ("description", "merchant", "name", "payee", "details", "narrative"),
    "amount": ("amount", "value"),
    "debit": ("debit", "withdrawal", "money out", "paid out"),
    "credit": ("credit", "deposit", "money in", "paid in"),
    "memo": ("memo", "notes", "note", "reference", "extra details"),
    "category": ("category",),
}

FIELDS = tuple(HEADER_HINTS)


def normalize_header(header: str) -> str:
    """Lowercase, collapse punctuation and whitespace. `"Posted Date "` and
    `"posted_date"` are the same column asking twice."""
    return re.sub(r"[^a-z0-9]+", " ", header.strip().lower()).strip()


def suggest_mapping(headers: Sequence[str]) -> dict[str, str]:
    """A first guess at which column is which, for the mapping step to show.

    Only exact matches against the hints — a fuzzy guess that is wrong is
    worse than no guess, because the user skims a filled-in form and clicks
    on. Anything unrecognised is simply left for them to say.
    """
    normalized = {normalize_header(h): h for h in headers}
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for fieldname, hints in HEADER_HINTS.items():
        for hint in hints:
            column = normalized.get(hint)
            if column is not None and column not in taken:
                mapping[fieldname] = column
                taken.add(column)
                break
    return mapping


def detect_date_format(values: Sequence[str]) -> str | None:
    """The first format that reads every non-empty value.

    Every value, not most: a format that parses 90% of a file is a format that
    is wrong about the other 10%, and those rows would land on invented dates.
    """
    sample = [v.strip() for v in values if v and v.strip()]
    if not sample:
        return None
    for fmt in DATE_FORMATS:
        try:
            for value in sample:
                datetime.strptime(value, fmt)
        except ValueError:
            continue
        return fmt
    return None


@dataclass(frozen=True)
class ParsedRow:
    line: int  # 1-based row number in the file, for talking about a problem
    date: date
    amount: Decimal
    payee: str
    memo: str | None
    category: str | None


@dataclass(frozen=True)
class SkippedRow:
    line: int
    reason: str


@dataclass
class ParsedCsv:
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[SkippedRow] = field(default_factory=list)
    date_format: str | None = None

    @property
    def total(self) -> int:
        return len(self.rows) + len(self.skipped)


def _amount_of(record: Mapping[str, str], mapping: Mapping[str, str]) -> Decimal:
    """The row's signed amount.

    Two shapes. One `amount` column carries its own sign. Separate
    debit/credit columns do not: the sign is which column the figure is in,
    and a debit is money leaving. A file with both columns filled on one row
    is contradictory, and saying so beats picking one.
    """
    if "amount" in mapping:
        return parse_csv_amount(record.get(mapping["amount"], ""))

    debit = (record.get(mapping.get("debit", ""), "") or "").strip()
    credit = (record.get(mapping.get("credit", ""), "") or "").strip()
    if debit and credit:
        raise ValueError("both a debit and a credit on one row")
    if debit:
        return -abs(parse_csv_amount(debit))
    if credit:
        return abs(parse_csv_amount(credit))
    raise ValueError("empty amount")


def parse_csv(
    records: Sequence[Mapping[str, str]],
    mapping: Mapping[str, str],
    *,
    date_format: str | None = None,
) -> ParsedCsv:
    """Read every row, keeping the ones that make sense and saying why the
    rest did not.

    A row is never dropped silently. `skipped` carries a line number and a
    reason for each, because "128 rows, 3 skipped" is only useful if you can
    find out which three.
    """
    if "date" not in mapping:
        raise ValueError("No date column chosen")
    if not ({"amount", "debit", "credit"} & set(mapping)):
        raise ValueError("No amount column chosen")

    date_column = mapping["date"]
    fmt = date_format or detect_date_format([r.get(date_column, "") for r in records])
    out = ParsedCsv(date_format=fmt)
    if fmt is None:
        out.skipped = [SkippedRow(i + 2, "unreadable date") for i in range(len(records))]
        return out

    for index, record in enumerate(records):
        # +2: a spreadsheet's row 1 is the header, and its rows are 1-based.
        line = index + 2
        raw_date = (record.get(date_column, "") or "").strip()
        if not raw_date:
            out.skipped.append(SkippedRow(line, "no date"))
            continue
        try:
            parsed_date = datetime.strptime(raw_date, fmt).date()
        except ValueError:
            out.skipped.append(SkippedRow(line, f"date {raw_date!r} is not {fmt}"))
            continue

        try:
            amount = _amount_of(record, mapping)
        except ValueError as exc:
            out.skipped.append(SkippedRow(line, str(exc)))
            continue

        def value(fieldname: str) -> str | None:
            column = mapping.get(fieldname)
            if not column:
                return None
            return (record.get(column, "") or "").strip() or None

        out.rows.append(
            ParsedRow(
                line=line,
                date=parsed_date,
                amount=amount,
                payee=value("payee") or "",
                memo=value("memo"),
                category=value("category"),
            )
        )
    return out
