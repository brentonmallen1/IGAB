from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, Payee, Transaction
from igab.domain.bank_posting import Apply, FeedRecord, Review, RowState, posting_updates
from igab.domain.exceptions import InvariantViolation
from igab.domain.merging import MergeSide, choose_survivor, survivor_violation
from igab.domain.reconciliation import (
    RECONCILED_LOCKED_FIELDS,
    locked_changes,
    locked_values,
    reconciled_edit_message,
)
from igab.domain.splits import require_split_balances
from igab.domain.transfers import (
    leg_may_carry_category,
    linking_breaks_category_rule,
    pair_may_carry_category,
    transfer_link_fields,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match, source_for
from igab.services.filing import may_be_filed_to, require_categorizable
from igab.services.ownership import require_in_budget

if TYPE_CHECKING:
    from igab.repositories.attachment_repo import AttachmentRepository
    from igab.repositories.transaction_match_repo import TransactionMatchRepository

# Sentinel distinguishing "field not provided" from an explicit None (which
# clears nullable fields like category_id/payee_id/memo on PATCH).
UNSET = cast(Any, object())


@dataclass
class TransactionCreate:
    account_id: uuid.UUID
    date: datetime.date
    amount: Decimal
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: str = "uncleared"
    approved: bool = True
    transfer_account_id: uuid.UUID | None = None
    parent_transaction_id: uuid.UUID | None = None
    import_id: str | None = None
    import_batch_id: uuid.UUID | None = None
    import_description: str | None = None
    sync_id: str | None = None
    sync_source: str | None = None
    bank_posted_date: datetime.date | None = None
    bank_amount: Decimal | None = None
    bank_payee: str | None = None
    # Set False when an uncategorized row is the point — a reconciliation
    # adjustment must reach Ready to Assign, not inherit whatever category
    # the last adjustment happened to be filed under.
    auto_categorize: bool = True
    # AI provenance ('ai_receipt' | 'ai_nl') — set server-side only, never
    # accepted verbatim from clients.
    created_via: str | None = None
    #: The schedule this row is being entered from (see §enter_now).
    scheduled_transaction_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class TransactionUpdate:
    date: datetime.date | None = UNSET
    amount: Decimal | None = UNSET
    payee_id: uuid.UUID | None = UNSET
    category_id: uuid.UUID | None = UNSET
    memo: str | None = UNSET
    cleared: str | None = UNSET
    approved: bool | None = UNSET
    #: Not a column. Set: make/repoint this row into a transfer to that
    #: account (linking or creating the partner leg). Explicit None: break a
    #: linked transfer, or clear an orphan leg's transfer payee.
    transfer_account_id: uuid.UUID | None = UNSET
    #: Not a column. With transfer_account_id: link exactly this existing row
    #: as the partner (the user's pick among ambiguous candidates).
    transfer_partner_transaction_id: uuid.UUID | None = UNSET
    #: Not a column. Create the far leg even though candidates exist.
    transfer_create_partner: bool = UNSET
    latitude: float | None = UNSET
    longitude: float | None = UNSET


@dataclass
class SplitSpec:
    """One line of a split — everything else (account, date, cleared,
    approved) is inherited from the parent transaction. `id` names an
    existing line to update in place; None means a new line."""

    amount: Decimal
    category_id: uuid.UUID | None = None
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    memo: str | None = None
    id: uuid.UUID | None = None


# Fields that may never be set to NULL via PATCH
_REQUIRED_FIELDS = ("date", "amount", "cleared", "approved")


def origin_of(data: TransactionCreate) -> str:
    """Where a new row comes from, when the caller did not say (the AI paths
    say 'ai_receipt' / 'ai_nl' themselves). See Transaction.created_via."""
    if data.sync_source:
        return "sync"
    if data.scheduled_transaction_id is not None:
        return "scheduled"
    if data.import_batch_id is not None or data.import_id:
        return "import"
    return "manual"


def build_transaction_service(session: AsyncSession) -> TransactionService:
    """A fully wired TransactionService over one session.

    The one place the constructor is called with every repository. Five
    call sites used to wire it by hand, and the scheduler's two left out the
    attachment and match repositories — so a merge made by the hourly sync
    silently skipped reassigning receipts and cancelling stale review matches.
    """
    from igab.repositories.attachment_repo import AttachmentRepository
    from igab.repositories.transaction_match_repo import TransactionMatchRepository

    return TransactionService(
        session,
        TransactionRepository(session),
        AccountRepository(session),
        CategoryRepository(session),
        PayeeRepository(session),
        attachment_repo=AttachmentRepository(session),
        match_repo=TransactionMatchRepository(session),
    )


# Cleared values reserved for system flows (reconciliation, bank sync)
_SYSTEM_CLEARED_VALUES = ("reconciled", "pending")


class TransactionService:
    def __init__(
        self,
        session: AsyncSession,
        transaction_repo: TransactionRepository,
        account_repo: AccountRepository,
        category_repo: CategoryRepository,
        payee_repo: PayeeRepository,
        attachment_repo: AttachmentRepository | None = None,
        match_repo: TransactionMatchRepository | None = None,
    ) -> None:
        self.session = session
        self.transaction_repo = transaction_repo
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.payee_repo = payee_repo
        self.attachment_repo = attachment_repo
        self.match_repo = match_repo
        self.changes = ChangeRecorder(session)

    async def _record_txn(
        self,
        txn: Transaction,
        action: str,
        *,
        before: dict | None = None,
        source: str = "manual",
        refresh: bool = True,
    ) -> None:
        """Record a change with the transaction's final (post-flush) state, so
        undo's changed-since checks compare against what the DB will return."""
        if refresh:
            await self.transaction_repo.refresh(txn)
        after = None if action == "delete" else snapshot("transaction", txn)
        # A PATCH that changes nothing is not a user-visible event.
        if action == "update" and before is not None and after is not None:
            if not snapshots_match(after, before):
                return
        await self.changes.record(
            budget_id=txn.budget_id,
            entity_type="transaction",
            entity_id=txn.id,
            action=action,
            before=before,
            after=after,
            source=source,
        )

    async def create(
        self, budget_id: uuid.UUID, data: TransactionCreate, *, record: bool = True
    ) -> Transaction:
        account = await self.account_repo.get_or_raise(data.account_id)
        if str(account.budget_id) != str(budget_id):
            raise InvariantViolation("Account does not belong to this budget")

        # Body-supplied ids bypass the route's BudgetAccess guard; reject any
        # that point at another budget's category/payee before persisting.
        await require_in_budget(self.session, Category, data.category_id, budget_id, "Category")
        await require_categorizable(self.session, data.category_id)
        await require_in_budget(self.session, Payee, data.payee_id, budget_id, "Payee")

        if data.transfer_account_id:
            return await self._create_transfer(budget_id, data, record=record)

        # A plain row is a leg with no partner — the one category rule in
        # domain/transfers.py decides it. Off-budget rows are net-worth
        # movement: a category here moved envelopes (and, via the floor,
        # Ready to Assign) with no on-budget event behind it.
        if data.category_id is not None and not leg_may_carry_category(account.on_budget):
            raise InvariantViolation(
                "Transactions on a tracking account cannot carry a category — "
                "off-budget activity is net-worth movement, not budget spending"
            )

        # Resolve or create payee
        payee = await self._resolve_payee(budget_id, data.payee_id, data.payee_name)
        payee_id = payee.id if payee else None

        # Auto-categorization: use the most recent category for this payee.
        # Falls back to default_category_id for new payees with no transaction
        # history. Never offered to an off-budget row: a synced brokerage or
        # mortgage row would otherwise inherit whatever category its payee
        # last used on the checking side, recurring every sync.
        category_id = data.category_id
        if payee and not category_id and data.auto_categorize and account.on_budget:
            category_id = await self.transaction_repo.get_most_recent_category_for_payee(
                budget_id, payee.id
            )
            if not category_id and payee.default_category_id:
                # The same rule the caller's own category was held to, asked
                # rather than enforced. This resolution happens *after*
                # `require_categorizable`, so a default pointing at a card's
                # set-aside envelope, a tracked debt or an archived envelope
                # would file a brand-new row somewhere the guard refuses — and
                # it is a stored pointer, so it outlives what it points at.
                if await may_be_filed_to(self.session, payee.default_category_id):
                    category_id = payee.default_category_id

        created_via = data.created_via or origin_of(data)
        txn = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=data.account_id,
            date=data.date,
            amount=data.amount,
            payee_id=payee_id,
            category_id=category_id,
            memo=data.memo,
            cleared=data.cleared,
            approved=data.approved,
            parent_transaction_id=data.parent_transaction_id,
            scheduled_transaction_id=data.scheduled_transaction_id,
            import_id=data.import_id,
            import_batch_id=data.import_batch_id,
            import_description=data.import_description,
            sync_id=data.sync_id,
            sync_source=data.sync_source,
            # Bank-sourced from birth: the posting rule would otherwise
            # write this on the next sync, and "writes nothing" is a promise.
            has_sync_source=data.sync_source is not None,
            bank_posted_date=data.bank_posted_date,
            bank_amount=data.bank_amount,
            bank_payee=data.bank_payee,
            created_via=created_via,
            latitude=data.latitude,
            longitude=data.longitude,
        )
        if record:
            await self._record_txn(txn, "create", source=source_for(created_via))
        return txn

    async def create_split(
        self, budget_id: uuid.UUID, header: TransactionCreate, splits: list[TransactionCreate]
    ) -> Transaction:
        """Create a split transaction: one parent + N children."""
        specs = [
            SplitSpec(
                amount=s.amount,
                category_id=s.category_id,
                payee_id=s.payee_id,
                payee_name=s.payee_name,
                memo=s.memo,
            )
            for s in splits
        ]
        require_split_balances(header.amount, [s.amount for s in specs])

        # Parent has no category (it's distributed across splits). Auto-
        # categorization in create() may have applied a payee default, so
        # force category back to NULL alongside the is_split flag.
        header.category_id = None
        with self.changes.batch():
            parent = await self.create(budget_id, header, record=False)
            parent = await self.transaction_repo.update(parent.id, is_split=True, category_id=None)
            # Recorded after the is_split flip so the snapshot holds final state.
            await self._record_txn(parent, "create", refresh=False)
            await self._apply_split_legs(budget_id, parent, specs, existing=[])
        await self.transaction_repo.refresh(parent)
        return parent

    async def convert_to_split(
        self, budget_id: uuid.UUID, transaction_id: uuid.UUID, splits: list[SplitSpec]
    ) -> Transaction:
        """Split an existing transaction in place: the row becomes the parent.

        Unlike create-replacement-and-delete, this preserves the transaction's
        identity — attachments, AI-job links, import/sync ids, and provenance
        all stay put. Receipts made this mandatory: the image is attached to
        the row being split. A reconciled row may be split: its amount does
        not move (the lines must sum to it) and the lines lock with it.
        """
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.is_split:
            raise InvariantViolation("Transaction is already split")
        if txn.parent_transaction_id is not None:
            raise InvariantViolation("Cannot split a split child")
        if txn.transfer_id is not None:
            raise InvariantViolation("Cannot split a transfer")

        before = snapshot("transaction", txn)
        # One batch: undoing it deletes the lines and restores the parent's
        # pre-split category and is_split flag. Lines first — they validate
        # (sum, categories) before anything is written — then the flip.
        with self.changes.batch():
            await self._apply_split_legs(budget_id, txn, splits, existing=[])
            await self.transaction_repo.update(txn.id, is_split=True, category_id=None)
            await self._record_txn(txn, "update", before=before)
        await self.transaction_repo.refresh(txn)
        return txn

    async def replace_splits(
        self, budget_id: uuid.UUID, parent_id: uuid.UUID, splits: list[SplitSpec]
    ) -> list[Transaction]:
        """Make these the split's lines: update the ones named by id, create
        the rest, remove the missing. The parent's amount does not move — the
        lines must still sum to it — so this is bookkeeping, and works on a
        reconciled parent too (its lines stay reconciled). Returns the lines.
        """
        parent = await self.transaction_repo.get_or_raise(parent_id)
        if str(parent.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if not parent.is_split:
            raise InvariantViolation("Transaction is not split")
        existing = await self.transaction_repo.get_splits(parent.id)
        with self.changes.batch():
            lines = await self._apply_split_legs(budget_id, parent, splits, existing=existing)
        return lines

    async def _apply_split_legs(
        self,
        budget_id: uuid.UUID,
        parent: Transaction,
        specs: list[SplitSpec],
        *,
        existing: list[Transaction],
    ) -> list[Transaction]:
        """The one place a split's lines are written.

        Lines mirror the parent's date, cleared state and approval — account
        balances (parent rows) and category activity (leaf rows) have to
        agree on when money moved — and they must sum to the parent's amount
        exactly (domain.splits). A spec naming an id updates that line; an
        id from some other transaction is refused (the route guards only the
        parent); a line not named is removed, its attachments moved to the
        parent and remembered so undo puts them back. Lines list oldest first;
        lines written in one request share a created_at and order by id.
        Three creation-time copies of the mirror rule used to exist; this is
        the one. Records every step; callers own the batch.
        """
        require_split_balances(parent.amount, [s.amount for s in specs])
        # Children share the parent's account, and line updates write through
        # the repo below (not service.update) — so the category rule is
        # checked once here for the whole split.
        if any(spec.category_id is not None for spec in specs):
            parent_account = await self.account_repo.get_or_raise(parent.account_id)
            if not leg_may_carry_category(parent_account.on_budget):
                raise InvariantViolation(
                    "Transactions on a tracking account cannot carry a category — "
                    "off-budget activity is net-worth movement, not budget spending"
                )
        existing_by_id = {child.id: child for child in existing}
        for spec in specs:
            if spec.id is not None and spec.id not in existing_by_id:
                raise InvariantViolation("Split line does not belong to this transaction")
            await require_in_budget(self.session, Category, spec.category_id, budget_id, "Category")
            await require_categorizable(self.session, spec.category_id)

        kept: list[Transaction] = []
        for spec in specs:
            if spec.id is not None:
                child = existing_by_id[spec.id]
                child_before = snapshot("transaction", child)
                changes: dict[str, Any] = {
                    "amount": spec.amount,
                    "category_id": spec.category_id,
                    "memo": spec.memo,
                }
                if spec.payee_id is not None or spec.payee_name:
                    payee = await self._resolve_payee(budget_id, spec.payee_id, spec.payee_name)
                    changes["payee_id"] = payee.id if payee else None
                updated = await self.transaction_repo.update(child.id, **changes)
                await self._record_txn(updated, "update", before=child_before)
                kept.append(updated)
            else:
                child = await self.create(
                    budget_id,
                    TransactionCreate(
                        account_id=parent.account_id,
                        date=parent.date,
                        amount=spec.amount,
                        category_id=spec.category_id,
                        payee_id=spec.payee_id,
                        payee_name=spec.payee_name,
                        memo=spec.memo,
                        cleared=parent.cleared,
                        approved=parent.approved,
                        parent_transaction_id=parent.id,
                        created_via=parent.created_via,
                    ),
                    record=False,
                )
                await self._record_txn(child, "create")
                kept.append(child)

        kept_ids = {child.id for child in kept}
        for child in existing:
            if child.id in kept_ids:
                continue
            child_before = snapshot("transaction", child)
            if self.attachment_repo is not None:
                child_before["_attachment_ids"] = [
                    str(a.id) for a in await self.attachment_repo.get_for_transaction(child.id)
                ]
                await self.attachment_repo.reassign(child.id, parent.id)
            await self.transaction_repo.soft_delete(child.id)
            await self._record_txn(child, "delete", before=child_before, refresh=False)
        return kept

    async def update(
        self, budget_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
    ) -> Transaction:
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")

        changes = {k: v for k, v in vars(data).items() if v is not UNSET}
        # Not columns — pulled out before the generic column update. Handled
        # as their own recorded steps inside the same undo batch below.
        transfer_requested = "transfer_account_id" in changes
        transfer_account_id: uuid.UUID | None = changes.pop("transfer_account_id", None)
        partner_pick: uuid.UUID | None = changes.pop("transfer_partner_transaction_id", None)
        create_partner: bool = bool(changes.pop("transfer_create_partner", False))
        for field in _REQUIRED_FIELDS:
            if field in changes and changes[field] is None:
                raise InvariantViolation(f"{field} cannot be empty")

        # Reconciled: the money is locked, the bookkeeping is not (see
        # domain.reconciliation). Unchanged locked values are dropped rather
        # than refused — the editor sends every field it shows — so they
        # cannot trip the transfer or split-propagation rules below either.
        if txn.cleared == "reconciled":
            locked = locked_changes(locked_values(txn), changes)
            if locked:
                raise InvariantViolation(reconciled_edit_message(locked))
            for field in RECONCILED_LOCKED_FIELDS & changes.keys():
                del changes[field]

        if transfer_requested:
            if txn.is_split or txn.parent_transaction_id is not None:
                raise InvariantViolation(
                    "A split (or one of its lines) cannot be linked as a transfer"
                )
            if {"amount", "date"} & changes.keys():
                raise InvariantViolation(
                    "Change the transfer link and money fields in separate edits"
                )

        # Body-supplied category/payee ids bypass BudgetAccess; a re-point to
        # another budget's object must be rejected (also covers bulk-categorize).
        await require_in_budget(
            self.session, Category, changes.get("category_id"), budget_id, "Category"
        )
        await require_categorizable(self.session, changes.get("category_id"))
        await require_in_budget(self.session, Payee, changes.get("payee_id"), budget_id, "Payee")
        if changes.get("cleared") in _SYSTEM_CLEARED_VALUES:
            raise InvariantViolation(
                "Reconciled and pending statuses are set by reconciliation and bank sync"
            )

        # Split children: money-moving fields live on the parent so that
        # account balances (parent rows) and category activity (leaf rows)
        # can never disagree. Category/payee/memo remain child-editable.
        if txn.parent_transaction_id is not None:
            locked = {"amount", "date", "cleared", "approved"} & changes.keys()
            if locked:
                raise InvariantViolation(
                    "Edit the split's parent transaction to change " + ", ".join(sorted(locked))
                )

        # Split parents: amount is the children's sum; category lives on children.
        if txn.is_split:
            if "amount" in changes:
                raise InvariantViolation(
                    "Change the split line amounts instead; the total is their sum"
                )
            if changes.get("category_id") is not None:
                raise InvariantViolation("A split transaction's categories live on its lines")

        # Plain rows: same rule as create — a category may not land on an
        # off-budget account (bulk-categorize funnels through here too).
        if changes.get("category_id") is not None and not txn.transfer_id:
            own_account = await self.account_repo.get_or_raise(txn.account_id)
            if not leg_may_carry_category(own_account.on_budget):
                raise InvariantViolation(
                    "Transactions on a tracking account cannot carry a category — "
                    "off-budget activity is net-worth movement, not budget spending"
                )

        # Transfers: guard the pair as a unit.
        partner: Transaction | None = None
        if txn.transfer_id:
            partner = await self.transaction_repo.get(txn.transfer_id)
            if "payee_id" in changes:
                # The payee of a linked leg IS its destination; changing it
                # alone would make the name and the link disagree.
                raise InvariantViolation(
                    "This is a linked transfer — its payee is its destination. "
                    "Change the transfer's account, or break the transfer first."
                )
            if changes.get("category_id") is not None and not transfer_requested:
                own_account = await self.account_repo.get_or_raise(txn.account_id)
                partner_account = (
                    await self.account_repo.get(partner.account_id) if partner is not None else None
                )
                # A missing partner reads as on-budget: refuse rather than
                # categorize half a link whose other side cannot be checked.
                partner_on_budget = partner_account.on_budget if partner_account else True
                if not leg_may_carry_category(own_account.on_budget, partner_on_budget):
                    raise InvariantViolation(
                        "Transfers can only be categorized on the on-budget side "
                        "of an off-budget transfer"
                    )
            if ("amount" in changes or "date" in changes) and partner is not None:
                if partner.cleared == "reconciled":
                    raise InvariantViolation(
                        "The other side of this transfer is reconciled; unreconcile it first"
                    )
            if "amount" in changes:
                new_amount = Decimal(changes["amount"])
                if (new_amount >= 0) != (txn.amount >= 0):
                    raise InvariantViolation(
                        "Changing a transfer's direction isn't supported; "
                        "delete it and create a new transfer"
                    )

        transfer_plan: dict[str, Any] | None = None
        if transfer_requested:
            transfer_plan = await self._plan_transfer_edit(
                budget_id,
                txn,
                target_account_id=transfer_account_id,
                partner_pick=partner_pick,
                create_partner=create_partner,
                # The category this row will END UP with — the on/off-budget
                # rule has to judge the edit's result, not its starting point.
                category_id=changes["category_id"] if "category_id" in changes else txn.category_id,
            )

        before_self = snapshot("transaction", txn)
        with self.changes.batch():
            if transfer_plan is not None:
                # Merges the row's own transfer_id/payee_id into `changes`, so
                # the pair moves in one recorded step per row and one undo.
                changes.update(await self._apply_transfer_edit(budget_id, txn, transfer_plan))

            # Keep the transfer pair zero-sum and date-aligned.
            if partner is not None and transfer_plan is None:
                partner_changes: dict[str, Any] = {}
                if "amount" in changes:
                    partner_changes["amount"] = -changes["amount"]
                if "date" in changes:
                    partner_changes["date"] = changes["date"]
                if partner_changes:
                    partner_before = snapshot("transaction", partner)
                    updated_partner = await self.transaction_repo.update(
                        partner.id, **partner_changes
                    )
                    await self._record_txn(updated_partner, "update", before=partner_before)

            # Propagate parent date/cleared to children (mirror invariant).
            if txn.is_split and ({"date", "cleared"} & changes.keys()):
                child_changes = {k: changes[k] for k in ("date", "cleared") if k in changes}
                await self._mirror_children(txn.id, **child_changes)

            updated = await self.transaction_repo.update(transaction_id, **changes)
            await self._record_txn(updated, "update", before=before_self)
        return updated

    async def delete(
        self, budget_id: uuid.UUID, transaction_id: uuid.UUID, *, source: str = "manual"
    ) -> uuid.UUID:
        """Soft-delete a transaction (plus transfer partner and split
        children). Returns the change-log batch id so callers can offer undo.
        `source` is who is acting — "system" when the bank sync sweeps a
        pending row the feed dropped."""
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared == "reconciled":
            raise InvariantViolation("Cannot delete a reconciled transaction")
        if txn.parent_transaction_id is not None:
            raise InvariantViolation(
                "Delete the split's parent transaction (or edit its lines) instead"
            )

        with self.changes.batch() as batch_id:
            # Soft delete transfer partner too — unless it's reconciled.
            if txn.transfer_id:
                partner = await self.transaction_repo.get(txn.transfer_id)
                if partner is not None:
                    if partner.cleared == "reconciled":
                        raise InvariantViolation(
                            "The other side of this transfer is reconciled; unreconcile it first"
                        )
                    partner_before = snapshot("transaction", partner)
                    await self.transaction_repo.soft_delete(partner.id)
                    await self._record_txn(
                        partner, "delete", before=partner_before, source=source, refresh=False
                    )

            # Soft delete any splits (children mirror the parent's cleared state,
            # so a non-reconciled parent implies non-reconciled children).
            splits = await self.transaction_repo.get_splits(transaction_id)
            for split in splits:
                split_before = snapshot("transaction", split)
                await self.transaction_repo.soft_delete(split.id)
                await self._record_txn(
                    split, "delete", before=split_before, source=source, refresh=False
                )

            if self.match_repo is not None:
                await self.match_repo.cancel_pending_for_transaction(transaction_id)

            txn_before = snapshot("transaction", txn)
            await self.transaction_repo.soft_delete(transaction_id)
            await self._record_txn(txn, "delete", before=txn_before, source=source, refresh=False)
        return batch_id

    async def unreconcile(self, budget_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        """Unlock a reconciled transaction back to cleared (explicit user action)."""
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared != "reconciled":
            raise InvariantViolation("Transaction is not reconciled")

        with self.changes.batch():
            if txn.is_split:
                await self._mirror_children(txn.id, cleared="cleared")
            before = snapshot("transaction", txn)
            updated = await self.transaction_repo.update(transaction_id, cleared="cleared")
            await self._record_txn(updated, "update", before=before)
        return updated

    async def _mirror_children(
        self, parent_id: uuid.UUID, *, source: str = "manual", **fields: Any
    ) -> None:
        """Write `fields` onto every live split line of a parent, recorded.

        Children must always share their parent's date and cleared state —
        account balances (parent rows) and category activity (leaf rows) have
        to agree on when money moved. This is the only place that mirror is
        written; three copies of it once existed and one of them (the bank
        sync's) cleared a parent while leaving its lines pending.
        """
        for child in await self.transaction_repo.get_splits(parent_id):
            child_before = snapshot("transaction", child)
            updated_child = await self.transaction_repo.update(child.id, **fields)
            await self._record_txn(updated_child, "update", before=child_before, source=source)

    async def apply_bank_posting(
        self, txn: Transaction, feed: FeedRecord, *, confirmed: bool
    ) -> Apply | Review:
        """The bank feed has a record for this row: apply what the posting
        rule says (domain.bank_posting) and record it.

        The only writer of bank-driven changes. Both sync paths — a row found
        by its bank id and a row found by amount and date — come through
        here, as does an accepted amount-change review (`confirmed=True`,
        via `merge`). A sync therefore never rewrites a row unrecorded, and a
        split parent's lines always follow its cleared state.
        """
        outcome = posting_updates(RowState.from_transaction(txn), feed, confirmed=confirmed)
        if isinstance(outcome, Review) or not outcome.updates:
            return outcome
        before = snapshot("transaction", txn)
        with self.changes.batch():
            updated = await self.transaction_repo.update(txn.id, **outcome.updates)
            await self._record_txn(updated, "update", before=before, source="system")
            if "cleared" in outcome.updates and txn.is_split:
                await self._mirror_children(
                    txn.id, source="system", cleared=outcome.updates["cleared"]
                )
        return outcome

    async def release_bank_link(self, txn: Transaction) -> None:
        """The bank record this row was linked to moved on — the bank posted
        a different amount, or re-identified the record. The row goes back to
        unlinked and matchable; its bank provenance stays as a trace."""
        if txn.sync_id is None:
            return
        before = snapshot("transaction", txn)
        updated = await self.transaction_repo.update(txn.id, sync_id=None)
        await self._record_txn(updated, "update", before=before, source="system")

    async def approve(self, transaction_id: uuid.UUID, budget_id: uuid.UUID | None = None):
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if budget_id is not None and str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        before = snapshot("transaction", txn)
        updated = await self.transaction_repo.update(transaction_id, approved=True)
        if not before["approved"]:
            await self._record_txn(updated, "approve", before=before)
        return updated

    async def _create_transfer(
        self, budget_id: uuid.UUID, data: TransactionCreate, *, record: bool = True
    ) -> Transaction:
        if data.transfer_account_id is None:
            raise ValueError("transfer_account_id is required for transfer transactions")
        to_account = await self.account_repo.get_or_raise(data.transfer_account_id)
        if str(to_account.budget_id) != str(budget_id):
            raise InvariantViolation("Transfer account does not belong to this budget")
        from_account = await self.account_repo.get_or_raise(data.account_id)

        # YNAB "spending transfer" rule — the one implementation lives in
        # domain/transfers.py; this call site only decides the message and
        # which leg receives the category.
        category_id = data.category_id
        if category_id is not None and not pair_may_carry_category(
            from_account.on_budget, to_account.on_budget
        ):
            raise InvariantViolation(
                "Only transfers between an on-budget and an off-budget account can be categorized"
            )
        source_category = (
            category_id
            if leg_may_carry_category(from_account.on_budget, to_account.on_budget)
            else None
        )
        dest_category = (
            category_id
            if leg_may_carry_category(to_account.on_budget, from_account.on_budget)
            else None
        )

        # Source: outflow from from-account
        from_payee = await self._get_transfer_payee(budget_id, to_account)
        created_via = data.created_via or origin_of(data)
        source = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=data.account_id,
            date=data.date,
            amount=-abs(data.amount),
            payee_id=from_payee.id,
            category_id=source_category,
            memo=data.memo,
            cleared=data.cleared,
            approved=data.approved,
            created_via=created_via,
            scheduled_transaction_id=data.scheduled_transaction_id,
        )

        # Destination: inflow into to-account
        to_payee = await self._get_transfer_payee(budget_id, from_account)
        dest = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=data.transfer_account_id,
            date=data.date,
            amount=abs(data.amount),
            payee_id=to_payee.id,
            category_id=dest_category,
            memo=data.memo,
            cleared="uncleared",
            approved=data.approved,
            transfer_id=source.id,
            created_via=created_via,
            scheduled_transaction_id=data.scheduled_transaction_id,
        )

        # Link source → dest
        await self.transaction_repo.update(source.id, transfer_id=dest.id)
        await self.transaction_repo.refresh(source)
        if record:
            # Recorded after linking so both snapshots carry their transfer_id;
            # one batch, so the pair is undone together.
            with self.changes.batch():
                await self._record_txn(source, "create", refresh=False)
                await self._record_txn(dest, "create")
        return source

    async def repair_tracking_categories(self, budget_id: uuid.UUID) -> dict[str, int]:
        """Strip the category from rows on off-budget accounts.

        Such rows predate the write-side rule (an import, a sync
        auto-categorize, an account flipped off budget after the fact). The
        activity sums already exclude them, so this moves no money — it makes
        the register stop claiming spending the budget never counted. Each
        strip is change-logged in one batch, so undo restores all of them.
        Idempotent: a second run finds nothing.

        Returns {stripped}.
        """
        rows = await self.transaction_repo.list_categorized_tracking_rows(budget_id)
        stripped = 0
        with self.changes.batch():
            for row in rows:
                before = snapshot("transaction", row)
                updated = await self.transaction_repo.update(row.id, category_id=None)
                await self._record_txn(updated, "update", before=before)
                stripped += 1
        return {"stripped": stripped}

    async def link_legs(
        self,
        budget_id: uuid.UUID,
        outflow: Transaction,
        inflow: Transaction,
        *,
        clear_categories: Collection[uuid.UUID] = (),
    ) -> None:
        """Join two existing rows as one transfer, writing both sides.

        The unattended counterpart of the editor's `link` action: same field
        set (`transfer_link_fields`), same transfer-payee convention, so a pair
        linked by a sync is indistinguishable from one linked by hand.

        `clear_categories` names the legs whose category must go, decided by
        `domain/transfers.pair_legs` — an internal on↔on movement is not
        spending, so a category on either leg would count moving money as
        money spent. The caller has already established that each of those
        categories was a guess, not a person's choice.

        Change-logged like any other write, so the whole pairing is undoable.
        """
        accounts = {
            leg.id: await self.account_repo.get_or_raise(leg.account_id)
            for leg in (outflow, inflow)
        }
        out_payee = await self._get_transfer_payee(budget_id, accounts[inflow.id])
        in_payee = await self._get_transfer_payee(budget_id, accounts[outflow.id])
        out_fields, in_fields = transfer_link_fields(
            out_payee.id, in_payee.id, own_id=outflow.id, partner_id=inflow.id
        )
        to_clear = set(clear_categories)
        with self.changes.batch():
            for leg, fields in ((outflow, out_fields), (inflow, in_fields)):
                before = snapshot("transaction", leg)
                if leg.id in to_clear:
                    fields = {**fields, "category_id": None}
                updated = await self.transaction_repo.update(leg.id, **fields)
                await self._record_txn(updated, "update", before=before)

    async def repair_transfers(
        self, budget_id: uuid.UUID, *, date_tolerance_days: int = 0
    ) -> dict[str, int]:
        """Link the transfer legs already in the budget whose partner is plain.

        Fixing the importer only helps the next import; a budget already
        carrying a thousand orphan legs needs the pass. Idempotent: it links
        only rows that are unlinked now, so running it twice links nothing the
        second time.

        Deliberately conservative — it writes no money and creates no rows.
        Linking changes only `transfer_id`, so amounts, categories and
        reconciled state are untouched and even a reconciled leg is safe to
        pair. Where more than one row could be the partner it links NOTHING
        and reports the cluster as ambiguous: the register's picker is where a
        person answers that, and a wrong guess here is a wrong number in a
        report nobody would think to question.

        Returns {linked, ambiguous, remaining} — pairs made, legs left for a
        person to decide, and legs with no candidate at all.
        """
        legs = await self.transaction_repo.list_unpaired_transfer_legs(budget_id)
        on_budget = {
            a.id: a.on_budget
            for a in await self.account_repo.get_all(budget_id, include_closed=True)
        }
        # (leg id, partner account) → the payee's target. Both directions of a
        # pair appear in this list, so each pair is seen twice; `claimed`
        # keeps the second sighting from re-linking or double-counting it.
        claimed: set[uuid.UUID] = set()
        # Every row in a cluster the pass refuses to resolve. The whole cluster
        # goes off limits, not just the leg that noticed: with one row in
        # checking and two candidates in savings, each of THOSE sees only one
        # candidate, so a per-leg rule would cheerfully link one of them from
        # the other side — the arbitrary guess this exists to avoid.
        contested: set[uuid.UUID] = set()
        linked = 0

        with self.changes.batch():
            for leg in legs:
                if leg.id in claimed or leg.id in contested:
                    continue
                target_id = leg.counterpart_account_id
                if target_id is None:
                    continue
                candidates = [
                    c
                    for c in await self.transaction_repo.find_transfer_candidates(
                        account_id=target_id,
                        amount=-leg.amount,
                        counterpart_account_id=leg.account_id,
                        on_date=leg.date,
                        date_tolerance_days=date_tolerance_days,
                    )
                    if c.id != leg.id and c.id not in claimed and c.id not in contested
                ]
                if not candidates:
                    continue
                if len(candidates) > 1:
                    contested.add(leg.id)
                    contested.update(c.id for c in candidates)
                    continue

                partner = candidates[0]
                # Ambiguity is a property of the CLUSTER, but it is only
                # visible from the crowded side, and which side is visited
                # first is not decided here: `list_unpaired_transfer_legs`
                # orders by (date, created_at), and every row an import wrote
                # in one transaction shares both — `func.now()` is the
                # transaction's start time — so Postgres may return them in
                # any order.
                #
                # With one leg in checking and two identical candidates in
                # savings, reaching the checking leg first contests all three;
                # reaching a savings leg first sees exactly one candidate and
                # links an arbitrary half of the pair. That is the guess this
                # whole pass exists to refuse, and it turned up as a CI flake
                # rather than as a wrong number, which is the lucky version.
                #
                # So the rule is mutual: a pair is linked only when each side
                # is the other's only candidate. Order cannot change that.
                partner_options = [
                    c
                    for c in await self.transaction_repo.find_transfer_candidates(
                        account_id=leg.account_id,
                        amount=-partner.amount,
                        counterpart_account_id=partner.account_id,
                        on_date=partner.date,
                        date_tolerance_days=date_tolerance_days,
                    )
                    if c.id != partner.id and c.id not in claimed and c.id not in contested
                ]
                if len(partner_options) > 1:
                    contested.add(leg.id)
                    contested.add(partner.id)
                    contested.update(c.id for c in partner_options)
                    continue
                # The auto-pass must not create what the manual paths refuse:
                # a category anywhere but the on-budget side of an on↔off pair
                # (domain/transfers.py). Such a pair stays in `remaining`; the
                # manual repair path explains why when the user resolves it
                # there. Found in review: without this, the pass linked a
                # categorized on↔on pair with zero validation.
                leg_on = on_budget.get(leg.account_id)
                partner_on = on_budget.get(partner.account_id)
                if (
                    leg_on is None
                    or partner_on is None
                    or linking_breaks_category_rule(
                        leg.category_id is not None,
                        leg_on,
                        partner.category_id is not None,
                        partner_on,
                    )
                ):
                    continue
                leg_before = snapshot("transaction", leg)
                partner_before = snapshot("transaction", partner)
                updated_leg = await self.transaction_repo.update(leg.id, transfer_id=partner.id)
                updated_partner = await self.transaction_repo.update(partner.id, transfer_id=leg.id)
                await self._record_txn(updated_leg, "update", before=leg_before)
                await self._record_txn(updated_partner, "update", before=partner_before)
                claimed.update({leg.id, partner.id})
                linked += 1

        # Counted over the legs the hygiene panel counts, so the three numbers
        # account for exactly the rows it reported: every leg is linked,
        # contested, or left with no candidate at all.
        leg_ids = {leg.id for leg in legs}
        return {
            "linked": linked,
            "ambiguous": len(contested & leg_ids),
            "remaining": len(leg_ids - claimed - contested),
        }

    async def _plan_transfer_edit(
        self,
        budget_id: uuid.UUID,
        txn: Transaction,
        *,
        target_account_id: uuid.UUID | None,
        partner_pick: uuid.UUID | None,
        create_partner: bool,
        category_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Resolve a `transfer_account_id` edit into a concrete plan, or raise.

        Every check lives here, before anything is written: an edit that
        cannot be carried out must not leave one leg of a pair changed.

        Actions: `retarget` (move a linked partner to another account),
        `link` (adopt an existing row as the partner), `create` (write the far
        leg), `break` (unlink a pair, both rows kept), `unmark` (drop an
        orphan leg's transfer payee), `none`.
        """
        current_partner = (
            await self.transaction_repo.get(txn.transfer_id) if txn.transfer_id else None
        )

        if target_account_id is None:
            if current_partner is not None:
                if current_partner.cleared == "reconciled":
                    raise InvariantViolation(
                        "The other side of this transfer is reconciled; unreconcile it first"
                    )
                # Both rows stay — breaking a link must never silently delete
                # money. They keep their transfer payees, so they read as
                # unpaired legs (`is:unpaired`) and can be relinked.
                return {"action": "break", "partner": current_partner}
            payee = await self.payee_repo.get(txn.payee_id) if txn.payee_id else None
            if payee is not None and payee.transfer_account_id is not None:
                return {"action": "unmark"}
            return {"action": "none"}

        target = await self.account_repo.get_or_raise(target_account_id)
        if str(target.budget_id) != str(budget_id):
            raise InvariantViolation("Transfer account does not belong to this budget")
        if target.id == txn.account_id:
            raise InvariantViolation("A transfer needs two different accounts")

        own_account = await self.account_repo.get_or_raise(txn.account_id)
        # Same rule as create — domain/transfers.py — asked leg-wise here,
        # because the category being edited sits on THIS row.
        if category_id is not None and not leg_may_carry_category(
            own_account.on_budget, target.on_budget
        ):
            raise InvariantViolation(
                "Transfers can only be categorized on the on-budget side of an off-budget transfer"
            )

        if current_partner is not None:
            if current_partner.account_id == target.id:
                return {"action": "none"}
            if current_partner.cleared == "reconciled":
                raise InvariantViolation(
                    "The other side of this transfer is reconciled; unreconcile it first"
                )
            return {"action": "retarget", "partner": current_partner, "target": target}

        if partner_pick is not None:
            chosen = await self.transaction_repo.get(partner_pick)
            if chosen is None or str(chosen.budget_id) != str(budget_id):
                raise InvariantViolation("The chosen transfer partner was not found")
            if chosen.id == txn.id:
                raise InvariantViolation("A transaction cannot be its own transfer partner")
            if chosen.account_id != target.id:
                raise InvariantViolation("The chosen partner is not in that account")
            if chosen.transfer_id is not None:
                raise InvariantViolation("The chosen partner is already part of a transfer")
            if chosen.is_split or chosen.parent_transaction_id is not None:
                raise InvariantViolation("A split cannot be a transfer partner")
            if chosen.amount != -txn.amount:
                # Linking rows of different sizes would claim two different
                # amounts are the same movement of money.
                raise InvariantViolation(
                    "The chosen partner's amount is not the opposite of this one"
                )
            return {"action": "link", "partner": chosen, "target": target}

        # High-confidence shape: an unlinked, opposite, same-date row in the
        # target whose own transfer payee points back here.
        matched = await self.transaction_repo.find_transfer_candidates(
            account_id=target.id,
            amount=-txn.amount,
            counterpart_account_id=txn.account_id,
            on_date=txn.date,
        )
        if len(matched) == 1:
            return {"action": "link", "partner": matched[0], "target": target}
        if len(matched) > 1 and not create_partner:
            raise InvariantViolation(
                f"{len(matched)} transactions in {target.name} could be the other side "
                "of this transfer — choose which one to link"
            )

        if not create_partner:
            # Nothing points back, but a plain row (a bank-imported far leg
            # whose payee is "Online Transfer") may still BE the other side.
            # Creating alongside it would double-count the money, so ask.
            plain = [
                c
                for c in await self.transaction_repo.find_transfer_candidates(
                    account_id=target.id, amount=-txn.amount, on_date=txn.date
                )
                if c.id != txn.id
            ]
            if plain:
                raise InvariantViolation(
                    f"{len(plain)} transaction{'s' if len(plain) > 1 else ''} in "
                    f"{target.name} could be the other side of this transfer — "
                    "choose one, or confirm you want a new one written"
                )
        return {"action": "create", "target": target}

    async def _apply_transfer_edit(
        self, budget_id: uuid.UUID, txn: Transaction, plan: dict[str, Any]
    ) -> dict[str, Any]:
        """Carry out a plan from `_plan_transfer_edit`; caller is in a batch.

        Returns the edited row's own field changes for the caller to merge
        into its single update — the partner's are written here.
        """
        action = plan["action"]
        if action == "none":
            return {}
        if action == "unmark":
            return {"payee_id": None}

        partner: Transaction | None = plan.get("partner")
        if action == "break":
            assert partner is not None
            partner_before = snapshot("transaction", partner)
            unlinked = await self.transaction_repo.update(partner.id, transfer_id=None)
            await self._record_txn(unlinked, "update", before=partner_before)
            return {"transfer_id": None}

        target: Account = plan["target"]
        own_account = await self.account_repo.get_or_raise(txn.account_id)
        # Each leg's payee names the OTHER account — that is what a transfer
        # payee means, and what the register renders.
        own_payee = await self._get_transfer_payee(budget_id, target)
        partner_payee = await self._get_transfer_payee(budget_id, own_account)

        if action == "retarget":
            assert partner is not None
            partner_before = snapshot("transaction", partner)
            moved = await self.transaction_repo.update(
                partner.id, account_id=target.id, payee_id=partner_payee.id
            )
            await self._record_txn(moved, "update", before=partner_before)
            return {"payee_id": own_payee.id}

        if action == "link":
            assert partner is not None
            own_fields, partner_fields = transfer_link_fields(
                own_payee.id, partner_payee.id, own_id=txn.id, partner_id=partner.id
            )
            partner_before = snapshot("transaction", partner)
            linked = await self.transaction_repo.update(partner.id, **partner_fields)
            await self._record_txn(linked, "update", before=partner_before)
            return own_fields

        # create: the far leg never existed (a skipped account at import).
        # Uncleared, because nothing has confirmed it at the bank. No
        # category: the plan rejects any pair where this row's category
        # doesn't belong on this side.
        created = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=target.id,
            date=txn.date,
            amount=-txn.amount,
            payee_id=partner_payee.id,
            memo=txn.memo,
            cleared="uncleared",
            approved=txn.approved,
            transfer_id=txn.id,
            created_via=txn.created_via or "manual",
            scheduled_transaction_id=txn.scheduled_transaction_id,
        )
        await self._record_txn(created, "create")
        return {"payee_id": own_payee.id, "transfer_id": created.id}

    async def _get_transfer_payee(self, budget_id: uuid.UUID, account: Account):
        """The "Transfer : <account>" payee, with transfer_account_id set.

        Naming it alone is not enough: `transfer_account_id` is what still
        identifies a row as transfer-shaped after its partner link is gone, and
        it is what keeps transfer payees out of payee pickers and AI
        suggestions.
        """
        return await self.payee_repo.find_or_create_transfer(budget_id, account.id, account.name)

    async def merge(
        self,
        budget_id: uuid.UUID,
        transaction_ids: list[uuid.UUID],
        survivor_id: uuid.UUID | None = None,
    ) -> Transaction:
        """Merge two rows that are the same real-world transaction.

        The one merge: the user's explicit merge and the bank-sync review
        queue's accept both come here. Who survives is domain.merging's
        rule; what a bank-sourced loser contributes is the bank-posting
        rule's (its posted amount replaces the survivor's — this is the
        accepted amount-change review — with the prior amount kept in
        `entered_amount`; its posted date, amount and payee string arrive as
        provenance; an uncleared survivor clears). Everything else is
        additive: the survivor keeps what it has and takes what it lacks —
        memo, category, payee, approval, the loser's attachments, its import
        and bank identity. A merge determines which value wins, never which
        one is lost.

        The loser is soft-deleted before the survivor is written so the
        partial unique index on (account_id, sync_id) never sees two live
        rows. Recorded as one batch, so undo restores both rows and moves
        exactly the loser's attachments back.
        """
        if len(transaction_ids) != 2:
            raise InvariantViolation("Exactly 2 transactions are required for a merge")

        txn1 = await self.transaction_repo.get_or_raise(transaction_ids[0])
        txn2 = await self.transaction_repo.get_or_raise(transaction_ids[1])
        for txn in (txn1, txn2):
            if str(txn.budget_id) != str(budget_id):
                raise InvariantViolation("All transactions must belong to this budget")

        side1, side2 = MergeSide.from_transaction(txn1), MergeSide.from_transaction(txn2)
        survivor_side, deleted_side = choose_survivor(side1, side2, survivor_id)
        violation = survivor_violation(survivor_side, deleted_side, survivor_id)
        if violation is not None:
            raise InvariantViolation(violation)
        survivor = txn1 if survivor_side.id == txn1.id else txn2
        deleted = txn2 if survivor is txn1 else txn1

        updates: dict[str, Any] = {}
        if deleted_side.bank_sourced:
            outcome = posting_updates(
                RowState.from_transaction(survivor),
                FeedRecord.from_transaction(deleted),
                confirmed=True,
            )
            if isinstance(outcome, Review):
                raise InvariantViolation(outcome.reason)
            updates.update(outcome.updates)
        elif survivor.amount != deleted.amount:
            # Neither side speaks for the bank, so nothing arbitrates the
            # difference — and merging would silently change the account
            # balance by it.
            raise InvariantViolation("Only transactions with identical amounts can be merged")

        # Identity and import metadata the survivor lacks.
        if not survivor.import_id and deleted.import_id:
            updates["import_id"] = deleted.import_id
        if not survivor.import_description and deleted.import_description:
            updates.setdefault("import_description", deleted.import_description)
        if not survivor.sync_id and deleted.sync_id:
            updates.setdefault("sync_id", deleted.sync_id)
        if not survivor.sync_source and deleted.sync_source:
            updates.setdefault("sync_source", deleted.sync_source)
        if deleted.has_sync_source or survivor.has_sync_source:
            updates["has_sync_source"] = True

        # Mirror case: survivor is the bank row, the deleted row is manual —
        # keep the user's date once as entered-date provenance.
        if (
            survivor_side.bank_sourced
            and not deleted_side.bank_sourced
            and survivor.entered_date is None
            and deleted.date != survivor.date
        ):
            updates["entered_date"] = deleted.date

        # Bookkeeping is additive. A memo present on both sides and different
        # is kept whole — "survivor — loser" — rather than one being dropped.
        # Category and payee never land on a transfer leg (its payee is its
        # destination and a category is allowed on only one kind of leg), and
        # a split parent's categories live on its lines.
        if deleted.memo and not survivor.memo:
            updates["memo"] = deleted.memo
        elif deleted.memo and survivor.memo and deleted.memo != survivor.memo:
            updates["memo"] = f"{survivor.memo} — {deleted.memo}"
        if survivor.transfer_id is None:
            if survivor.category_id is None and deleted.category_id and not survivor.is_split:
                updates["category_id"] = deleted.category_id
            if survivor.payee_id is None and deleted.payee_id:
                updates["payee_id"] = deleted.payee_id
        if deleted.approved and not survivor.approved:
            updates["approved"] = True

        survivor_before = snapshot("transaction", survivor)
        deleted_before = snapshot("transaction", deleted)
        # Which attachments the loser is contributing — undo moves exactly
        # these back instead of guessing from the survivor's final set.
        if self.attachment_repo is not None:
            deleted_before["_attachment_ids"] = [
                str(a.id) for a in await self.attachment_repo.get_for_transaction(deleted.id)
            ]

        with self.changes.batch():
            # Delete first so the partial unique indexes never see two live
            # rows with the same identity, then write onto the survivor.
            await self.transaction_repo.soft_delete(deleted.id)
            if updates:
                await self.transaction_repo.update(survivor.id, **updates)
            if "cleared" in updates and survivor.is_split:
                await self._mirror_children(survivor.id, cleared=updates["cleared"])

            # The deleted row's attachments belong to the surviving record now.
            if self.attachment_repo is not None:
                await self.attachment_repo.reassign(deleted.id, survivor.id)
            # Pending review matches pointing at the deleted row are moot.
            if self.match_repo is not None:
                await self.match_repo.cancel_pending_for_transaction(deleted.id)

            await self.transaction_repo.refresh(survivor)
            await self._record_txn(deleted, "delete", before=deleted_before, refresh=False)
            await self._record_txn(survivor, "update", before=survivor_before, refresh=False)
        return survivor

    async def _resolve_payee(
        self, budget_id: uuid.UUID, payee_id: uuid.UUID | None, payee_name: str | None
    ) -> Payee | None:
        if payee_id:
            return await self.session.get(Payee, payee_id)
        if not payee_name:
            return None
        # Exact match first
        existing = await self.payee_repo.find_by_name(budget_id, payee_name)
        if existing:
            return existing
        # User-defined regex patterns beat fuzzy matching — they are explicit intent
        by_pattern = await self.payee_repo.find_by_pattern(budget_id, payee_name)
        if by_pattern:
            return by_pattern
        # Fuzzy match against names and mapping_samples
        similar = await self.payee_repo.find_best_match(budget_id, payee_name)
        if similar:
            return similar
        # Create new payee
        return await self.payee_repo.create(budget_id=budget_id, name=payee_name)
