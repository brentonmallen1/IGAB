"""The on-disk shape of a budget snapshot, and the rules for reading one back.

A snapshot is an ``.igab.zip``: a manifest plus one NDJSON member per table.

    manifest.json
    tables/accounts.ndjson
    tables/transactions.ndjson
    …

Zip, because the manifest reads **without touching a data row** — which is what
makes "validate before mutating anything" cheap, and what an inspect endpoint
serves from; because per-table members decouple write order from read order;
because attachment bytes can drop in later as ``attachments/…`` with no format
change; and because single-line rows stream in both directions at O(one row)
memory, which a single JSON document cannot.

This module is pure: it knows the format, the codec and the compatibility
rules, and it never opens a file or a session. The service around it does the
I/O, so every branch here is a one-line test.

**Money is encoded as a string, never a float.** A snapshot is a file someone
restores a year later; ``0.1 + 0.2`` is not a risk worth taking with a ledger,
and the client already reads canonical decimal strings through
``parseApiDecimal``.

**An unhandled column type raises.** Falling back to ``str()`` would write a
value nothing can read back, and it would do it silently — which is how a
restore discovers, a year later, that one column has been prose all along.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from igab.db.budget_scope import budget_tables
from igab.db.models import Base

FORMAT = "igab.budget-snapshot"
VERSION = 1
MIN_SUPPORTED_VERSION = 1

#: The one hard floor on age, and the only one. Snapshots exported before this
#: migration carry account_type values whose *meaning* changed — 'loan' became
#: mortgage / auto_loan / student_loan — so their rows would import cleanly and
#: describe the wrong thing, which is worse than refusing.
#:
#: Nothing else is a hard gate. Refusing on any revision mismatch would make it
#: impossible to restore last month's backup, which is the entire point of
#: having one; a blunt gate is a rule people learn to defeat.
MIN_SUPPORTED_REVISION = "d2e6a9c53b71"

#: Budget-owned tables a snapshot deliberately leaves behind, each with the
#: reason. Data rather than prose, because "why isn't X in my backup?" is a
#: question this feature will be asked for as long as it exists.
SNAPSHOT_OMITTED: Mapping[str, str] = MappingProxyType(
    {
        "budget_members": "Membership is authorization. Carrying it would "
        "grant the exporter's collaborators access to the importer's budget.",
        "change_log": "Undo history. seq is an Identity column, user_id may "
        "name nobody on this installation, and before/after are JSONB full of "
        "ids no remapper can reach without a second copy of the field list. "
        "Undoing across a restore is meaningless anyway.",
        "ai_jobs": "A work queue whose payloads embed staged file paths under ATTACHMENTS_DIR.",
        "category_month_snapshots": "Derived cache. Rebuilt from transactions "
        "and assignments on the first read after import.",
        "budget_snapshot_meta": "The validity flag for that cache. Carrying it "
        "would declare a freshly imported budget's cache valid when no cache "
        "has been computed.",
        "transaction_attachments": "The bytes are not in the file, and "
        "storage_path embeds the source transaction id.",
    }
)

#: Columns forced to a fixed value when a snapshot lands in a **different**
#: budget than it left. A duplicate has never been connected to a bank, and two
#: Accounts sharing a simplefin_account_id means one sync writes the same rows
#: into both budgets.
#:
#: Applied at import and never at export: doing it on export would be simpler
#: and wrong, because restore-in-place would then silently break a working bank
#: link. "Don't fight over the same feed" is a property of *duplication*.
#:
#: Row-level sync_id / sync_source are deliberately kept — they are ledger
#: provenance scoped by account_id, so uq_transactions_account_sync_id cannot
#: collide across budgets, and keeping them means deduplication still works if
#: the copy is later linked to the same bank.
REDACT_ON_NEW_BUDGET: Mapping[tuple[str, str], Any] = MappingProxyType(
    {
        ("accounts", "simplefin_account_id"): None,
        ("accounts", "simplefin_account_name"): None,
        ("accounts", "simplefin_balance"): None,
        ("accounts", "last_simplefin_sync_at"): None,
        # Back to the schema default rather than to False: the copy is not
        # connected to anything, so the source's paused/enabled preference
        # says nothing about it, and a later link should behave normally.
        ("accounts", "simplefin_sync_enabled"): True,
        ("accounts", "first_sync_complete"): False,
    }
)


@dataclass(frozen=True)
class AttachmentSummary:
    """What happened to receipts. Attachments are excluded in v1 and the file
    says so out loud, so the UI can tell someone *before* they restore.

    This is a correctness rule, not a size optimisation. AttachmentService
    writes ``YYYY/MM/DD/<transaction_id>/<file>.webp`` and its delete unlinks
    the file. Import the rows without the bytes and two transactions share one
    path — delete either and a receipt vanishes from the other budget. v2 adds
    ``attachments/<new_txn_id>/<file>`` to the zip and rewrites storage_path on
    insert; that is the only correct shape.
    """

    included: bool = False
    omitted_count: int = 0


@dataclass(frozen=True)
class SnapshotManifest:
    """Everything needed to decide whether a file can be read, without
    reading a single data row."""

    format: str
    format_version: int
    alembic_revision: str
    app_version: str
    exported_at: str
    source_budget_id: str
    budget_name: str
    #: table -> columns AS EXPORTED. The compatibility check diffs this
    #: against live metadata; it is not decoration.
    columns: Mapping[str, Sequence[str]] = field(default_factory=dict)
    row_counts: Mapping[str, int] = field(default_factory=dict)
    omitted_tables: Mapping[str, str] = field(default_factory=dict)
    attachments: AttachmentSummary = field(default_factory=AttachmentSummary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "format_version": self.format_version,
            "alembic_revision": self.alembic_revision,
            "app_version": self.app_version,
            "exported_at": self.exported_at,
            "source_budget_id": self.source_budget_id,
            "budget_name": self.budget_name,
            "columns": {t: list(c) for t, c in self.columns.items()},
            "row_counts": dict(self.row_counts),
            "omitted_tables": dict(self.omitted_tables),
            "attachments": {
                "included": self.attachments.included,
                "omitted_count": self.attachments.omitted_count,
            },
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SnapshotManifest":
        attachments = raw.get("attachments") or {}
        return cls(
            format=str(raw.get("format", "")),
            format_version=int(raw.get("format_version", 0)),
            alembic_revision=str(raw.get("alembic_revision", "")),
            app_version=str(raw.get("app_version", "")),
            exported_at=str(raw.get("exported_at", "")),
            source_budget_id=str(raw.get("source_budget_id", "")),
            budget_name=str(raw.get("budget_name", "")),
            columns={t: list(c) for t, c in (raw.get("columns") or {}).items()},
            row_counts=dict(raw.get("row_counts") or {}),
            omitted_tables=dict(raw.get("omitted_tables") or {}),
            attachments=AttachmentSummary(
                included=bool(attachments.get("included", False)),
                omitted_count=int(attachments.get("omitted_count", 0)),
            ),
        )


def carried_tables(metadata: MetaData = Base.metadata) -> tuple[Table, ...]:
    """The budget's tables a snapshot actually writes, in insert order."""
    return tuple(t for t in budget_tables(metadata) if t.name not in SNAPSHOT_OMITTED)


