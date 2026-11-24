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
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal


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


# --- What the merged row reads -------------------------------------------
#
# Survivorship (above) decides which ROW stays. It does not have to decide
# which date, payee, category and memo the merged transaction reads: where
# the two rows disagree, that is the person's to say, and where only one of
# them has a value, nothing is lost by taking it. This is the one place that
# is worked out — the merge writes from it and the preview draws from it, so
# what the dialog shows is what the merge does.

#: Which row a field is kept from. `"both"` is the memo's alone: two
#: different memos are joined rather than one being dropped.
KeepSource = uuid.UUID | Literal["both"]

MEMO_JOIN = " — "


@dataclass(frozen=True)
class MergeKeep:
    """The person's picks: the id of the row each field is kept from. None
    leaves a field at its default — the survivor's value, or the other row's
    where the survivor has none."""

    date: uuid.UUID | None = None
    payee: uuid.UUID | None = None
    category: uuid.UUID | None = None
    memo: KeepSource | None = None


@dataclass(frozen=True)
class MergeRow:
    """The bookkeeping one row brings to a merge — what a person reads on it."""

    id: uuid.UUID
    date: date
    payee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    memo: str | None
    is_split: bool
    is_leg: bool
    reconciled: bool

    @classmethod
    def from_transaction(cls, txn: Any) -> "MergeRow":
        return cls(
            id=txn.id,
            date=txn.date,
            payee_id=txn.payee_id,
            category_id=txn.category_id,
            memo=txn.memo or None,
            is_split=bool(txn.is_split),
            is_leg=txn.transfer_id is not None,
            reconciled=txn.cleared == "reconciled",
        )


@dataclass(frozen=True)
class Kept:
    """One field of the merged row: its value, the row it comes from (None
    when neither row has one), and whether the person had a choice."""

    value: Any
    source: KeepSource | None
    choosable: bool


@dataclass(frozen=True)
class MergedBookkeeping:
    date: Kept
    payee_id: Kept
    category_id: Kept
    memo: Kept


def keep_violation(keep: MergeKeep, a: uuid.UUID, b: uuid.UUID) -> str | None:
    """A pick has to name one of the two rows being merged."""
    for field in ("date", "payee", "category", "memo"):
        wanted = getattr(keep, field)
        if wanted is None or wanted in (a, b) or (field == "memo" and wanted == "both"):
            continue
        return f"The {field} to keep must come from one of the two transactions"
    return None


def merge_bookkeeping(
    survivor: MergeRow,
    deleted: MergeRow,
    keep: MergeKeep | None = None,
    *,
    becomes_leg: bool = False,
    date_fixed: bool = False,
) -> MergedBookkeeping:
    """The date, payee, category and memo of the merged row.

    The default is additive, and is what a merge with no picks has always
    done: the survivor keeps what it has and takes what it lacks, and two
    different memos are joined. A field is `choosable` only where the two
    rows both have a value and the values differ — and the structure allows
    it:

    - **A transfer leg** (the survivor is one, or `becomes_leg`): its payee
      is its destination, its category is the transfer rule's, and its date
      is its partner's. Only the memo is a choice.
    - **A split** on either side: the categories live on its lines, which
      always carry over, and the lines share their parent's date — so
      neither the category nor the date is a choice.
    - **A reconciled survivor**: the statement vouched for the date.
    - `date_fixed`: the bank's posting has already decided the date (a
      pending hold taking its posted date).

    A pick for a field that is not choosable is ignored, not refused: the
    preview said so, and the pick changes nothing it could have changed.
    """
    keep = keep or MergeKeep()
    rows = {survivor.id: survivor, deleted.id: deleted}
    leg = survivor.is_leg or becomes_leg
    split = survivor.is_split or deleted.is_split

    def held(field: str, wanted: KeepSource | None, *, choice: bool) -> Kept:
        """An ordinary field: the survivor's value, else the other row's —
        or the picked row's, where both have one and `choice` allows it."""
        mine, theirs = getattr(survivor, field), getattr(deleted, field)
        choosable = choice and mine is not None and theirs is not None and mine != theirs
        picked = rows.get(wanted) if isinstance(wanted, uuid.UUID) else None
        if choosable and picked is not None:
            return Kept(getattr(picked, field), picked.id, True)
        if mine is not None:
            return Kept(mine, survivor.id, choosable)
        if theirs is not None:
            return Kept(theirs, deleted.id, False)
        return Kept(None, None, False)

    def own(field: str) -> Kept:
        """What the survivor has, even nothing — no filling, no choice."""
        value = getattr(survivor, field)
        return Kept(value, survivor.id if value is not None else None, False)

    when = held("date", keep.date, choice=not (leg or split or survivor.reconciled or date_fixed))
    # A leg keeps the payee and category it has, even none: the transfer
    # rules decide those. A row only now becoming a leg still takes what it
    # lacks — the link judges that next — but is offered no choice.
    payee = own("payee_id") if survivor.is_leg else held("payee_id", keep.payee, choice=not leg)
    if split:
        owner = survivor if survivor.is_split else deleted
        category = Kept(None, owner.id, False)
    elif survivor.is_leg:
        category = own("category_id")
    else:
        category = held("category_id", keep.category, choice=not leg)

    mine, theirs = survivor.memo, deleted.memo
    if mine and theirs and mine != theirs:
        if keep.memo == survivor.id:
            memo = Kept(mine, survivor.id, True)
        elif keep.memo == deleted.id:
            memo = Kept(theirs, deleted.id, True)
        else:
            memo = Kept(f"{mine}{MEMO_JOIN}{theirs}", "both", True)
    elif theirs and not mine:
        memo = Kept(theirs, deleted.id, False)
    else:
        memo = Kept(mine, survivor.id if mine else None, False)

    return MergedBookkeeping(date=when, payee_id=payee, category_id=category, memo=memo)
