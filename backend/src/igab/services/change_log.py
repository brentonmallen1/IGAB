"""Change recording for the undo/audit system.

Write paths call `ChangeRecorder.record()` explicitly — no ORM-event magic —
so what lands in the log is exactly what the services decide is a
user-visible mutation. The standing rule is that EVERY user-visible mutation
records, because the global undo is LIFO over this log and any uncovered
domain makes ⌘Z silently revert something older and unrelated. Its corollary:
every MANUAL record must have a working inverse in undo_service, or the
first ⌘Z that reaches it jams on "cannot be undone". Auto-created side
effects (transfer payees, payees resolved during transaction entry, derived
tag syncs) are deliberately not recorded: undoing them independently would
orphan references. The deliberate exclusions — whole-budget deletes and
snapshot restores (they destroy this log itself), and rows with no budget to
file under (users, app settings, SimpleFIN connections; `budget_id` here is
NOT NULL) — are named in the API modules that own them.

Snapshots hold every restorable field, serialized to JSON-safe values.
Keys starting with "_" carry undo bookkeeping (e.g. attachment ids moved by
a merge) and are never written back onto the entity.
"""

from __future__ import annotations

import datetime
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    Asset,
    AssetValueSnapshot,
    Budget,
    BudgetAssignment,
    Category,
    CategoryGroup,
    CategoryTarget,
    ChangeLog,
    Liability,
    LiabilityBalanceSnapshot,
    Payee,
    ScheduledTransaction,
    Transaction,
    WishlistItem,
    WishlistProject,
    new_uuid,
)
from igab.domain.payee_names import samples_from_legacy

ENTITY_MODELS: dict[str, type] = {
    "transaction": Transaction,
    "payee": Payee,
    "category": Category,
    "category_group": CategoryGroup,
    "assignment": BudgetAssignment,
    # Only ever the subject of a `reorder` (of its groups); it has no
    # snapshot fields because nothing on the budget row itself is restored.
    "budget": Budget,
    "wishlist_item": WishlistItem,
    "wishlist_project": WishlistProject,
    # Pseudo-subject in the same spirit as "budget": a reorder of the
    # budget's wishes or wish projects (`_collection` bookkeeping says
    # which). Resolves to the budget row; nothing on it is restored.
    "wishlist": Budget,
    # Hard-row entities (no is_deleted column): undo re-inserts from the
    # snapshot — see undo_service.HARD_ROW_NATURAL_KEY.
    "category_target": CategoryTarget,
    "liability_snapshot": LiabilityBalanceSnapshot,
    "asset_value": AssetValueSnapshot,
    "liability": Liability,
    "asset": Asset,
    "scheduled_transaction": ScheduledTransaction,
}

# Restorable fields per entity. is_deleted is excluded on purpose — the
# delete/restore lifecycle is carried by the change's `action`, not the
# snapshot. Timestamps are excluded because they are server-managed.
SNAPSHOT_FIELDS: dict[str, tuple[str, ...]] = {
    "transaction": (
        "account_id",
        "date",
        "entered_date",
        "entered_amount",
        "bank_posted_date",
        "amount",
        "bank_amount",
        "bank_payee",
        "payee_id",
        "category_id",
        # Provenance, restored alongside category_id so an undone edit does not
        # leave a row filed in one category while claiming it "was" another.
        "prior_category_id",
        "prior_category_name",
        "memo",
        "cleared",
        "approved",
        "latitude",
        "longitude",
        "transfer_id",
        "parent_transaction_id",
        "is_split",
        "import_id",
        "import_batch_id",
        "import_description",
        "sync_id",
        "sync_source",
        "created_via",
        "scheduled_transaction_id",
        "linked_transaction_id",
        "link_confidence",
        "has_sync_source",
    ),
    "payee": (
        "name",
        "default_category_id",
        "transfer_account_id",
        "mapping_samples",
        "match_pattern",
    ),
    "category": (
        "category_group_id",
        "name",
        "subtitle",
        "sort_order",
        "note",
        "is_archived",
        "linked_account_id",
        "linked_liability_id",
    ),
    "category_group": ("name", "sort_order", "is_archived", "is_system"),
    "assignment": ("category_id", "month", "assigned"),
    "wishlist_item": (
        "project_id",
        "name",
        "url",
        "notes",
        "cost",
        "category_id",
        "owns_envelope",
        "priority",
        "is_priority",
        "status",
        "cooling_until",
        "last_affirmed_at",
        "done_at",
    ),
    "wishlist_project": ("name", "category_id", "notes", "sort_order"),
    "category_target": (
        "category_id",
        "target_type",
        "target_amount",
        "target_date",
        "repeat_frequency",
    ),
    "liability": (
        "name",
        "liability_type",
        "linked_account_id",
        "linked_asset_id",
        "manual_balance",
        "interest_rate",
        "minimum_payment",
        "minimum_payment_kind",
        "minimum_payment_percent",
        "minimum_payment_floor",
        "minimum_payment_plus_interest",
        "compounding",
        "planned_extra_payment",
        "origination_date",
        "original_principal",
        "promo_end_date",
        "promo_deferred_interest",
        "term_months",
        "payment_due_day",
    ),
    "liability_snapshot": ("liability_id", "date", "balance", "source"),
    # manual_value/value_as_of are derived from the newest surviving value
    # point, but they snapshot anyway: a value-point operation records the
    # pair's move as an explicit asset update in the same batch, so undo
    # restores it by field instead of re-running the derivation.
    "asset": ("name", "asset_type", "manual_value", "value_as_of"),
    "asset_value": ("asset_id", "date", "value", "source"),
    "scheduled_transaction": (
        "account_id",
        "amount",
        "payee_id",
        "category_id",
        "memo",
        "frequency",
        "start_date",
        "end_date",
        "second_day_of_month",
        "auto_create",
        "days_before_reminder",
        "transfer_account_id",
        "last_created_date",
        "next_occurrence_date",
    ),
}