def exported_columns(table: Table) -> tuple[str, ...]:
    """Column names written for one table, in schema order."""
    return tuple(column.name for column in table.columns)


# ─── Codec ────────────────────────────────────────────────────────────────────


class UnsupportedColumnType(TypeError):
    """A column whose type this format has no encoding for.

    Raised rather than falling back to ``str()``: a value written by a fallback
    is a value nothing can read back, and nothing would have said so.
    """


def column_kind(column: Column[Any]) -> str:
    """Which of the codec's encodings this column uses."""
    type_ = column.type
    # JSONB before the scalar checks: it is not a String, but a dialect type
    # that must pass through untouched.
    if isinstance(type_, JSONB):
        return "json"
    if isinstance(type_, PG_UUID):
        return "uuid"
    if isinstance(type_, Numeric) and not isinstance(type_, Float):
        return "decimal"
    if isinstance(type_, DateTime):
        return "datetime"
    if isinstance(type_, Date):
        return "date"
    if isinstance(type_, Boolean):
        return "bool"
    if isinstance(type_, (BigInteger, Integer)):
        return "int"
    if isinstance(type_, Float):
        return "float"
    if isinstance(type_, (String, Text)):
        return "str"
    raise UnsupportedColumnType(
        f"{column.table.name}.{column.name} is {type(type_).__name__}, which "
        f"snapshot_format has no encoding for. Add one here and to "
        f"test_snapshot_format, rather than letting it be written as prose."
    )


def encode_value(column: Column[Any], value: Any) -> Any:
    """One column value, as it is written to NDJSON."""
    kind = column_kind(column)
    if value is None:
        return None
    if kind == "uuid":
        return str(value)
    if kind == "decimal":
        # str(), not float(): Decimal("100.0000") must come back with its
        # scale intact, and money must never round-trip through binary.
        return str(value)
    if kind in ("date", "datetime"):
        return value.isoformat()
    if kind == "json":
        return value
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    return str(value)


def decode_value(column: Column[Any], value: Any) -> Any:
    """The inverse of :func:`encode_value`, for one column value."""
    kind = column_kind(column)
    if value is None:
        return None
    if kind == "uuid":
        return value if isinstance(value, UUID) else UUID(str(value))
    if kind == "decimal":
        return value if isinstance(value, Decimal) else Decimal(str(value))
    if kind == "datetime":
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if kind == "date":
        if isinstance(value, datetime):
            return value.date()
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if kind == "json":
        return value
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    return str(value)


