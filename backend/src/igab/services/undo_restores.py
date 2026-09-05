"""Bookkeeping-payload inverses for the undo service.

The orchestration core (undo_service.py) dispatches; this mixin holds the
restorers that rebuild what a record carries as bookkeeping rather than as
plain fields — hard rows re-inserted under their original ids, a view's
child rows, a tag set, one Guide key or concept, a membership row, a
reconciliation's lock, a rotation's complementary spin. Split from the core
when it crossed the file-length budget; the seam is real: everything here
reads a payload and writes rows, nothing here decides WHAT to undo.
"""

import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    Account,
    Asset,
    BudgetFilterCategory,
    BudgetMember,
    BudgetViewGroup,
    BudgetViewPlacement,
    Category,
    ChangeLog,
    GuideBinding,
    GuideState,
    Liability,
    Tag,
    Transaction,
    category_tags,
    payee_tags,
)
from igab.domain.enums import ClearedStatus
from igab.domain.exceptions import UndoConflict
from igab.services.change_log import (
    ENTITY_MODELS,
    binding_rows_dump,
    coerce_value,
    filter_selection_dump,
    view_children_dump,
)

# Entities whose rows are removed outright rather than soft-deleted: nothing
# references them by id, so a delete leaves no flag to flip back. Undo of a
# delete (and redo of a create) re-inserts the recorded snapshot under its
# original id via `_insert_hard_row`; undo of a create removes the row again.
# The natural key names the columns that make a concurrent replacement
# detectable — a second row on the same key since the delete is a person's
# later decision, and undo refuses rather than fighting the unique index.
HARD_ROW_NATURAL_KEY: dict[str, tuple[str, ...]] = {
    "category_target": ("category_id",),
    "liability_snapshot": ("liability_id", "date"),
    "asset_value": ("asset_id", "date"),
    "account_type": ("budget_id", "key"),
    "reconciliation": ("account_id", "reconciled_at"),
    "category_plan": ("budget_id", "name"),
}

# The FK a re-inserted hard row hangs from. Checked before insert so a
# vanished parent surfaces as a conflict message, never an IntegrityError.
HARD_ROW_PARENT: dict[str, tuple[type, str]] = {
    "category_target": (Category, "category_id"),
    "liability_snapshot": (Liability, "liability_id"),
    "asset_value": (Asset, "asset_id"),
}

# Rows that may point AT a hard row (no ondelete on the FK). Checked before a
# hard delete — undo of a create, redo of a delete — so a referenced row
# refuses with words rather than an IntegrityError.
HARD_ROW_REFERENCERS: dict[str, tuple[Any, str]] = {
    "account_type": (Account, "account_type_id"),
}


