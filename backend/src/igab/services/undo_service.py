"""Undo for the change log.

Undo applies the inverse of a recorded change directly to the entity —
soft-delete for creates, restore `before` for updates, resurrect for
deletes — and stamps `undone_at`. It never appends new change rows, so the
log stays a faithful history of what the user did.

Conflict policy: a change is only undone if the entity still looks exactly
like the recorded `after` snapshot (Decimal-scale tolerant). `force=True`
overrides that staleness check, but never the reconciliation guard —
the money on reconciled transactions is immutable to undo, in both
directions (see domain.reconciliation); their bookkeeping is not.

Batches are all-or-nothing: changes apply in reverse insertion order inside
one DB transaction, so a conflict mid-batch rolls back everything.
"""

import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    BudgetAssignment,
    BudgetFilterCategory,
    BudgetMove,
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
from igab.domain.reconciliation import RECONCILED_LOCKED_FIELDS, locked_changes
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.repositories.change_log_repo import ChangeLogRepository
from igab.services.change_log import ENTITY_MODELS, coerce_value, snapshot, snapshots_match


def _opt_uuid(value: object) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


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
            # One flush per step, so the reverse order is the order the
            # database sees. A merge's batch is "delete the loser, then write
            # its bank id onto the survivor"; undone in one flush, the unit of
            # work may revive the loser before the survivor gives the id
            # back, and the partial unique index on (account_id, sync_id)
            # refuses two live rows with it.
            await self.session.flush()
        return undone

    async def undo_newer(
        self,
        budget_id: uuid.UUID,
        change_id: uuid.UUID,
        force: bool = False,
        dry_run: bool = False,
    ) -> list[uuid.UUID]:
        """Undo everything recorded after `change_id`, which itself survives.

        This is the Activity page's line between two entries: the id passed is
        the newest entry BELOW the line, and everything above it goes. Putting
        the control between two rows rather than on one is what makes the
        question "does it include the one I clicked?" unaskable.

        `dry_run` returns the same ids without touching anything, so the
        confirmation's count comes from this selection rather than from a
        second one that could disagree with it.

        A batch is undone as a unit everywhere else, so the boundary snaps to
        the END of the target's batch: an id from the middle of one can never
        leave half a transfer or half a split reverted.
        """
        target = await self.repo.get_or_raise(change_id)
        if target.budget_id != budget_id:
            raise NotFoundError("change_log", str(change_id))
        boundary = target.seq
        if target.batch_id is not None:
            siblings = await self.repo.get_batch(budget_id, target.batch_id)
            if siblings:
                boundary = siblings[0].seq  # get_batch is seq-descending
        pending = await self.repo.list_live_after(budget_id, boundary)
        if not pending:
            raise UndoConflict("Nothing has been recorded since that point")
        if dry_run:
            return [c.id for c in pending]
        undone: list[uuid.UUID] = []
        for change in pending:
            await self._apply(change, force)
            change.undone_at = func.now()
            undone.append(change.id)
            # One flush per step, for the same reason undo_batch does it: the
            # database must see the reversals in the order they are applied.
            await self.session.flush()
        return undone

    async def undo_move(self, budget_id: uuid.UUID, move_id: uuid.UUID) -> list[uuid.UUID]:
        """Undo one budget move, whatever batch it sits in.

        A move from a bulk assign shares its batch with every sibling, and
        undoing that batch would be far more than "take this one back". So a
        move is reversed by its own two rows, and by DELTA rather than by
        restoring `before`: a later move through the same category keeps its
        effect, which a snapshot restore would silently wipe. The rows are
        stamped undone (⌘Z will not reverse them again), the audit row is
        deleted so the move leaves the month's list, and — as with every
        undo — no new rows are written, so this is not itself undoable."""
        move = await self.session.get(BudgetMove, move_id)
        if move is None or move.budget_id != budget_id:
            raise NotFoundError("budget move", str(move_id))
        rows = await self.repo.get_for_move(budget_id, move_id)
        if not rows:
            # Recorded before moves were linked to their change rows: there is
            # nothing to reverse it by, and dropping the row would hide money.
            raise UndoConflict("This move was recorded before per-move undo existed")
        # Rows already undone through the log (⌘Z, the Activity page) have
        # reversed the money; only the audit row is left to drop.
        pending = [r for r in rows if r.undone_at is None]
        undone: list[uuid.UUID] = []
        for row in pending:
            entity = await self.session.get(BudgetAssignment, row.entity_id)
            if entity is None:
                raise UndoConflict("The affected category no longer exists")
            delta = Decimal(str((row.after or {})["assigned"])) - Decimal(
                str((row.before or {})["assigned"])
            )
            entity.assigned = entity.assigned - delta
            row.undone_at = func.now()
            undone.append(row.id)
        await self.session.delete(move)
        await self.session.flush()
        return undone

    async def redo_latest(self, budget_id: uuid.UUID, force: bool = False) -> list[uuid.UUID]:
        """Re-apply the most recently undone change (its whole batch, if it
        had one). Refused when anything has been recorded since the undo:
        a new action empties the redo stack, as in any editor."""
        candidate = await self.repo.latest_undone(budget_id)
        if candidate is None:
            raise UndoConflict("Nothing to redo")
        if await self.repo.count_live_after(budget_id, candidate.undone_at) > 0:
            raise UndoConflict("Nothing to redo — something changed since that undo")
        rows = (
            await self.repo.get_batch(budget_id, candidate.batch_id)
            if candidate.batch_id is not None
            else [candidate]
        )
        # Redo replays in insertion order, the reverse of undo
        pending = sorted((r for r in rows if r.undone_at is not None), key=lambda r: r.seq)
        redone: list[uuid.UUID] = []
        for change in pending:
            await self._reapply(change, force)
            change.undone_at = None
            redone.append(change.id)
        await self.session.flush()
        return redone

    async def _reapply(self, change: ChangeLog, force: bool) -> None:
        model = ENTITY_MODELS.get(change.entity_type)
        if model is None:
            raise UndoConflict(f"Unknown entity type '{change.entity_type}'")
        entity: Any = await self.session.get(model, change.entity_id)
        if entity is None:
            raise UndoConflict("The affected item no longer exists")
        if change.action in ("create", "import"):
            if not getattr(entity, "is_deleted", False):
                raise UndoConflict("The item is already present")
            entity.is_deleted = False
        elif change.action in ("update", "approve"):
            skip = self._reconciled_skip(entity, change, "redo")
            if not force and change.before is not None:
                diff = snapshots_match(snapshot(change.entity_type, entity), change.before)
                diff = [f for f in diff if f not in skip]
                if diff:
                    raise UndoConflict("The item has been edited since this undo", fields=diff)
            for field, value in (change.after or {}).items():
                if field.startswith("_") or field in skip:
                    continue
                setattr(entity, field, coerce_value(model, field, value))
            if change.entity_type == "assignment":
                await self._remember_move(change)
        elif change.action == "delete" and change.entity_type != "category":
            if getattr(entity, "is_deleted", False):
                raise UndoConflict("The item is already deleted")
            entity.is_deleted = True
        elif change.action == "reorder":
            await self._apply_order(change, force, target="after")
        elif change.action in ("archive", "unarchive"):
            await self._apply_archive(change, target="after")
        else:
            raise UndoConflict(f"Changes of type '{change.action}' cannot be redone")

    async def _remember_move(self, change: ChangeLog) -> None:
        """Redo of a move's row puts the audit row back, under its original id,
        so undo can find it again."""
        after = change.after or {}
        raw_id, data = after.get("_move_id"), after.get("_move")
        if not raw_id or not data:
            return
        move_id = uuid.UUID(str(raw_id))
        if await self.session.get(BudgetMove, move_id) is not None:
            return
        self.session.add(
            BudgetMove(
                id=move_id,
                budget_id=change.budget_id,
                month=datetime.date.fromisoformat(data["month"]),
                from_category_id=_opt_uuid(data.get("from_category_id")),
                to_category_id=_opt_uuid(data.get("to_category_id")),
                amount=Decimal(str(data["amount"])),
            )
        )
        # Both of a move's rows call this; a pending add is invisible to
        # session.get until flushed, so flush now or the second side re-adds it.
        await self.session.flush()

    async def _forget_move(self, change: ChangeLog) -> None:
        """An assignment row undone through the log (⌘Z, the Activity page, a
        batch) takes its budget move out of the month's list with it."""
        raw = (change.after or {}).get("_move_id")
        if not raw:
            return
        move = await self.session.get(BudgetMove, uuid.UUID(str(raw)))
        if move is not None:
            await self.session.delete(move)

    # ─── Inverse operations ───────────────────────────────────────────────────

    async def _apply(self, change: ChangeLog, force: bool) -> None:
        model = ENTITY_MODELS.get(change.entity_type)
        if model is None:
            raise UndoConflict(f"Unknown entity type '{change.entity_type}'")
        entity = await self.session.get(model, change.entity_id)
        if entity is None:
            # A hard delete removed the row outright, so there is no flag to
            # flip back — the record carries what to rebuild from. Only a
            # category delete takes that path, and only when nothing recorded
            # that the category existed, which is why rebuilding the bare rows
            # is a complete inverse here and would not be anywhere else.
            if (change.before or {}).get("_hard") and change.entity_type == "category":
                await self._undo_hard_category_delete(change)
                return
            raise UndoConflict("The affected item no longer exists")

        if change.action in ("create", "import"):
            self._undo_create(change, entity, force)
        elif change.action in ("update", "approve"):
            self._undo_update(change, entity, force)
            if change.entity_type == "assignment":
                await self._forget_move(change)
        elif change.action == "delete" and change.entity_type == "category":
            await self._undo_category_delete(change, entity)
        elif change.action == "delete":
            await self._undo_delete(change, entity)
        elif change.action == "merge":
            await self._undo_merge(change, entity)
        elif change.action == "reorder":
            await self._apply_order(change, force, target="before")
        elif change.action in ("archive", "unarchive"):
            await self._apply_archive(change, target="before")
        else:
            raise UndoConflict(f"Changes of type '{change.action}' cannot be undone")

    async def _apply_archive(self, change: ChangeLog, *, target: str) -> None:
        """Put the archived flag and its stamp back for every row one archive touched.

        Recorded keyed by id because a single archive covers many envelopes —
        the shape a bulk delete already uses — where the generic update path
        reads a flat field dict. Without this case both `_apply` and `_reapply`
        fell through to "cannot be undone", and `undo_newer` has no per-item
        handling, so one archive anywhere in the range aborted the whole
        "Revert to here".

        Covers groups as well as categories: `_set_group_archived` records in
        the same shape under `entity_type="category_group"`, so the model comes
        from `ENTITY_MODELS` rather than being assumed.
        """
        model = ENTITY_MODELS[change.entity_type]
        for raw_id, fields in (getattr(change, target) or {}).items():
            entity = await self.session.get(model, uuid.UUID(str(raw_id)))
            if entity is None:
                continue
            for name, value in fields.items():
                setattr(entity, name, coerce_value(model, name, value))

    async def _apply_order(self, change: ChangeLog, force: bool, *, target: str) -> None:
        """Put a reordered list back the way the record says.

        `_order` is bookkeeping, hidden from `snapshots_match`, so staleness is
        checked here: the rows the record knows about must still stand in the
        order this step left them (`after` for an undo, `before` for a redo)
        unless `force`. Rows created since go to the end and rows deleted
        since are skipped — an undo of "move Groceries up" must not lose a
        category added an hour later, nor fail because one was deleted. The
        restore goes through the same repository `reorder` the endpoint uses.
        """
        expected_key = "after" if target == "before" else "before"
        expected = [uuid.UUID(x) for x in (getattr(change, expected_key) or {}).get("_order", [])]
        wanted = [uuid.UUID(x) for x in (getattr(change, target) or {}).get("_order", [])]
        if change.entity_type == "budget":
            groups = CategoryGroupRepository(self.session)
            live = [g.id for g in await groups.get_all(change.entity_id, include_archived=True)]
        elif change.entity_type == "category_group":
            categories = CategoryRepository(self.session)
            live = [c.id for c in await categories.get_by_group(change.entity_id)]
        else:
            raise UndoConflict("This reorder cannot be undone")

        live_set, expected_set = set(live), set(expected)
        still_there = [i for i in live if i in expected_set]
        if not force and still_there != [i for i in expected if i in live_set]:
            raise UndoConflict("The order has changed since this reorder")
        wanted_set = set(wanted)
        restored = [i for i in wanted if i in live_set] + [i for i in live if i not in wanted_set]
        if change.entity_type == "budget":
            await CategoryGroupRepository(self.session).reorder(change.entity_id, restored)
        else:
            await CategoryRepository(self.session).reorder(change.entity_id, restored)

    def _undo_create(self, change: ChangeLog, entity, force: bool) -> None:
        if not hasattr(entity, "is_deleted"):
            raise UndoConflict("This item cannot be removed by undo")
        if entity.is_deleted:
            raise UndoConflict("The item has already been deleted")
        # Reconciliation is a hard guard on money: undo must never remove a
        # transaction the user has reconciled against their bank. A split line
        # is not money — its parent carries the balance — so lines under a
        # reconciled parent may still go: re-splitting is bookkeeping, and
        # bookkeeping has to stay undoable.
        if (
            isinstance(entity, Transaction)
            and entity.cleared == ClearedStatus.RECONCILED
            and entity.parent_transaction_id is None
        ):
            raise UndoConflict("Reconciled transactions cannot be removed by undo")
        if not force and change.after is not None:
            diff = snapshots_match(snapshot(change.entity_type, entity), change.after)
            if diff:
                raise UndoConflict("The item has been edited since this change", fields=diff)
        entity.is_deleted = True

    def _undo_update(self, change: ChangeLog, entity, force: bool) -> None:
        if getattr(entity, "is_deleted", False):
            raise UndoConflict("The item has been deleted since this change")
        skip = self._reconciled_skip(entity, change, "undo")
        if not force and change.after is not None:
            diff = snapshots_match(snapshot(change.entity_type, entity), change.after)
            diff = [f for f in diff if f not in skip]
            if diff:
                raise UndoConflict("The item has been edited since this change", fields=diff)
        self._restore_fields(change, entity, skip=skip)

    @staticmethod
    def _reconciled_skip(entity: Any, change: ChangeLog, verb: str) -> frozenset[str]:
        """Fields undo/redo must leave alone on a reconciled transaction.

        The one rule in domain.reconciliation, applied to what this change
        itself moved: a step that changed the amount (or date, cleared,
        account) cannot be reverted while the row is reconciled. A step that
        changed only bookkeeping can — but its snapshots predate
        reconciliation, so the locked fields are neither compared (the
        reconcile itself is not an "edit since") nor written back (restoring
        the old `cleared` would quietly unreconcile the row).
        """
        if not (isinstance(entity, Transaction) and entity.cleared == ClearedStatus.RECONCILED):
            return frozenset()

        def typed(snap: dict[str, Any] | None) -> dict[str, Any]:
            return {
                f: coerce_value(Transaction, f, v)
                for f, v in (snap or {}).items()
                if f in RECONCILED_LOCKED_FIELDS
            }

        moved = locked_changes(typed(change.before), typed(change.after))
        if moved:
            raise UndoConflict(
                "Reconciled transactions cannot have "
                + ", ".join(sorted(moved))
                + f" changed by {verb}; unlock the transaction first"
            )
        return RECONCILED_LOCKED_FIELDS

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

    async def _undo_hard_category_delete(self, change: ChangeLog) -> None:
        """Rebuild categories (and their group) that were removed outright.

        `CategoryService` only hard-deletes when the preview says nothing
        recorded the category — no transactions, no assignments, no money
        moves, no wishes, no saved-view placement. So there is nothing to
        re-point afterwards and the rows themselves are the whole inverse.

        Ids are restored as they were rather than reissued: a change row and a
        `_categories` payload both name them, and a rebuilt category with a new
        id would leave those pointing at nothing.
        """
        before = change.before or {}
        rows = before.get("_categories") or []
        if not rows:
            raise UndoConflict("This delete did not record what to restore")

        group_payload = before.get("_group")
        if group_payload:
            group_id = uuid.UUID(group_payload["id"])
            if await self.session.get(CategoryGroup, group_id) is None:
                self.session.add(
                    CategoryGroup(
                        id=group_id,
                        budget_id=change.budget_id,
                        **{
                            f: coerce_value(CategoryGroup, f, v)
                            for f, v in group_payload.items()
                            if f != "id"
                        },
                    )
                )
                await self.session.flush()

        for row in rows:
            cat_id = uuid.UUID(row["id"])
            if await self.session.get(Category, cat_id) is not None:
                # Something already put it back. Leave it as it stands rather
                # than overwriting — the rule every other branch here follows.
                continue
            self.session.add(
                Category(
                    id=cat_id,
                    budget_id=change.budget_id,
                    **{f: coerce_value(Category, f, v) for f, v in row.items() if f != "id"},
                )
            )
        await self.session.flush()

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
        # This branch also serves REPAIR records — hygiene passes over
        # categories deleted long before the repair ran. Undoing one still
        # restores the category to the budget, deliberately: re-orphaning
        # (category dead, rows re-filed into it, assignments recreated) would
        # recreate the exact stranded-money corruption the repair exists to
        # fix. A live category is the only coherent inverse, and the repair
        # UI says so. Pinned by
        # test_undoing_a_repair_restores_the_category_to_the_budget.

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

        # 2. Transactions, restored by the exact id list the delete recorded
        #    (`_transactions`), never by `prior_category_id` — provenance is
        #    display-only and single-level, so a later delete of the
        #    destination overwrites it, and an undo keyed on it silently
        #    matched nothing (measured: delete A into B, delete B, undo both
        #    in reverse — the rows stayed in B). The ids don't age like that,
        #    and reverse-order undo walks all the way home.
        #    `IS NOT DISTINCT FROM` rather than `==` because the destination is
        #    NULL on the uncategorize path, and `category_id = NULL` is never
        #    true — the whole restore would silently match nothing.
        moved_raw = before.get("_moved_to")
        destination = uuid.UUID(moved_raw) if moved_raw else None
        moved_map = before.get("_transactions") or {}
        for cat_id in restored:
            txn_ids = [uuid.UUID(t) for t in moved_map.get(str(cat_id), [])]
            # Chunked: a well-used category's list can be thousands of ids and
            # asyncpg caps statement parameters.
            for i in range(0, len(txn_ids), 1000):
                await self.session.execute(
                    update(Transaction)
                    .where(
                        Transaction.id.in_(txn_ids[i : i + 1000]),
                        Transaction.category_id.is_not_distinct_from(destination),
                    )
                    .values(
                        category_id=cat_id,
                        prior_category_id=None,
                        prior_category_name=None,
                    )
                )

        # 2b. The cover the delete granted the destination (move path only)
        #     comes back out — the exact inverse of the recorded deltas, so an
        #     assignment the user edited in between keeps their edit and loses
        #     only what the delete added.
        for row in before.get("_dest_assignment_deltas") or []:
            if destination is None:
                break
            month = datetime.date.fromisoformat(row["month"])
            delta = Decimal(row["delta"])
            existing = (
                await self.session.execute(
                    select(BudgetAssignment).where(
                        BudgetAssignment.category_id == destination,
                        BudgetAssignment.month == month,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.assigned = existing.assigned - delta
            else:
                self.session.add(
                    BudgetAssignment(
                        budget_id=change.budget_id,
                        category_id=destination,
                        month=month,
                        assigned=-delta,
                    )
                )

        # 3. Assignments: add back what the delete removed. Matched by
        #    (category, month) — the unique key — not by row id: an
        #    out-of-order undo can already have written an inverse-delta row
        #    for the same month (2b above), and an id-keyed insert then
        #    collides with it. Additive, so the two undos compose to the
        #    arithmetic truth instead of the last one winning.
        for row in before.get("_assignments") or []:
            month = datetime.date.fromisoformat(row["month"])
            category_id = uuid.UUID(row["category_id"])
            existing = (
                await self.session.execute(
                    select(BudgetAssignment).where(
                        BudgetAssignment.category_id == category_id,
                        BudgetAssignment.month == month,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.assigned = existing.assigned + Decimal(row["assigned"])
            else:
                self.session.add(
                    BudgetAssignment(
                        id=uuid.UUID(row["id"]),
                        budget_id=uuid.UUID(row["budget_id"]),
                        category_id=category_id,
                        month=month,
                        assigned=Decimal(row["assigned"]),
                    )
                )
        await self.session.flush()

        # 4. Payee defaults and scheduled transactions — each restored to the
        #    category IT pointed at (a group cascade clears defaults across
        #    several; measured, restoring them all to the primary filed
        #    Chipotle's default under Groceries) — and only where still empty,
        #    so a default the user set in the meantime survives.
        for payee_raw, cat_raw in (before.get("_payee_defaults") or {}).items():
            await self.session.execute(
                update(Payee)
                .where(
                    Payee.id == uuid.UUID(payee_raw),
                    Payee.default_category_id.is_(None),
                )
                .values(default_category_id=uuid.UUID(cat_raw))
            )
        for sched_raw, cat_raw in (before.get("_scheduled_categories") or {}).items():
            await self.session.execute(
                update(ScheduledTransaction)
                .where(
                    ScheduledTransaction.id == uuid.UUID(sched_raw),
                    ScheduledTransaction.category_id.is_(None),
                )
                .values(category_id=uuid.UUID(cat_raw))
            )

        # 5. View placements and saved-filter selections.
        for row in before.get("_placements") or []:
            self.session.add(
                BudgetViewPlacement(
                    view_id=uuid.UUID(row["view_id"]),
                    category_id=uuid.UUID(row["category_id"]),
                    group_id=uuid.UUID(row["group_id"]) if row.get("group_id") else None,
                    is_hidden=bool(row.get("is_hidden")),
                    sort_order=int(row.get("sort_order") or 0),
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

    def _restore_fields(
        self, change: ChangeLog, entity, skip: frozenset[str] = frozenset()
    ) -> None:
        model = ENTITY_MODELS[change.entity_type]
        for field, value in (change.before or {}).items():
            if field.startswith("_") or field in skip:
                continue
            setattr(entity, field, coerce_value(model, field, value))
