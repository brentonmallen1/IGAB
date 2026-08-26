"""What changes on an existing row when the bank feed has a record for it.

Two places used to answer this — the sync's identity path (a row found by
its bank id) and its auto-match path (a row found by amount and date) — and
they had drifted: one upgraded only `pending` rows to cleared, so a
hand-typed row that was linked while the bank record was still an auth hold
stayed `uncleared` forever once it posted; one cleared a split parent and
left its children pending; one blanked `import_description` whenever the
feed omitted it. This module is the single answer, and
`TransactionService.apply_bank_posting` is its single writer.

The rule, by what the row is:

- **Provenance always**: the bank's amount and payee string, its
  description, source and id, and — once posted — its posted date. These sit
  beside the user's values (`bank_amount` beside `amount`) and are what the
  bank-record tooltip shows.
- **A pending feed record** changes nothing else. A hold is provisional.
- **A bank-created `pending` row** (the sync wrote it) takes the bank's
  posted values wholesale: amount, date, cleared. Holds routinely change at
  posting (tips, gas) and the user never typed that amount. The prior date
  and amount are kept once as `entered_date` / `entered_amount`.
- **A user-entered row** (`uncleared` or `cleared`) clears when the bank
  posts the same amount, keeping the user's ledger date — budget months
  follow it. When the bank posts a *different* amount, the answer is
  `Review`: the change is never applied silently. The sync queues the posted
  record for review and only an accepted review (`confirmed=True`) applies
  the bank's amount, again keeping the prior one as `entered_amount`. A
  split parent or a transfer leg stays `Review` even then — its legs or its
  partner must be adjusted first, and the message says so.
- **A reconciled row** takes provenance only. What reconciliation locks is
  defined once, in `domain.reconciliation`, and stripped here.

Keys equal to the row's current value are dropped, so a second sync of a
posted record writes nothing.
"""

from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal
from typing import Any

from igab.domain.reconciliation import RECONCILED_LOCKED_FIELDS


@dataclass(frozen=True)
class RowState:
    """The slice of a transaction the posting rule reads. Frozen and plain so
    the rule is testable without an ORM row."""

    cleared: str
    amount: Decimal
    date: _date
    entered_date: _date | None
    entered_amount: Decimal | None
    bank_posted_date: _date | None
    bank_amount: Decimal | None
    bank_payee: str | None
    import_description: str | None
    sync_id: str | None
    sync_source: str | None
    has_sync_source: bool
    is_split: bool
    is_transfer_leg: bool

    @classmethod
    def from_transaction(cls, txn: Any) -> "RowState":
        return cls(
            cleared=txn.cleared,
            amount=txn.amount,
            date=txn.date,
            entered_date=txn.entered_date,
            entered_amount=txn.entered_amount,
            bank_posted_date=txn.bank_posted_date,
            bank_amount=txn.bank_amount,
            bank_payee=txn.bank_payee,
            import_description=txn.import_description,
            sync_id=txn.sync_id,
            sync_source=txn.sync_source,
            has_sync_source=bool(txn.has_sync_source),
            is_split=bool(txn.is_split),
            is_transfer_leg=txn.transfer_id is not None,
        )


@dataclass(frozen=True)
class FeedRecord:
    """One bank record as the feed reports it. `date` is the posted date when
    posted, else the transacted date."""

    amount: Decimal
    date: _date
    posted: bool
    payee: str | None
    description: str | None
    sync_id: str | None
    source: str = "simplefin"

    @classmethod
    def from_transaction(cls, txn: Any) -> "FeedRecord":
        """A bank-sourced row standing in for the feed — the loser of a merge
        carries the bank's values the survivor should take."""
        return cls(
            amount=txn.bank_amount if txn.bank_amount is not None else txn.amount,
            date=txn.bank_posted_date or txn.date,
            posted=txn.cleared != "pending",
            payee=txn.bank_payee,
            description=txn.import_description,
            sync_id=txn.sync_id,
            source=txn.sync_source or "simplefin",
        )


@dataclass(frozen=True)
class Apply:
    """Write these — possibly nothing."""

    updates: dict[str, Any]


@dataclass(frozen=True)
class Review:
    """The bank posted a different amount than the user entered. Not
    applied: the caller queues it for the user to confirm, or refuses."""

    reason: str


Outcome = Apply | Review


def _refuse_structured(row: RowState, feed: FeedRecord) -> Review:
    kind = "split" if row.is_split else "transfer"
    return Review(
        f"The bank posted {feed.amount} but this {kind} is {row.amount}; "
        f"adjust the {'lines' if row.is_split else 'transfer'} to match, then accept"
    )


def posting_updates(row: RowState, feed: FeedRecord, *, confirmed: bool) -> Outcome:
    """What changes on `row` given `feed`. `confirmed` is True only on an
    accepted review — the one path that may apply a changed amount to a
    user-entered row."""
    updates: dict[str, Any] = {
        "sync_source": feed.source,
        "has_sync_source": True,
        "bank_amount": feed.amount,
    }
    if feed.sync_id is not None:
        updates["sync_id"] = feed.sync_id
    # Only when the feed has one: an absent value must not blank a recorded one.
    if feed.payee:
        updates["bank_payee"] = feed.payee
    if feed.description:
        updates["import_description"] = feed.description

    if feed.posted:
        updates["bank_posted_date"] = feed.date
        amount_differs = feed.amount != row.amount

        if row.cleared == "pending":
            updates["cleared"] = "cleared"
            if amount_differs:
                updates["amount"] = feed.amount
                if row.entered_amount is None:
                    updates["entered_amount"] = row.amount
            if feed.date != row.date:
                updates["date"] = feed.date
                if row.entered_date is None:
                    updates["entered_date"] = row.date

        elif row.cleared in ("uncleared", "cleared"):
            if amount_differs:
                if not confirmed:
                    return Review(
                        f"The bank posted {feed.amount}; this transaction was entered as "
                        f"{row.amount}"
                    )
                if row.is_split or row.is_transfer_leg:
                    return _refuse_structured(row, feed)
                updates["amount"] = feed.amount
                if row.entered_amount is None:
                    updates["entered_amount"] = row.amount
            if row.cleared == "uncleared":
                updates["cleared"] = "cleared"

    if row.cleared == "reconciled":
        # Belt and braces: nothing above writes these for a reconciled row,
        # but the lock has one home and this is where it is honoured.
        for field in RECONCILED_LOCKED_FIELDS:
            updates.pop(field, None)

    current = {
        "sync_source": row.sync_source,
        "has_sync_source": row.has_sync_source,
        "bank_amount": row.bank_amount,
        "sync_id": row.sync_id,
        "bank_payee": row.bank_payee,
        "import_description": row.import_description,
        "bank_posted_date": row.bank_posted_date,
        "cleared": row.cleared,
        "amount": row.amount,
        "date": row.date,
        "entered_amount": row.entered_amount,
        "entered_date": row.entered_date,
    }
    return Apply({k: v for k, v in updates.items() if current.get(k) != v})
