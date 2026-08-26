"""Which of two rows survives a merge, and whether the merge may happen.

A merge asserts "these two rows are the same real-world transaction" and
keeps one. Two paths do it — the user's explicit merge and the bank-sync
review queue's accept — and each carried its own precedence for the keeper
role. They agreed on the first rule (a reconciled row always survives) and
disagreed on everything after it. This module is the one answer; the
service applies it and phrases the refusals.

Precedence for the survivor:

1. **Reconciled.** The statement vouched for it; it never goes.
2. **Structured** — a split parent or a transfer leg. Soft-deleting a split
   parent orphans its live lines (they keep feeding category activity,
   double-counting spending); soft-deleting a transfer leg strands its
   partner and breaks zero-sum.
3. **The row the caller asked for**, when there is one.
4. **The row the user entered** — the one without a bank source. Its payee,
   category and memo are the user's choices; the bank row's are descriptors.
5. **The older row.**

A merge is refused when the loser would be structured (the pair cannot be
collapsed without losing something), when both are reconciled, when a split
line is involved, when the rows sit in different accounts, or when they
carry different bank identities.

Pure: takes plain slices of the two rows, returns the verdict. Amounts are
not judged here — whether the survivor may take the loser's amount is the
bank-posting rule's question (domain.bank_posting), asked by the service.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MergeSide:
    id: uuid.UUID
    cleared: str
    is_split: bool
    transfer_id: uuid.UUID | None
    parent_transaction_id: uuid.UUID | None
    account_id: uuid.UUID
    sync_id: str | None
    sync_source: str | None
    created_at: datetime | None

    @classmethod
    def from_transaction(cls, txn: Any) -> "MergeSide":
        return cls(
            id=txn.id,
            cleared=txn.cleared,
            is_split=bool(txn.is_split),
            transfer_id=txn.transfer_id,
            parent_transaction_id=txn.parent_transaction_id,
            account_id=txn.account_id,
            sync_id=txn.sync_id,
            sync_source=txn.sync_source,
            created_at=txn.created_at,
        )

    @property
    def reconciled(self) -> bool:
        return self.cleared == "reconciled"

    @property
    def structured(self) -> bool:
        return self.is_split or self.transfer_id is not None

    @property
    def bank_sourced(self) -> bool:
        """An id-less bank feed row has sync_source but no sync_id — it still
        carries bank identity and provenance."""
        return bool(self.sync_id or self.sync_source)


def choose_survivor(
    a: MergeSide, b: MergeSide, requested: uuid.UUID | None
) -> tuple[MergeSide, MergeSide]:
    """(survivor, deleted) by the precedence above. Never raises — a choice
    the rules forbid is reported by `survivor_violation`."""
    if a.reconciled != b.reconciled:
        return (a, b) if a.reconciled else (b, a)
    if a.structured != b.structured:
        return (a, b) if a.structured else (b, a)
    if requested is not None and requested in (a.id, b.id):
        return (a, b) if a.id == requested else (b, a)
    if a.bank_sourced != b.bank_sourced:
        return (b, a) if a.bank_sourced else (a, b)
    if a.created_at is not None and b.created_at is not None and b.created_at < a.created_at:
        return (b, a)
    return (a, b)


def survivor_violation(
    survivor: MergeSide, deleted: MergeSide, requested: uuid.UUID | None
) -> str | None:
    """Why this pair cannot be merged with this survivor, or None."""
    if survivor.id == deleted.id:
        return "A transaction cannot be merged with itself"
    if survivor.reconciled and deleted.reconciled:
        return "Cannot merge two reconciled transactions; unreconcile one first"
    if survivor.parent_transaction_id or deleted.parent_transaction_id:
        return "Cannot merge a split line; act on its parent transaction instead"
    if requested is not None and requested not in (survivor.id, deleted.id):
        return "survivor_id must be one of the transaction_ids"
    if requested is not None and requested != survivor.id:
        if survivor.reconciled:
            return "The reconciled transaction must be kept as the survivor"
        return "A split transaction or transfer must be kept as the survivor"
    if deleted.is_split:
        return (
            "Cannot merge away a split transaction; unreconcile the other row "
            "so the split can be kept, or reject the match"
        )
    if deleted.transfer_id is not None:
        return "Cannot merge away a transfer; reject the match or delete the transfer instead"
    if survivor.account_id != deleted.account_id:
        return "Transactions must be in the same account"
    if survivor.sync_id and deleted.sync_id and survivor.sync_id != deleted.sync_id:
        return "Both transactions are linked to different bank transactions"
    return None
