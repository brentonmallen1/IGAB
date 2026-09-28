"""What a receipt's read may write onto a row that already exists — pure.

Two paths put a read on an existing row, and they used to spell the rule
twice and disagree about it:

- **placing** (`receipt_placement.attach_to`): the receipt lands on the
  bank's own row, unasked. It fills only what the row is missing.
- **reprocessing** (`ai_worker._apply_draft_to_existing`): a person asked for
  a fresh read of a receipt that already has a row. It refreshes what it
  read. It used to refuse any approved or cleared row outright, and it
  blanked the payee or category whenever the new read could not resolve one.

What both obey, and what this module says once:

- **Bank facts stay the bank's.** A row's date and amount move only when the
  row is the scan's own (`created_via == "ai_receipt"`) and nobody has
  confirmed it yet: not approved, not cleared by anything. On a bank row
  (`attach_to` matched it) or a confirmed one, the receipt refreshes the
  payee, the category and the memo, and nothing else.
- **A read never blanks.** A value the read could not resolve leaves the
  row's own standing. The one thing it clears is the failure stub's
  placeholder memo, which was never the user's and is false once a read
  works.
- **A split's category is its lines'**, and its amount is their sum, so a
  read sends neither to a split parent.
- **A linked transfer's payee is its destination** and its category follows
  the pair rule, so a read sends neither to a transfer leg.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

#: The memo on the $0 row a failed scan leaves so its image stays reachable.
FAILURE_STUB_MEMO = "Receipt scan failed — enter details from the image"

#: The two facts a bank vouches for.
BANK_FACTS = frozenset({"date", "amount"})


@dataclass(frozen=True)
class ExistingRow:
    #: The scan made this row (`created_via == "ai_receipt"`).
    own: bool
    #: Approved, or cleared by anything (cleared, reconciled, pending).
    confirmed: bool
    is_split: bool
    is_transfer: bool
    has_payee: bool
    has_category: bool
    memo: str | None


@dataclass(frozen=True)
class ReceiptRead:
    """The read, resolved against this budget. None means unresolved."""

    date: date
    amount: Decimal
    payee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    memo: str | None


def _has_memo(row: ExistingRow) -> bool:
    return bool(row.memo and row.memo.strip()) and row.memo != FAILURE_STUB_MEMO


def writable_fields(row: ExistingRow, *, refresh: bool) -> frozenset[str]:
    """The fields a read may write onto `row`.

    `refresh` is a person asking for a fresh read: it overwrites what it
    reads. Without it (placing a receipt on a row) only what the row is
    missing is filled."""
    fields: set[str] = set()
    if refresh and row.own and not row.confirmed:
        fields |= BANK_FACTS
        if row.is_split:
            fields.discard("amount")
    if not row.is_transfer and (refresh or not row.has_payee):
        fields.add("payee_id")
    if not row.is_transfer and not row.is_split and (refresh or not row.has_category):
        fields.add("category_id")
    if refresh or not _has_memo(row):
        fields.add("memo")
    return frozenset(fields)


def receipt_changes(row: ExistingRow, read: ReceiptRead, *, refresh: bool) -> dict[str, Any]:
    """The TransactionUpdate fields a read sets on `row` — only fields it may
    write and has a value for. Empty means the row is left alone."""
    fields = writable_fields(row, refresh=refresh)
    changes: dict[str, Any] = {}
    for field in ("date", "amount", "payee_id", "category_id"):
        value = getattr(read, field)
        if field in fields and value is not None:
            changes[field] = value
    memo = read.memo.strip() if read.memo else None
    if "memo" in fields and memo:
        changes["memo"] = memo
    elif row.memo == FAILURE_STUB_MEMO:
        changes["memo"] = None
    return changes
