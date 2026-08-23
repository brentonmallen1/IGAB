from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, Payee, Transaction
from igab.domain.exceptions import InvariantViolation
from igab.domain.splits import require_split_balances
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
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
    """One leg of a split conversion — everything else (account, date,
    cleared, approved) is inherited from the parent transaction."""

    amount: Decimal
    category_id: uuid.UUID | None = None
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    memo: str | None = None


# Fields that may never be set to NULL via PATCH
_REQUIRED_FIELDS = ("date", "amount", "cleared", "approved")
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
        await require_in_budget(self.session, Payee, data.payee_id, budget_id, "Payee")

        if data.transfer_account_id:
            return await self._create_transfer(budget_id, data, record=record)

        # Resolve or create payee
        payee = await self._resolve_payee(budget_id, data)
        payee_id = payee.id if payee else None

        # Auto-categorization: use the most recent category for this payee.
        # Falls back to default_category_id for new payees with no transaction history.
        category_id = data.category_id
        if payee and not category_id and data.auto_categorize:
            category_id = await self.transaction_repo.get_most_recent_category_for_payee(
                budget_id, payee.id
            )
            if not category_id and payee.default_category_id:
                category_id = payee.default_category_id

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
            import_id=data.import_id,
            import_batch_id=data.import_batch_id,
            import_description=data.import_description,
            sync_id=data.sync_id,
            sync_source=data.sync_source,
            bank_posted_date=data.bank_posted_date,
            bank_amount=data.bank_amount,
            bank_payee=data.bank_payee,
            created_via=data.created_via,
            latitude=data.latitude,
            longitude=data.longitude,
        )
        if record:
            source = "ai" if data.created_via else ("import" if data.import_batch_id else "manual")
            await self._record_txn(txn, "create", source=source)
        return txn

    async def create_split(
        self, budget_id: uuid.UUID, header: TransactionCreate, splits: list[TransactionCreate]
    ) -> Transaction:
        """Create a split transaction: one parent + N children."""
        require_split_balances(header.amount, [s.amount for s in splits])

        # Parent has no category (it's distributed across splits). Auto-
        # categorization in create() may have applied a payee default, so
        # force category back to NULL alongside the is_split flag.
        header.category_id = None
        parent = await self.create(budget_id, header, record=False)
        await self.transaction_repo.update(parent.id, is_split=True, category_id=None)

        children: list[Transaction] = []
        for split in splits:
            split.parent_transaction_id = parent.id
            split.account_id = header.account_id
            # Children mirror the parent's date and posting state so account
            # balances (parent rows) and category activity (leaf rows) always
            # agree on when the money moved.
            split.date = header.date
            split.cleared = header.cleared
            split.approved = header.approved
            children.append(await self.create(budget_id, split, record=False))

        await self.transaction_repo.refresh(parent)
        # Recorded after the is_split flip so the snapshots hold final state.
        with self.changes.batch():
            await self._record_txn(parent, "create", refresh=False)
            for child in children:
                await self._record_txn(child, "create")
        return parent

    async def convert_to_split(
        self, budget_id: uuid.UUID, transaction_id: uuid.UUID, splits: list[SplitSpec]
    ) -> Transaction:
        """Split an existing transaction in place: the row becomes the parent.

        Unlike create-replacement-and-delete, this preserves the transaction's
        identity — attachments, AI-job links, import/sync ids, and provenance
        all stay put. Receipts made this mandatory: the image is attached to
        the row being split.
        """
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared == "reconciled":
            raise InvariantViolation("Cannot split a reconciled transaction")
        if txn.is_split:
            raise InvariantViolation("Transaction is already split")
        if txn.parent_transaction_id is not None:
            raise InvariantViolation("Cannot split a split child")
        if txn.transfer_id is not None:
            raise InvariantViolation("Cannot split a transfer")

        require_split_balances(txn.amount, [s.amount for s in splits])

        for split in splits:
            await require_in_budget(
                self.session, Category, split.category_id, budget_id, "Category"
            )

        before = snapshot("transaction", txn)
        await self.transaction_repo.update(txn.id, is_split=True, category_id=None)
        children = []
        for split in splits:
            children.append(
                await self.create(
                    budget_id,
                    TransactionCreate(
                        account_id=txn.account_id,
                        date=txn.date,
                        amount=split.amount,
                        category_id=split.category_id,
                        payee_id=split.payee_id,
                        payee_name=split.payee_name,
                        memo=split.memo,
                        cleared=txn.cleared,
                        approved=txn.approved,
                        parent_transaction_id=txn.id,
                    ),
                    record=False,
                )
            )

        await self.transaction_repo.refresh(txn)
        # One batch: undoing it deletes the children and restores the parent's
        # pre-split category and is_split flag.
        with self.changes.batch():
            await self._record_txn(txn, "update", before=before, refresh=False)
            for child in children:
                await self._record_txn(child, "create")
        return txn

    async def update(
        self, budget_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
    ) -> Transaction:
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared == "reconciled":
            raise InvariantViolation("Cannot edit a reconciled transaction")

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
                partner_off_budget = partner_account is not None and not partner_account.on_budget
                if not (own_account.on_budget and partner_off_budget):
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
                for child in await self.transaction_repo.get_splits(txn.id):
                    child_before = snapshot("transaction", child)
                    updated_child = await self.transaction_repo.update(child.id, **child_changes)
                    await self._record_txn(updated_child, "update", before=child_before)

            updated = await self.transaction_repo.update(transaction_id, **changes)
            await self._record_txn(updated, "update", before=before_self)
        return updated

    async def delete(self, budget_id: uuid.UUID, transaction_id: uuid.UUID) -> uuid.UUID:
        """Soft-delete a transaction (plus transfer partner and split
        children). Returns the change-log batch id so callers can offer undo."""
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
                    await self._record_txn(partner, "delete", before=partner_before, refresh=False)

            # Soft delete any splits (children mirror the parent's cleared state,
            # so a non-reconciled parent implies non-reconciled children).
            splits = await self.transaction_repo.get_splits(transaction_id)
            for split in splits:
                split_before = snapshot("transaction", split)
                await self.transaction_repo.soft_delete(split.id)
                await self._record_txn(split, "delete", before=split_before, refresh=False)

            if self.match_repo is not None:
                await self.match_repo.cancel_pending_for_transaction(transaction_id)

            txn_before = snapshot("transaction", txn)
            await self.transaction_repo.soft_delete(transaction_id)
            await self._record_txn(txn, "delete", before=txn_before, refresh=False)
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
                for child in await self.transaction_repo.get_splits(txn.id):
                    if child.cleared == "reconciled":
                        child_before = snapshot("transaction", child)
                        updated_child = await self.transaction_repo.update(
                            child.id, cleared="cleared"
                        )
                        await self._record_txn(updated_child, "update", before=child_before)
            before = snapshot("transaction", txn)
            updated = await self.transaction_repo.update(transaction_id, cleared="cleared")
            await self._record_txn(updated, "update", before=before)
        return updated

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

        # YNAB "spending transfer": a transfer between an on-budget and an
        # off-budget account is real spending/income and may carry a category,
        # which lives on the ON-BUDGET leg. On-budget↔on-budget transfers are
        # internal money movement and can never be categorized.
        category_id = data.category_id
        if category_id is not None and from_account.on_budget == to_account.on_budget:
            raise InvariantViolation(
                "Only transfers between an on-budget and an off-budget account can be categorized"
            )
        source_category = category_id if from_account.on_budget else None
        dest_category = category_id if to_account.on_budget else None

        # Source: outflow from from-account
        from_payee = await self._get_transfer_payee(budget_id, to_account)
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
        # Same rule as create: a categorized transfer is a YNAB spending
        # transfer, and the category lives on the on-budget side of an
        # on↔off pair. Categorizing any other transfer would count internal
        # movement as spending.
        if category_id is not None and not (own_account.on_budget and not target.on_budget):
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
            partner_before = snapshot("transaction", partner)
            linked = await self.transaction_repo.update(
                partner.id, transfer_id=txn.id, payee_id=partner_payee.id
            )
            await self._record_txn(linked, "update", before=partner_before)
            return {"payee_id": own_payee.id, "transfer_id": partner.id}

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
        """Merge two transactions. Survivor keeps its data; import metadata is merged."""
        if len(transaction_ids) != 2:
            raise InvariantViolation("Exactly 2 transactions are required for a merge")

        txn1 = await self.transaction_repo.get_or_raise(transaction_ids[0])
        txn2 = await self.transaction_repo.get_or_raise(transaction_ids[1])

        for txn in (txn1, txn2):
            if str(txn.budget_id) != str(budget_id):
                raise InvariantViolation("All transactions must belong to this budget")
            if txn.is_split or txn.parent_transaction_id:
                raise InvariantViolation("Cannot merge split transactions")
            if txn.transfer_id:
                raise InvariantViolation("Cannot merge transfer transactions")

        if txn1.cleared == "reconciled" and txn2.cleared == "reconciled":
            raise InvariantViolation("Cannot merge two reconciled transactions")

        if txn1.account_id != txn2.account_id:
            raise InvariantViolation("Transactions must be in the same account")

        # A merge asserts "these are the same real-world transaction" — with
        # different amounts that's false, and merging would silently change
        # the account balance by the difference.
        if txn1.amount != txn2.amount:
            raise InvariantViolation("Only transactions with identical amounts can be merged")

        if txn1.sync_id and txn2.sync_id and txn1.sync_id != txn2.sync_id:
            raise InvariantViolation("Both transactions are linked to different bank transactions")

        # When one transaction is reconciled it must always be the survivor
        if txn1.cleared == "reconciled":
            reconciled_txn = txn1
        elif txn2.cleared == "reconciled":
            reconciled_txn = txn2
        else:
            reconciled_txn = None
        if reconciled_txn is not None:
            if survivor_id is not None and survivor_id != reconciled_txn.id:
                raise InvariantViolation("The reconciled transaction must be kept as the survivor")
            survivor = reconciled_txn
            deleted = txn2 if survivor is txn1 else txn1
        elif survivor_id is not None:
            if survivor_id not in transaction_ids:
                raise InvariantViolation("survivor_id must be one of the transaction_ids")
            survivor = txn1 if txn1.id == survivor_id else txn2
            deleted = txn2 if txn1.id == survivor_id else txn1
        else:
            if txn1.created_at <= txn2.created_at:
                survivor, deleted = txn1, txn2
            else:
                survivor, deleted = txn2, txn1

        # Merge import metadata from deleted into survivor if survivor lacks it
        updates: dict = {}
        if not survivor.import_id and deleted.import_id:
            updates["import_id"] = deleted.import_id
        if not survivor.import_description and deleted.import_description:
            updates["import_description"] = deleted.import_description
        if not survivor.sync_id and deleted.sync_id:
            updates["sync_id"] = deleted.sync_id
        # An id-less bank feed row has sync_source but no sync_id — its bank
        # identity still transfers to the survivor.
        if not survivor.sync_source and deleted.sync_source:
            updates["sync_source"] = deleted.sync_source
        if deleted.has_sync_source or survivor.has_sync_source:
            updates["has_sync_source"] = True

        # The survivor's ledger date is never touched — it is the date the
        # user chose by picking the survivor. Bank provenance follows the
        # merge as metadata instead.
        if survivor.bank_posted_date is None:
            deleted_is_bank = bool(deleted.sync_id or deleted.sync_source)
            inherited = deleted.bank_posted_date or (deleted.date if deleted_is_bank else None)
            if inherited is not None:
                updates["bank_posted_date"] = inherited
        if survivor.bank_amount is None:
            deleted_is_bank = bool(deleted.sync_id or deleted.sync_source)
            inherited_amount = deleted.bank_amount or (deleted.amount if deleted_is_bank else None)
            if inherited_amount is not None:
                updates["bank_amount"] = inherited_amount
        if survivor.bank_payee is None and deleted.bank_payee:
            updates["bank_payee"] = deleted.bank_payee
        # Mirror case: survivor is the bank row, the deleted row is manual —
        # keep the user's date once as entered-date provenance.
        if (
            (survivor.sync_id or survivor.sync_source)
            and not (deleted.sync_id or deleted.sync_source)
            and survivor.entered_date is None
            and deleted.date != survivor.date
        ):
            updates["entered_date"] = deleted.date

        survivor_before = snapshot("transaction", survivor)
        deleted_before = snapshot("transaction", deleted)
        # Which attachments the loser is contributing — undo moves exactly
        # these back instead of guessing from the survivor's final set.
        if self.attachment_repo is not None:
            deleted_before["_attachment_ids"] = [
                str(a.id) for a in await self.attachment_repo.get_for_transaction(deleted.id)
            ]

        # Delete first so the partial unique indexes never see two live rows
        # with the same identity, then write metadata onto the survivor.
        await self.transaction_repo.soft_delete(deleted.id)
        if updates:
            await self.transaction_repo.update(survivor.id, **updates)

        # The deleted row's attachments belong to the surviving record now.
        if self.attachment_repo is not None:
            await self.attachment_repo.reassign(deleted.id, survivor.id)
        # Pending review matches pointing at the deleted row are moot.
        if self.match_repo is not None:
            await self.match_repo.cancel_pending_for_transaction(deleted.id)

        await self.transaction_repo.refresh(survivor)
        with self.changes.batch():
            await self._record_txn(deleted, "delete", before=deleted_before, refresh=False)
            await self._record_txn(survivor, "update", before=survivor_before, refresh=False)
        return survivor

    async def _resolve_payee(self, budget_id: uuid.UUID, data: TransactionCreate) -> Payee | None:
        if data.payee_id:
            return await self.session.get(Payee, data.payee_id)
        if not data.payee_name:
            return None
        # Exact match first
        existing = await self.payee_repo.find_by_name(budget_id, data.payee_name)
        if existing:
            return existing
        # User-defined regex patterns beat fuzzy matching — they are explicit intent
        by_pattern = await self.payee_repo.find_by_pattern(budget_id, data.payee_name)
        if by_pattern:
            return by_pattern
        # Fuzzy match against names and mapping_samples
        similar = await self.payee_repo.find_best_match(budget_id, data.payee_name)
        if similar:
            return similar
        # Create new payee
        return await self.payee_repo.create(budget_id=budget_id, name=data.payee_name)