class UndoRestores:
    """Mixin over the undo service's session; see the module docstring."""

    session: AsyncSession

    async def _restore_tag_membership(self, change: ChangeLog, *, target: str, force: bool) -> None:
        """Put one category's or payee's tag set back the way the record says.

        The membership rows are hard-replaced by every set, so the record is
        a `_tag_ids` dump per side and staleness is checked here against the
        step's own expected side. Tags deleted since are skipped."""
        assoc = category_tags if change.entity_type == "category_tags" else payee_tags
        owner_col = "category_id" if change.entity_type == "category_tags" else "payee_id"
        current = sorted(
            str(t)
            for t in (
                await self.session.execute(
                    select(assoc.c.tag_id).where(assoc.c[owner_col] == change.entity_id)
                )
            ).scalars()
        )
        expected_side = getattr(change, "after" if target == "before" else "before") or {}
        if not force and current != (expected_side.get("_tag_ids") or []):
            raise UndoConflict("The tags have changed since this change")
        wanted = [uuid.UUID(t) for t in (getattr(change, target) or {}).get("_tag_ids") or []]
        alive: set[uuid.UUID] = set()
        if wanted:
            alive = set(
                (
                    await self.session.execute(
                        select(Tag.id).where(
                            Tag.id.in_(wanted),
                            Tag.is_deleted == False,  # noqa: E712
                        )
                    )
                ).scalars()
            )
        await self.session.execute(delete(assoc).where(assoc.c[owner_col] == change.entity_id))
        for tag_id in wanted:
            if tag_id in alive:
                await self.session.execute(
                    assoc.insert().values(**{owner_col: change.entity_id, "tag_id": tag_id})
                )
        await self.session.flush()
        # See _restore_view_children: same shared-session staleness rule.
        owner = await self.session.get(ENTITY_MODELS[change.entity_type], change.entity_id)
        if owner is not None:
            self.session.expire(owner)

    async def _restore_view_children(self, change: ChangeLog, *, target: str, force: bool) -> None:
        """Put a view's groups and placements back the way the record says.

        The scalar fields went through the generic update path; the children
        are hard-replaced rows, recorded as canonical dumps (invisible to
        `snapshots_match`), so staleness is checked here: the children must
        still stand as this step left them, unless `force`. Placements whose
        category has been deleted since are skipped — the reorder rule.
        Groups keep their recorded ids, because placements reference them.
        """
        payload = getattr(change, target) or {}
        if "_groups" not in payload and "_placements" not in payload:
            return
        expected = getattr(change, "after" if target == "before" else "before") or {}
        groups = list(
            (
                await self.session.execute(
                    select(BudgetViewGroup).where(BudgetViewGroup.view_id == change.entity_id)
                )
            ).scalars()
        )
        placements = list(
            (
                await self.session.execute(
                    select(BudgetViewPlacement).where(
                        BudgetViewPlacement.view_id == change.entity_id
                    )
                )
            ).scalars()
        )
        current = view_children_dump(groups, placements)
        recorded = {k: expected.get(k) for k in ("_groups", "_placements")}
        if not force and current != recorded:
            raise UndoConflict("The view has been rearranged since this change")
        for row in placements:
            await self.session.delete(row)
        for row in groups:
            await self.session.delete(row)
        await self.session.flush()
        wanted_groups = payload.get("_groups") or []
        for g in wanted_groups:
            self.session.add(
                BudgetViewGroup(
                    id=uuid.UUID(g["id"]),
                    view_id=change.entity_id,
                    name=g["name"],
                    sort_order=int(g["sort_order"]),
                )
            )
        await self.session.flush()
        group_ids = {g["id"] for g in wanted_groups}
        wanted_placements = payload.get("_placements") or []
        cat_ids = [uuid.UUID(p["category_id"]) for p in wanted_placements]
        alive: set[uuid.UUID] = set()
        if cat_ids:
            alive = set(
                (
                    await self.session.execute(select(Category.id).where(Category.id.in_(cat_ids)))
                ).scalars()
            )
        for p in wanted_placements:
            cat_id = uuid.UUID(p["category_id"])
            if cat_id not in alive:
                continue
            self.session.add(
                BudgetViewPlacement(
                    view_id=change.entity_id,
                    category_id=cat_id,
                    group_id=uuid.UUID(p["group_id"]) if p.get("group_id") in group_ids else None,
                    sort_order=int(p["sort_order"]),
                    is_hidden=bool(p["is_hidden"]),
                )
            )
        await self.session.flush()
        # Expire the parent's loaded collections: a reader sharing this
        # session (the test harness does; a same-request reader could) must
        # re-query rather than serve the pre-rebuild rows from the identity
        # map — rebuilt children never enter an already-loaded collection.
        parent = await self.session.get(ENTITY_MODELS[change.entity_type], change.entity_id)
        if parent is not None:
            self.session.expire(parent, ["groups", "placements"])

    async def _restore_filter_selections(
        self, change: ChangeLog, *, target: str, force: bool
    ) -> None:
        """The filter analogue of `_restore_view_children`, for its one child
        set: the selected categories."""
        payload = getattr(change, target) or {}
        if "_category_ids" not in payload:
            return
        expected = getattr(change, "after" if target == "before" else "before") or {}
        rows = list(
            (
                await self.session.execute(
                    select(BudgetFilterCategory).where(
                        BudgetFilterCategory.filter_id == change.entity_id
                    )
                )
            ).scalars()
        )
        current = filter_selection_dump(rows)
        if not force and current["_category_ids"] != expected.get("_category_ids"):
            raise UndoConflict("The filter's categories have changed since this change")
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        cat_ids = [uuid.UUID(c) for c in payload.get("_category_ids") or []]
        alive: set[uuid.UUID] = set()
        if cat_ids:
            alive = set(
                (
                    await self.session.execute(select(Category.id).where(Category.id.in_(cat_ids)))
                ).scalars()
            )
        for cat_id in cat_ids:
            if cat_id in alive:
                self.session.add(
                    BudgetFilterCategory(filter_id=change.entity_id, category_id=cat_id)
                )
        await self.session.flush()
        # See _restore_view_children: same shared-session staleness rule.
        parent = await self.session.get(ENTITY_MODELS[change.entity_type], change.entity_id)
        if parent is not None:
            self.session.expire(parent, ["category_selections"])

    async def _undo_reconcile(self, change: ChangeLog, entity) -> None:
        """Unreconcile: flip the locked rows back to cleared, put the
        account's last-reconciled stamp back, and remove the snapshot row.

        `_transaction_ids` names exactly the rows the finish locked; only
        ones still reconciled flip back — one unreconciled by hand since was
        re-decided by a person. The reconciliation guard elsewhere is what
        makes this branch necessary AND safe: a locked row can only come
        back under undo through the very record that locked it.
        """
        after = change.after or {}
        txn_ids = [uuid.UUID(t) for t in after.get("_transaction_ids") or []]
        for i in range(0, len(txn_ids), 1000):
            await self.session.execute(
                update(Transaction)
                .where(
                    Transaction.id.in_(txn_ids[i : i + 1000]),
                    Transaction.cleared == ClearedStatus.RECONCILED,
                )
                .values(cleared="cleared")
            )
        account = await self.session.get(Account, entity.account_id)
        stamp = after.get("_account_before") or {}
        if account is not None:
            account.last_reconciled_at = coerce_value(
                Account, "last_reconciled_at", stamp.get("last_reconciled_at")
            )
            account.last_reconciled_balance = coerce_value(
                Account, "last_reconciled_balance", stamp.get("last_reconciled_balance")
            )
        await self.session.delete(entity)
        await self.session.flush()

    async def _redo_reconcile(self, change: ChangeLog) -> None:
        """Replay a finish the undo reversed: re-insert the snapshot row,
        re-lock the rows it named (only ones still cleared), and re-stamp
        the account."""
        after = change.after or {}
        await self._insert_hard_row(change, "after")
        txn_ids = [uuid.UUID(t) for t in after.get("_transaction_ids") or []]
        for i in range(0, len(txn_ids), 1000):
            await self.session.execute(
                update(Transaction)
                .where(
                    Transaction.id.in_(txn_ids[i : i + 1000]),
                    Transaction.cleared == ClearedStatus.CLEARED,
                )
                .values(cleared="reconciled")
            )
        raw_account = after.get("account_id")
        account = None
        if raw_account:
            account = await self.session.get(Account, uuid.UUID(str(raw_account)))
        stamp = after.get("_account_after") or {}
        if account is not None:
            account.last_reconciled_at = coerce_value(
                Account, "last_reconciled_at", stamp.get("last_reconciled_at")
            )
            account.last_reconciled_balance = coerce_value(
                Account, "last_reconciled_balance", stamp.get("last_reconciled_balance")
            )
        await self.session.flush()

    async def _restore_guide_state(self, change: ChangeLog, *, target: str, force: bool) -> None:
        """Put one Guide state key's value back the way the record says —
        `_value` None means the row was absent (a cleared step)."""
        payload = getattr(change, target) or {}
        key = payload.get("_key")
        if not key:
            raise UndoConflict("This record did not say which setting it moved")
        row = (
            await self.session.execute(
                select(GuideState).where(
                    GuideState.budget_id == change.budget_id, GuideState.key == key
                )
            )
        ).scalar_one_or_none()
        current = row.value if row is not None else None
        expected_side = getattr(change, "after" if target == "before" else "before") or {}
        if not force and current != expected_side.get("_value"):
            raise UndoConflict("The setting has changed since this change")
        wanted = payload.get("_value")
        if wanted is None:
            if row is not None:
                await self.session.delete(row)
        elif row is None:
            self.session.add(GuideState(budget_id=change.budget_id, key=key, value=wanted))
        else:
            row.value = wanted
        await self.session.flush()

    async def _restore_guide_bindings(self, change: ChangeLog, *, target: str, force: bool) -> None:
        """Put one concept's binding rows back the way the record says. The
        rows are hard-replaced on every save (ids reissued), so the record
        carries a canonical `_rows` dump per side."""
        payload = getattr(change, target) or {}
        concept = payload.get("_concept_key")
        if not concept:
            raise UndoConflict("This record did not say which concept it moved")
        rows = list(
            (
                await self.session.execute(
                    select(GuideBinding).where(
                        GuideBinding.budget_id == change.budget_id,
                        GuideBinding.concept_key == concept,
                    )
                )
            ).scalars()
        )
        expected_side = getattr(change, "after" if target == "before" else "before") or {}
        if not force and binding_rows_dump(rows) != (expected_side.get("_rows") or []):
            raise UndoConflict("The answer has changed since this change")
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        fields = ("mode", "entity_type", "entity_id", "answer", "amount", "as_of", "note")
        for wanted in payload.get("_rows") or []:
            self.session.add(
                GuideBinding(
                    budget_id=change.budget_id,
                    concept_key=concept,
                    **{f: coerce_value(GuideBinding, f, wanted.get(f)) for f in fields},
                )
            )
        await self.session.flush()

    async def _apply_membership(self, change: ChangeLog, *, target: str) -> None:
        """Membership rows are keyed (budget, user); the record's entity_id
        carries the user. Undo of an add removes the row, undo of a remove
        re-invites with the recorded role; `target` picks the direction
        ("before" undoes, "after" replays). Removal is idempotent — a member
        already gone is the state the step wanted."""
        row = await self.session.get(BudgetMember, (change.budget_id, change.entity_id))
        undoing = target == "before"
        removing = (change.action == "create") == undoing
        if removing:
            if row is not None:
                await self.session.delete(row)
        else:
            role = (getattr(change, target) or {}).get("role") or "member"
            if row is not None:
                row.role = role
            else:
                self.session.add(
                    BudgetMember(budget_id=change.budget_id, user_id=change.entity_id, role=role)
                )
        await self.session.flush()

    async def _replay_rotation(self, change: ChangeLog, entity, *, direction: str) -> None:
        """A rotate is a lossless transpose, so its inverse is the
        complementary rotation, re-run through the same service — pixels,
        thumbnail and stored metadata all follow. There is nothing to
        field-restore, which is why this bypasses the generic update path."""
        from igab.repositories.attachment_repo import AttachmentRepository
        from igab.services.attachment_service import AttachmentService

        degrees = int((change.after or {}).get("_degrees") or 0)
        if degrees not in (90, 180, 270):
            raise UndoConflict("This rotation did not record its angle")
        if getattr(entity, "is_deleted", False):
            raise UndoConflict("The item has been deleted since this change")
        txn = await self.session.get(Transaction, entity.transaction_id)
        if txn is None:
            raise UndoConflict("The affected item no longer exists")
        spin = (360 - degrees) if direction == "undo" else degrees
        service = AttachmentService(AttachmentRepository(self.session))
        try:
            await service.rotate(entity, txn, spin)
        except (FileNotFoundError, ValueError) as e:
            raise UndoConflict("The image file is no longer available") from e

    async def _refuse_if_referenced(self, change: ChangeLog) -> None:
        """A hard delete of a row something still points at would be an
        IntegrityError; say why instead."""
        referencer = HARD_ROW_REFERENCERS.get(change.entity_type)
        if referencer is None:
            return
        ref_model, fk = referencer
        held = (
            await self.session.execute(
                select(getattr(ref_model, fk)).where(getattr(ref_model, fk) == change.entity_id)
            )
        ).first()
        if held is not None:
            raise UndoConflict("Something still uses this item — repoint or remove that first")

    async def _insert_hard_row(self, change: ChangeLog, side: str) -> None:
        """Re-insert a hard-deleted row — undo of its delete, redo of its
        create — from the recorded snapshot, under its original id.

        The row's spot may have been re-taken since: a new target on the same
        category, a new value point on the same date. That is a person's later
        decision, so the restore refuses rather than fighting the unique key.
        """
        model: Any = ENTITY_MODELS[change.entity_type]
        payload = getattr(change, side) or {}
        fields = {f: coerce_value(model, f, v) for f, v in payload.items() if not f.startswith("_")}
        if "budget_id" in model.__table__.columns and "budget_id" not in fields:
            fields["budget_id"] = change.budget_id
        parent = HARD_ROW_PARENT.get(change.entity_type)
        if parent is not None:
            parent_model, fk = parent
            if fields.get(fk) is None or await self.session.get(parent_model, fields[fk]) is None:
                raise UndoConflict("What this row belonged to no longer exists")
        key = HARD_ROW_NATURAL_KEY[change.entity_type]
        clauses = [getattr(model, col) == fields.get(col) for col in key]
        taken: Any = (await self.session.execute(select(model).where(*clauses))).scalars().first()
        if taken is not None:
            if taken.id == change.entity_id:
                # Something already put it back. Leave it as it stands rather
                # than overwriting — the rule every other branch here follows.
                return
            raise UndoConflict("Its place has been taken by a newer entry — remove that one first")
        self.session.add(model(id=change.entity_id, **fields))
        await self.session.flush()
