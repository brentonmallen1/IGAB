from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, Payee, Transaction
from igab.domain.exceptions import InvariantViolation
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
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

    async def create(self, budget_id: uuid.UUID, data: TransactionCreate) -> Transaction:
        account = await self.account_repo.get_or_raise(data.account_id)
        if str(account.budget_id) != str(budget_id):
            raise InvariantViolation("Account does not belong to this budget")

        # Body-supplied ids bypass the route's BudgetAccess guard; reject any
        # that point at another budget's category/payee before persisting.
        await require_in_budget(self.session, Category, data.category_id, budget_id, "Category")
        await require_in_budget(self.session, Payee, data.payee_id, budget_id, "Payee")

        if data.transfer_account_id:
            return await self._create_transfer(budget_id, data)

        # Resolve or create payee
        payee = await self._resolve_payee(budget_id, data)
        payee_id = payee.id if payee else None

        # Auto-categorization: use the most recent category for this payee.
        # Falls back to default_category_id for new payees with no transaction history.
        category_id = data.category_id
        if payee and not category_id:
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
            created_via=data.created_via,
            latitude=data.latitude,
            longitude=data.longitude,
        )
        return txn

    async def create_split(
        self, budget_id: uuid.UUID, header: TransactionCreate, splits: list[TransactionCreate]
    ) -> Transaction:
        """Create a split transaction: one parent + N children."""
        total = sum(s.amount for s in splits)
        if abs(total - header.amount) > Decimal("0.001"):
            raise InvariantViolation(
                f"Split amounts {total} do not sum to transaction amount {header.amount}"
            )

        # Parent has no category (it's distributed across splits). Auto-
        # categorization in create() may have applied a payee default, so
        # force category back to NULL alongside the is_split flag.
        header.category_id = None
        parent = await self.create(budget_id, header)
        await self.transaction_repo.update(parent.id, is_split=True, category_id=None)

        for split in splits:
            split.parent_transaction_id = parent.id
            split.account_id = header.account_id
            # Children mirror the parent's date and posting state so account
            # balances (parent rows) and category activity (leaf rows) always
            # agree on when the money moved.
            split.date = header.date
            split.cleared = header.cleared
            split.approved = header.approved
            await self.create(budget_id, split)

        await self.session.refresh(parent)
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

        total = sum(s.amount for s in splits)
        if abs(total - txn.amount) > Decimal("0.001"):
            raise InvariantViolation(
                f"Split amounts {total} do not sum to transaction amount {txn.amount}"
            )

        for split in splits:
            await require_in_budget(
                self.session, Category, split.category_id, budget_id, "Category"
            )

        await self.transaction_repo.update(txn.id, is_split=True, category_id=None)
        for split in splits:
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
            )

        await self.session.refresh(txn)
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
        for field in _REQUIRED_FIELDS:
            if field in changes and changes[field] is None:
                raise InvariantViolation(f"{field} cannot be empty")

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
            if changes.get("category_id") is not None:
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

        # Keep the transfer pair zero-sum and date-aligned.
        if partner is not None:
            partner_changes: dict[str, Any] = {}
            if "amount" in changes:
                partner_changes["amount"] = -changes["amount"]
            if "date" in changes:
                partner_changes["date"] = changes["date"]
            if partner_changes:
                await self.transaction_repo.update(partner.id, **partner_changes)

        # Propagate parent date/cleared to children (mirror invariant).
        if txn.is_split and ({"date", "cleared"} & changes.keys()):
            child_changes = {k: changes[k] for k in ("date", "cleared") if k in changes}
            for child in await self.transaction_repo.get_splits(txn.id):
                await self.transaction_repo.update(child.id, **child_changes)

        return await self.transaction_repo.update(transaction_id, **changes)

    async def delete(self, budget_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared == "reconciled":
            raise InvariantViolation("Cannot delete a reconciled transaction")
        if txn.parent_transaction_id is not None:
            raise InvariantViolation(
                "Delete the split's parent transaction (or edit its lines) instead"
            )

        # Soft delete transfer partner too — unless it's reconciled.
        if txn.transfer_id:
            partner = await self.transaction_repo.get(txn.transfer_id)
            if partner is not None:
                if partner.cleared == "reconciled":
                    raise InvariantViolation(
                        "The other side of this transfer is reconciled; unreconcile it first"
                    )
                await self.transaction_repo.soft_delete(partner.id)

        # Soft delete any splits (children mirror the parent's cleared state,
        # so a non-reconciled parent implies non-reconciled children).
        splits = await self.transaction_repo.get_splits(transaction_id)
        for split in splits:
            await self.transaction_repo.soft_delete(split.id)

        if self.match_repo is not None:
            await self.match_repo.cancel_pending_for_transaction(transaction_id)

        await self.transaction_repo.soft_delete(transaction_id)

    async def unreconcile(self, budget_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        """Unlock a reconciled transaction back to cleared (explicit user action)."""
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared != "reconciled":
            raise InvariantViolation("Transaction is not reconciled")

        if txn.is_split:
            for child in await self.transaction_repo.get_splits(txn.id):
                if child.cleared == "reconciled":
                    await self.transaction_repo.update(child.id, cleared="cleared")
        return await self.transaction_repo.update(transaction_id, cleared="cleared")

    async def approve(self, transaction_id: uuid.UUID, budget_id: uuid.UUID | None = None):
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if budget_id is not None and str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        return await self.transaction_repo.update(transaction_id, approved=True)

    async def _create_transfer(self, budget_id: uuid.UUID, data: TransactionCreate) -> Transaction:
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
        from_payee = await self._get_transfer_payee(budget_id, to_account.name)
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
        to_payee = await self._get_transfer_payee(budget_id, from_account.name)
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
        await self.session.refresh(source)
        return source

    async def _get_transfer_payee(self, budget_id: uuid.UUID, account_name: str):
        name = f"Transfer : {account_name}"
        return await self.payee_repo.find_or_create(budget_id, name)

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
            updates["sync_source"] = deleted.sync_source
        if deleted.has_sync_source or survivor.has_sync_source:
            updates["has_sync_source"] = True

        # The survivor's ledger date is never touched — it is the date the
        # user chose by picking the survivor. Bank provenance follows the
        # merge as metadata instead.
        if survivor.bank_posted_date is None:
            inherited = deleted.bank_posted_date or (deleted.date if deleted.sync_id else None)
            if inherited is not None:
                updates["bank_posted_date"] = inherited
        # Mirror case: survivor is the bank row, the deleted row is manual —
        # keep the user's date once as entered-date provenance.
        if (
            survivor.sync_id
            and not deleted.sync_id
            and survivor.entered_date is None
            and deleted.date != survivor.date
        ):
            updates["entered_date"] = deleted.date

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

        await self.session.refresh(survivor)
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
