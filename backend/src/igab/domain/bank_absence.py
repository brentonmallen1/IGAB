"""Rows the bank stopped reporting: what a sync did about each, and whether
the person still needs to hear about it.

A sync judges a linked row by its absence from the feed — only inside the
days the feed covered (`domain.sync_window.judged_from`), and only for an
account whose feed carried rows at all. What it does depends on whose row it
is and what the bank had said about it:

- **A pending hold the sync wrote** (`HOLD`) is removed. It was only ever the
  bank's provisional word, it is in no balance, and leaving it means a hold
  that never cleared sits in the register for good. Removed, not lost: the
  run records it, and the person can restore it with whatever they filed it
  under.
- **A person's row linked to a hold** (`LINKED_TO_HOLD`) is kept and unlinked.
  The person typed it; a dropped hold says nothing about whether they spent
  the money. It can never clear through that link again, so it goes back to
  matchable — and the person is told, because a hold that never cleared is
  exactly the row they typed in for nothing.
- **A posted row** (`POSTED`) is kept as it is, link and all. It may be
  reconciled, and a bank that omits a settled row for an hour must not cost
  one; if the id comes back, the row is still the one that carries it.

Every such row is recorded on the run (`SyncRun.no_longer_reported`), so the
toast and the sync log can say so and the accounts page can list it. The
listing (`is_open`) is decided here, on the server, because only the server
knows what it removed.

Pure: entries and row states in, verdicts out.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

#: How long a row the bank stopped reporting stays listed. Matches the sync
#: log's default retention (`sync_log_retention_days`), which bounds it anyway:
#: the runs that record these rows are purged after it.
LOOKBACK_DAYS = 30

# What kind of row it was when the bank stopped reporting it.
HOLD = "pending_hold"
LINKED_TO_HOLD = "linked_to_hold"
POSTED = "posted"

# What the run did.
REMOVED = "removed"
KEPT = "kept"
#: A posted row listed by an earlier run whose id the feed carries again —
#: the bank's omission was momentary. Written so the listing can drop the row
#: without re-reading every feed since.
REPORTED_AGAIN = "reported_again"


@dataclass(frozen=True)
class Absence:
    """One row a run found missing from the feed, and what it did."""

    transaction_id: uuid.UUID
    account_id: uuid.UUID
    date: date
    payee: str | None
    amount: Decimal
    #: The bank id the row carried when the run judged it. A removed hold and
    #: an unlinked row give theirs up, so this is the only place it survives.
    sync_id: str | None
    kind: str
    action: str

    def to_record(self) -> dict:
        return {
            "transaction_id": str(self.transaction_id),
            "account_id": str(self.account_id),
            "date": self.date.isoformat(),
            "payee": self.payee,
            "amount": str(self.amount),
            "sync_id": self.sync_id,
            "kind": self.kind,
            "action": self.action,
        }

    @classmethod
    def from_record(cls, record: dict) -> "Absence":
        return cls(
            transaction_id=uuid.UUID(str(record["transaction_id"])),
            account_id=uuid.UUID(str(record["account_id"])),
            date=date.fromisoformat(str(record["date"])),
            payee=record.get("payee"),
            amount=Decimal(str(record["amount"])),
            sync_id=record.get("sync_id"),
            kind=str(record["kind"]),
            action=str(record["action"]),
        )


def action_for(kind: str) -> str:
    """What a sync does to a row of this kind the bank no longer reports."""
    return REMOVED if kind == HOLD else KEPT


def latest_by_row(entries: Iterable[Absence]) -> dict[uuid.UUID, Absence]:
    """The newest entry per row, from entries given oldest first."""
    latest: dict[uuid.UUID, Absence] = {}
    for entry in entries:
        latest[entry.transaction_id] = entry
    return latest


def unreported_postings(entries: Iterable[Absence]) -> set[uuid.UUID]:
    """Posted rows an earlier run listed as missing and no run has seen since.

    A posted row stays missing run after run while the window covers it, and
    it is news once: a run records a posted row only when it is not already
    in this set, and records `REPORTED_AGAIN` for one in it whose id is back.
    """
    return {
        txn_id
        for txn_id, entry in latest_by_row(entries).items()
        if entry.kind == POSTED and entry.action == KEPT
    }


@dataclass(frozen=True)
class RowNow:
    """The listed row as it stands, for `is_open`."""

    is_deleted: bool
    sync_id: str | None
    cleared: str
    #: For a removed hold: the system delete has been taken back (restored
    #: here, or by undoing the run). Such a row is the person's again even if
    #: they later delete it themselves.
    removal_undone: bool = False


def is_open(entry: Absence, row: RowNow | None, live_ids: set[str]) -> bool:
    """Whether the person still needs to hear about this row.

    `entry` is the newest entry for the row; `live_ids` the bank ids live rows
    on its account carry now. Closed when:

    - the row is gone outright (a run's undo of an import, a hard delete);
    - a removed hold was restored, or the bank reports its id again — a hold
      that was only briefly missing came back as a fresh row;
    - a kept row was deleted, or has been linked to a bank record since (a
      posting matched it: it is not missing any more);
    - a posted row adopted another id, or was reported again.
    """
    if row is None or entry.action == REPORTED_AGAIN:
        return False
    if entry.action == REMOVED:
        if row.removal_undone or not row.is_deleted:
            return False
        return entry.sync_id is None or entry.sync_id not in live_ids
    if row.is_deleted:
        return False
    if entry.kind == POSTED:
        return row.sync_id == entry.sync_id
    return row.sync_id is None


#: What the listing offers on a row. Restore for a hold the sync removed;
#: Delete for a kept row the person can remove the ordinary way. A reconciled
#: row offers neither — deleting it is refused until it is unreconciled, and
#: that is a decision for the register, not a one-click fix.
RESTORE = "restore"
DELETE = "delete"


def offered_action(entry: Absence, row: RowNow) -> str | None:
    if entry.action == REMOVED:
        return RESTORE
    if row.cleared == "reconciled":
        return None
    return DELETE
