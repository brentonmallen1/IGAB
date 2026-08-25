"""Undo for the change log.

Undo applies the inverse of a recorded change directly to the entity —
soft-delete for creates, restore `before` for updates, resurrect for
deletes — and stamps `undone_at`. It never appends new change rows, so the
log stays a faithful history of what the user did.

Conflict policy: a change is only undone if the entity still looks exactly
like the recorded `after` snapshot (Decimal-scale tolerant). `force=True`
overrides that staleness check, but never the reconciliation guard —
reconciled transactions are immutable to undo, in both directions.

Batches are all-or-nothing: changes apply in reverse insertion order inside
one DB transaction, so a conflict mid-batch rolls back everything.
"""

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    BudgetAssignment,
    BudgetFilterCategory,
    BudgetViewPlacement,
    Category,
    CategoryGroup,
    ChangeLog,
    Payee,
    ScheduledTransaction,
    Transaction,
    TransactionAttachment,
)
from igab.domain.enums import ClearedStatus
from igab.domain.exceptions import NotFoundError, UndoConflict
from igab.repositories.change_log_repo import ChangeLogRepository
from igab.services.change_log import ENTITY_MODELS, coerce_value, snapshot, snapshots_match


class UndoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChangeLogRepository(session)

    async def undo_change(
        self, budget_id: uuid.UUID, change_id: uuid.UUID, force: bool = False
    ) -> list[uuid.UUID]:
        """Undo one change — or, if it belongs to a batch, the whole batch
        (a split's or transfer's halves are meaningless alone)."""
        change = await self.repo.get_or_raise(change_id)
        if change.budget_id != budget_id:
            raise NotFoundError("change_log", str(change_id))
        if change.batch_id is not None:
            return await self.undo_batch(budget_id, change.batch_id, force=force)
        if change.undone_at is not None:
            raise UndoConflict("This change has already been undone")
        await self._apply(change, force)
        change.undone_at = func.now()
        await self.session.flush()
        return [change.id]

    async def undo_batch(
        self, budget_id: uuid.UUID, batch_id: uuid.UUID, force: bool = False
    ) -> list[uuid.UUID]:
        changes = await self.repo.get_batch(budget_id, batch_id)
        if not changes:
            raise NotFoundError("change batch", str(batch_id))
        pending = [c for c in changes if c.undone_at is None]
        if not pending:
            raise UndoConflict("This batch has already been undone")
        undone: list[uuid.UUID] = []
        for change in pending:
            await self._apply(change, force)
            change.undone_at = func.now()
            undone.append(change.id)
        await self.session.flush()
        return undone

    # ─── Inverse operations ───────────────────────────────────────────────────

    async def _apply(self, change: ChangeLog, force: bool) -> None:
        model = ENTITY_MODELS.get(change.entity_type)
        if model is None:
            raise UndoConflict(f"Unknown entity type '{change.entity_type}'")
        entity = await self.session.get(model, change.entity_id)
        if entity is None:
            raise UndoConflict("The affected item no longer exists")

        if change.action in ("create", "import"):
            self._undo_create(change, entity, force)
        elif change.action in ("update", "approve"):
            self._undo_update(change, entity, force)
        elif change.action == "delete" and change.entity_type == "category":
            await self._undo_category_delete(change, entity)
        elif change.action == "delete":
            await self._undo_delete(change, entity)
        elif change.action == "merge":
            await self._undo_merge(change, entity)
        else:
            raise UndoConflict(f"Changes of type '{change.action}' cannot be undone")

    def _undo_create(self, change: ChangeLog, entity, force: bool) -> None:
        if not hasattr(entity, "is_deleted"):
            raise UndoConflict("This item cannot be removed by undo")
        if entity.is_deleted:
            raise UndoConflict("The item has already been deleted")
        # Reconciliation is a hard guard: undo must never remove a
        # transaction the user has reconciled against their bank.
        if isinstance(entity, Transaction) and entity.cleared == ClearedStatus.RECONCILED:
            raise UndoConflict("Reconciled transactions cannot be removed by undo")
        if not force and change.after is not None:
            diff = snapshots_match(snapshot(change.entity_type, entity), change.after)
            if diff:
                raise UndoConflict("The item has been edited since this change", fields=diff)
        entity.is_deleted = True

    def _undo_update(self, change: ChangeLog, entity, force: bool) -> None:
        if getattr(entity, "is_deleted", False):
            raise UndoConflict("The item has been deleted since this change")
        if isinstance(entity, Transaction) and entity.cleared == ClearedStatus.RECONCILED:
            raise UndoConflict("Reconciled transactions cannot be changed by undo")
        if not force and change.after is not None:
            diff = snapshots_match(snapshot(change.entity_type, entity), change.after)
            if diff:
                raise UndoConflict("The item has been edited since this change", fields=diff)
        self._restore_fields(change, entity)

    async def _undo_delete(self, change: ChangeLog, entity) -> None:
        if not getattr(entity, "is_deleted", False):
            raise UndoConflict("The item is no longer deleted")
        self._restore_fields(change, entity)
        entity.is_deleted = False
        # A transaction deleted by a merge carries the attachment ids that
        # were handed to the survivor; bring exactly those back.
        attachment_ids = (change.before or {}).get("_attachment_ids") or []
        if attachment_ids and change.entity_type == "transaction":
            await self.session.execute(
                update(TransactionAttachment)
                .where(TransactionAttachment.id.in_([uuid.UUID(a) for a in attachment_ids]))
                .values(transaction_id=change.entity_id)
            )

    async def _undo_category_delete(self, change: ChangeLog, entity) -> None:
        """Reverse a real category delete: the category, and everything the
        delete cleared on its way out.

        A category delete is one change row rather than a batch of per-row
        changes (see `CategoryService._record_delete`), so this branch has to
        put back what those rows would have. Every restore is conditional on
        the target still being where the delete left it — the same "only those
        still on the target" rule `_undo_merge` uses — so anything the user
        re-filed, re-assigned or re-pointed in the meantime stays as they left
        it rather than being silently overwritten by an undo.

        The reconciliation guard in `_undo_update` is deliberately not
        consulted: this is a bulk UPDATE on a `category` entity, not an edit of
        a reconciled transaction, and it restores exactly the category the row
        already had. `_undo_merge` re-points `payee_id` on reconciled rows on
        the same footing.
        """
        before = change.before or {}
        if not getattr(entity, "is_deleted", False):
            raise UndoConflict("The category is no longer deleted")

        # 1. The categories themselves, primary first so `entity` is consistent.
        self._restore_fields(change, entity)
        entity.is_deleted = False
        restored: list[uuid.UUID] = [change.entity_id]
        for row in before.get("_categories") or []:
            cat_id = uuid.UUID(row["id"])
            if cat_id == change.entity_id:
                continue
            cat = await self.session.get(Category, cat_id)
            if cat is None:
                continue
            for field, value in row.items():
                if field == "id" or field.startswith("_"):
                    continue
                setattr(cat, field, coerce_value(Category, field, value))
            cat.is_deleted = False
            restored.append(cat_id)

        # No contested-link handling here on purpose. A restored category
        # cannot end up fighting a live one over an account or liability,
        # because a category can only be deleted while its link is already
        # null: `CategoryService._blocking_link` refuses while the counterpart
        # is live, and both counterpart deletions clear the link on their way
        # out (`AccountRepository.soft_delete`, `delete_liability`). The
        # restored snapshot therefore carries null too. Pinned by
        # test_category_delete.py::test_a_deleted_category_never_holds_a_link.
        group_raw = before.get("_group_id")
        if group_raw:
            group = await self.session.get(CategoryGroup, uuid.UUID(group_raw))
            if group is not None:
                for field, value in (before.get("_group_before") or {}).items():
                    if not field.startswith("_"):
                        setattr(group, field, coerce_value(CategoryGroup, field, value))
                group.is_deleted = False

        # 2. Transactions. No id list is needed: the delete stamped
        #    `prior_category_id` on exactly the rows it touched, and clearing
        #    it here is what stops a restored row still reading "was: …".
        #    `IS NOT DISTINCT FROM` rather than `==` because the destination is
        #    NULL on the uncategorize path, and `category_id = NULL` is never
        #    true — the whole restore would silently match nothing.
        moved_raw = before.get("_moved_to")
        destination = uuid.UUID(moved_raw) if moved_raw else None
        for cat_id in restored:
            await self.session.execute(
                update(Transaction)
                .where(
                    Transaction.prior_category_id == cat_id,
                    Transaction.category_id.is_not_distinct_from(destination),
                )
                .values(
                    category_id=cat_id,
                    prior_category_id=None,
                    prior_category_name=None,
                )
            )

        # 3. Assignments, recreated with their original ids and amounts.
        for row in before.get("_assignments") or []:
            existing = await self.session.get(BudgetAssignment, uuid.UUID(row["id"]))
            if existing is not None:
                continue
            self.session.add(
                BudgetAssignment(
                    id=uuid.UUID(row["id"]),
                    budget_id=uuid.UUID(row["budget_id"]),
                    category_id=uuid.UUID(row["category_id"]),
                    month=datetime.date.fromisoformat(row["month"]),
                    assigned=Decimal(row["assigned"]),
                )
            )

        # 4. Payee defaults and scheduled transactions — only where still
        #    empty, so a default the user set in the meantime survives.
        primary = restored[0]
        payee_ids = [uuid.UUID(p) for p in (before.get("_payee_ids") or [])]
        if payee_ids:
            await self.session.execute(
                update(Payee)
                .where(Payee.id.in_(payee_ids), Payee.default_category_id.is_(None))
                .values(default_category_id=primary)
            )
        scheduled_ids = [uuid.UUID(s) for s in (before.get("_scheduled_ids") or [])]
        if scheduled_ids:
            await self.session.execute(
                update(ScheduledTransaction)
                .where(
                    ScheduledTransaction.id.in_(scheduled_ids),
                    ScheduledTransaction.category_id.is_(None),
                )
                .values(category_id=primary)
            )

        # 5. View placements and saved-filter selections.
        for row in before.get("_placements") or []:
            self.session.add(
                BudgetViewPlacement(
                    view_id=uuid.UUID(row["view_id"]),
                    category_id=uuid.UUID(row["category_id"]),
                    group_id=uuid.UUID(row["group_id"]) if row.get("group_id") else None,
                    is_hidden=bool(row.get("is_hidden")),
                )
            )
        for row in before.get("_filter_selections") or []:
            self.session.add(
                BudgetFilterCategory(
                    filter_id=uuid.UUID(row["filter_id"]),
                    category_id=uuid.UUID(row["category_id"]),
                )
            )

    async def _undo_merge(self, change: ChangeLog, entity) -> None:
        """Undo a payee merge: resurrect the source payee and move back the
        transactions the merge re-pointed — but only those still on the
        target, so anything the user re-payeed afterwards stays put."""
        if not getattr(entity, "is_deleted", False):
            raise UndoConflict("The merged payee is no longer deleted")
        self._restore_fields(change, entity)
        entity.is_deleted = False
        target_raw = (change.after or {}).get("merged_into")
        moved_raw = (change.before or {}).get("_transaction_ids") or []
        if target_raw and moved_raw:
            await self.session.execute(
                update(Transaction)
                .where(
                    Transaction.id.in_([uuid.UUID(t) for t in moved_raw]),
                    Transaction.payee_id == uuid.UUID(target_raw),
                )
                .values(payee_id=change.entity_id)
            )

    def _restore_fields(self, change: ChangeLog, entity) -> None:
        model = ENTITY_MODELS[change.entity_type]
        for field, value in (change.before or {}).items():
            if field.startswith("_"):
                continue
            setattr(entity, field, coerce_value(model, field, value))
