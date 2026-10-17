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

A reconciled plain row that outranks a split takes the split in: the lines
move onto the reconciled row, which becomes the split. That is the bank row
meeting the receipt someone itemised before the statement arrived — refusing
it left the user one choice, unreconcile a row the statement vouched for.

A transfer leg that loses is not refused either; its transfer goes with the
merge (`plan_merge`). Let L be the leg merged away and P its partner:

- **The survivor is not a leg.** It takes the transfer over: P links to it,
  and it takes the transfer payee. That is a reconciled bank row meeting the
  card payment someone typed before the statement arrived.
- **The survivor is a leg too**, with partner Q. Then P and Q are the same
  duplicate seen from the other account, and they are merged by the same
  precedence in the same change. Only when they are a pair the rules would
  merge on their own — same account, same amount, not both reconciled, not
  two different bank records — otherwise the merge is refused and says the
  other account's two legs don't match. This is what a sync builds when it
  pairs its own two bank rows into a transfer while the checking-side row is
  still queued as a duplicate of the payment someone typed: two transfers for
  one payment, and the review queue's accept used to refuse it with no way
  out.

A merge is refused when the loser is a split and the survivor already has a
structure, when a split would have to take over a transfer, when both are
reconciled, when a split line is involved, when the rows sit in different
accounts, or when they carry different bank identities.

Pure: takes plain slices of the rows, returns the verdict. Amounts are judged
only where nothing else would: the other account's two legs must agree. The
two rows being merged are the bank-posting rule's question
(domain.bank_posting), asked by the service.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class MergeSide:
    id: uuid.UUID
    cleared: str
    is_split: bool
    transfer_id: uuid.UUID | None
    parent_transaction_id: uuid.UUID | None
    account_id: uuid.UUID
    amount: Decimal
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
            amount=txn.amount,
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
    """Why this pair cannot be merged with this survivor, or None.

    The rules the two rows answer on their own. What becomes of a deleted
    leg's transfer needs its partner, and is `plan_merge`'s question."""
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
    if deleted.is_split and survivor.structured:
        return (
            "Cannot merge a split into another split or a transfer; "
            "delete the one you don't want instead"
        )
    if survivor.account_id != deleted.account_id:
        return "Transactions must be in the same account"
    if survivor.sync_id and deleted.sync_id and survivor.sync_id != deleted.sync_id:
        return "Both transactions are linked to different bank transactions"
    return None


@dataclass(frozen=True)
class MergePlan:
    """Everything one merge does, decided before anything is written.

    `survivor` keeps, `deleted` goes. When `deleted` is a transfer leg its
    transfer goes with the merge, in exactly one of two ways:

    - `adopted_partner`: the survivor was not a leg, and takes this row (the
      deleted leg's partner) as its own.
    - `partner_merge`: the survivor was a leg too, and the other account's two
      legs are merged by the same rules — a plan of its own, never nested
      further.
    """

    survivor: MergeSide
    deleted: MergeSide
    adopted_partner: MergeSide | None = None
    partner_merge: "MergePlan | None" = None

    @property
    def survivor_partner(self) -> MergeSide | None:
        """The row the survivor is linked to once the merge is done, or None
        when it was not and does not become a transfer leg."""
        if self.adopted_partner is not None:
            return self.adopted_partner
        if self.partner_merge is not None:
            return self.partner_merge.survivor
        return None

    @property
    def relinks(self) -> bool:
        """Whether the survivor's transfer link has to be rewritten. False when
        it keeps the partner it already had."""
        partner = self.survivor_partner
        return partner is not None and self.survivor.transfer_id != partner.id


@dataclass(frozen=True)
class Refused:
    """Why a merge cannot happen, worded for the person who asked for it."""

    reason: str


def _other_legs_mismatch(why: str) -> Refused:
    return Refused(f"The other account's two legs don't match ({why})")


def plan_merge(
    a: MergeSide,
    b: MergeSide,
    requested: uuid.UUID | None,
    partners: Mapping[uuid.UUID, MergeSide],
) -> MergePlan | Refused:
    """The whole merge of `a` and `b`, or why it cannot happen.

    `partners` holds the live partner of each transfer leg among `a` and `b`,
    keyed by its own id (a leg's `transfer_id`). A leg whose partner is absent
    is refused: its transfer is already broken, and a merge is no place to
    guess at it.
    """
    survivor, deleted = choose_survivor(a, b, requested)
    violation = survivor_violation(survivor, deleted, requested)
    if violation is not None:
        return Refused(violation)
    if deleted.transfer_id is None:
        return MergePlan(survivor=survivor, deleted=deleted)

    lost_partner = partners.get(deleted.transfer_id)
    if lost_partner is None:
        return Refused("The other side of this transfer is missing; repair the transfer first")
    if survivor.transfer_id is None:
        if survivor.is_split:
            return Refused(
                "A split cannot take over a transfer; delete the one you don't want instead"
            )
        return MergePlan(survivor=survivor, deleted=deleted, adopted_partner=lost_partner)

    own_partner = partners.get(survivor.transfer_id)
    if own_partner is None:
        return Refused("The other side of this transfer is missing; repair the transfer first")
    if own_partner.account_id != lost_partner.account_id:
        return _other_legs_mismatch("they are in different accounts")
    if own_partner.amount != lost_partner.amount:
        return _other_legs_mismatch(
            f"one is {abs(own_partner.amount):.2f}, the other {abs(lost_partner.amount):.2f}"
        )
    far_survivor, far_deleted = choose_survivor(own_partner, lost_partner, None)
    far_violation = survivor_violation(far_survivor, far_deleted, None)
    if far_violation is not None:
        return _other_legs_mismatch(far_violation[0].lower() + far_violation[1:])
    return MergePlan(
        survivor=survivor,
        deleted=deleted,
        partner_merge=MergePlan(survivor=far_survivor, deleted=far_deleted),
    )


def may_offer_merge(
    a: MergeSide, b: MergeSide, partners: Mapping[uuid.UUID, MergeSide] | None = None
) -> bool:
    """Would a merge of these two be accepted, with no survivor requested?

    Derived from the plan rather than restated, so it cannot answer
    differently from the merge itself. It exists so the register's own
    "may I offer Merge?" question has a server-side counterpart to be tested
    against: the client keeps a copy of this rule (it has the fields, and the
    button has to be drawn before any request is made), and that copy had
    already drifted — it knew about accounts, reconciled pairs, splits and
    transfer legs, but not about bank identity, so the register offered
    Merge on two SimpleFIN rows with different bank ids and the server
    refused every time.

    `partners` is `plan_merge`'s: a merge that takes a transfer's leg away
    depends on the other side, so without it such a merge reads as refused.

    `shared/merge_cases.json` is run by both sides; see
    tests/unit/test_merge_offer.py and frontend mergeEligibility.test.ts.
    """
    return isinstance(plan_merge(a, b, None, partners or {}), MergePlan)