def source_for(created_via: str | None) -> str:
    """The change-log `source` a row's origin implies.

    `created_via` is where the row came from (domain: manual | import | sync
    | scheduled | ai_receipt | ai_nl); `source` is who acted, as Activity
    renders it. One mapping, so a sync-created row can no longer be logged
    as a manual entry — which every one of them was, before this existed.
    """
    if created_via is None:
        return "manual"
    if created_via.startswith("ai"):
        return "ai"
    if created_via == "import":
        return "import"
    if created_via in ("sync", "scheduled"):
        return "system"
    return "manual"


def serialize_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    return value


def snapshot(entity_type: str, obj: Any) -> dict[str, Any]:
    """JSON-safe snapshot of an entity's restorable fields. `obj` may be an
    ORM instance or a plain dict (bulk-import rows); fields the object lacks
    are omitted (ORM rows always carry every column)."""
    fields = SNAPSHOT_FIELDS[entity_type]
    if isinstance(obj, dict):
        return {f: serialize_value(obj[f]) for f in fields if f in obj}
    return {f: serialize_value(getattr(obj, f)) for f in fields if hasattr(obj, f)}


def coerce_value(model: Any, field: str, value: Any) -> Any:
    """Convert a JSON snapshot value back to the column's Python type."""
    if model is Payee and field == "mapping_samples":
        # Snapshots recorded before the list migration hold the comma string;
        # the column is a non-null list now, so null reads as empty.
        return samples_from_legacy(value)
    if value is None:
        return None
    col_type = model.__table__.columns[field].type
    type_name = type(col_type).__name__
    if type_name == "UUID":
        return uuid.UUID(value)
    if type_name == "Numeric":
        return Decimal(value)
    if type_name == "Date":
        return datetime.date.fromisoformat(value)
    if type_name == "DateTime":
        return datetime.datetime.fromisoformat(value)
    return value


def values_equal(a: Any, b: Any) -> bool:
    """Snapshot-value comparison tolerant of Decimal scale ('12.34' vs
    '12.3400') — DB round-trips normalize Numeric scale."""
    if a == b:
        return True
    if isinstance(a, str) and isinstance(b, str):
        try:
            return Decimal(a) == Decimal(b)
        except InvalidOperation:
            return False
    return False


def snapshots_match(current: dict[str, Any], recorded: dict[str, Any]) -> list[str]:
    """Fields where the entity's current state differs from the recorded
    snapshot (undo bookkeeping keys ignored). Empty list = clean."""
    return [
        key
        for key, recorded_value in recorded.items()
        if not key.startswith("_") and not values_equal(current.get(key), recorded_value)
    ]


class ChangeRecorder:
    """Session-bound recorder. `batch()` groups every record made inside the
    outermost open batch under one batch_id, so compound operations (splits,
    transfers, bulk actions, merges) undo as a unit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._batch_id: uuid.UUID | None = None
        # Who is acting. Stamped by the request-layer dependency factories
        # (where CurrentUser is in scope); worker/scheduler recorders leave it
        # None, which renders as the source ('AI', 'system') in the UI.
        self.actor_user_id: uuid.UUID | None = None

    @contextmanager
    def batch(self):
        owner = self._batch_id is None
        if owner:
            self._batch_id = new_uuid()
        try:
            yield self._batch_id
        finally:
            if owner:
                self._batch_id = None

    @property
    def current_batch_id(self) -> uuid.UUID | None:
        """The open batch, for handing to ANOTHER service's recorder so a
        compound operation that crosses services still undoes as one unit
        (batch_id is just a column — it does not care which recorder wrote
        the row). None outside a batch, which `record` treats as unbatched."""
        return self._batch_id

    async def record(
        self,
        *,
        budget_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        source: str = "manual",
        batch_id: uuid.UUID | None = None,
    ) -> ChangeLog:
        row = ChangeLog(
            id=new_uuid(),
            budget_id=budget_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
            batch_id=batch_id if batch_id is not None else self._batch_id,
            source=source,
            user_id=self.actor_user_id,
        )
        self.session.add(row)
        return row