def encode_row(table: Table, row: Mapping[str, Any]) -> dict[str, Any]:
    return {c.name: encode_value(c, row.get(c.name)) for c in table.columns}


def decode_row(table: Table, row: Mapping[str, Any]) -> dict[str, Any]:
    """Decode the columns the file actually carries.

    Columns missing from ``row`` are left out rather than defaulted to None —
    a column added since the export must take its schema default, not a null
    that would fail a NOT NULL constraint the compatibility check already
    cleared.
    """
    return {c.name: decode_value(c, row[c.name]) for c in table.columns if c.name in row}


# ─── Compatibility ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Compatibility:
    """Whether a file can be read, and what will be lost if it is."""

    refusals: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    #: table -> columns present in the file and gone from the schema
    dropped_columns: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.refusals


def check_compatibility(
    manifest: SnapshotManifest,
    metadata: MetaData = Base.metadata,
    *,
    current_revision: str = "",
    revision_history: Sequence[str] = (),
) -> Compatibility:
    """Reconcile a file against the live schema.

    Real reconciliation, not a version equality check: what matters is whether
    every column this schema *requires* is in the file, not whether the two
    were built by the same migration.

    ``revision_history`` is the running app's revisions, oldest first, as the
    caller reads them from the migration scripts. Given it, a file older than
    :data:`MIN_SUPPORTED_REVISION` is refused. Without it the age of a revision
    cannot be known, so only equality is reported — as a warning.
    """
    refusals: list[str] = []
    warnings: list[str] = []
    dropped: dict[str, tuple[str, ...]] = {}

    if manifest.format != FORMAT:
        refusals.append(f"This is not an IGAB budget snapshot (it says {manifest.format!r}).")
        return Compatibility(tuple(refusals), tuple(warnings), dropped)

    if not MIN_SUPPORTED_VERSION <= manifest.format_version <= VERSION:
        refusals.append(
            f"Snapshot format v{manifest.format_version} cannot be read by this "
            f"version of IGAB, which reads v{MIN_SUPPORTED_VERSION}–v{VERSION}."
        )
        return Compatibility(tuple(refusals), tuple(warnings), dropped)

    refusals.extend(_revision_refusals(manifest, revision_history))
    warnings.extend(_revision_warnings(manifest, current_revision, revision_history))

    live = {table.name: table for table in carried_tables(metadata)}

    for table_name in manifest.columns:
        if table_name not in live:
            warnings.append(
                f"The file carries {table_name}, which this version of IGAB no "
                f"longer stores. Its rows will be skipped."
            )

    for name, table in live.items():
        if name not in manifest.columns:
            warnings.append(
                f"The file predates the {name} table, so the imported budget "
                f"will have none of those rows."
            )
            continue

        in_file = set(manifest.columns[name])
        in_schema = {column.name for column in table.columns}

        gone = tuple(sorted(in_file - in_schema))
        if gone:
            dropped[name] = gone
            warnings.append(f"{name}: {', '.join(gone)} no longer exist and will be dropped.")

        for column in table.columns:
            if column.name in in_file:
                continue
            if column.nullable or column.default is not None or column.server_default is not None:
                continue
            refusals.append(
                f"{name}.{column.name} is required and the file does not carry "
                f"it. This snapshot is too old to import into this version of "
                f"IGAB."
            )

    return Compatibility(tuple(refusals), tuple(warnings), dropped)


def _revision_refusals(manifest: SnapshotManifest, revision_history: Sequence[str]) -> list[str]:
    if not revision_history or manifest.alembic_revision not in revision_history:
        return []
    if MIN_SUPPORTED_REVISION not in revision_history:
        return []
    if revision_history.index(manifest.alembic_revision) >= revision_history.index(
        MIN_SUPPORTED_REVISION
    ):
        return []
    return [
        f"This snapshot predates migration {MIN_SUPPORTED_REVISION}, which "
        f"changed what an account type means. Its accounts would import "
        f"cleanly and describe the wrong thing."
    ]


def _revision_warnings(
    manifest: SnapshotManifest, current_revision: str, revision_history: Sequence[str]
) -> list[str]:
    if not manifest.alembic_revision:
        return ["The file does not say which schema version produced it."]
    if revision_history and manifest.alembic_revision not in revision_history:
        return [
            f"Schema version {manifest.alembic_revision} is not one this "
            f"installation knows — the file may come from a newer IGAB."
        ]
    if current_revision and manifest.alembic_revision != current_revision:
        return [
            f"The file was exported at schema version "
            f"{manifest.alembic_revision}; this installation is at "
            f"{current_revision}. Columns are reconciled individually, so this "
            f"is usually fine."
        ]
    return []
