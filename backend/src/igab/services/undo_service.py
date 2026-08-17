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

import uuid

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import ChangeLog, Transaction, TransactionAttachment
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
