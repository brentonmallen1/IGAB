"""Writing one budget out as a portable file, and reading back what a file says.

The whole-application backup beside this one is a `pg_dump` of the installation
— every budget, every user, one file. No filter makes it per-budget, which is
why "the backups list is global" was never a labelling problem. A snapshot is
the other thing: one budget, portable, and yours to keep.

Two destinations, one serializer. `GET …/snapshot` streams a file straight to
the browser; `POST …/snapshots` writes the same bytes into
``BACKUPS_DIR/budgets/<budget_id>/`` so the list a person sees inside a budget
is actually that budget's, and so restore-in-place has somewhere to put the
pre-restore copy it takes first.

Rows stream. ``session.stream`` with ``yield_per`` feeds one ``json.dumps``
line at a time straight into the deflate stream, so a 100k-transaction budget
costs the cursor buffer plus the compressor window rather than 80 MB of
resident JSON. Row order is the primary key, which makes two snapshots of the
same budget diffable.

The format itself — what is carried, what is left, and how a value is encoded
— lives in :mod:`igab.domain.snapshot_format`, which has no I/O and is tested
without a database. This module is the wiring.
"""

import json
import os
import re
import tempfile
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import bindparam, delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.config import settings
from igab.db.budget_scope import (
    POLYMORPHIC_REFERENCES,
    SOFT_REFERENCES,
    budget_predicate,
    deferred_columns,
    delete_order,
)
from igab.db.models import Base
from igab.domain.exceptions import IGABError, InvariantViolation, NotFoundError
from igab.domain.snapshot_format import (
    FORMAT,
    REDACT_ON_NEW_BUDGET,
    SNAPSHOT_OMITTED,
    VERSION,
    AttachmentSummary,
    Compatibility,
    SnapshotManifest,
    carried_tables,
    check_compatibility,
    decode_row,
    encode_row,
    exported_columns,
)
from igab.repositories.tag_repo import seed_system_tags
from igab.services.account_type_service import ensure_account_types_seeded
from igab.services.budget_provisioning import grant_owner, unique_budget_name

SNAPSHOT_SUFFIX = ".igab.zip"
MANIFEST_MEMBER = "manifest.json"

#: Rows per round trip out of the cursor. Large enough that a big export is
#: not a million round trips, small enough that the buffer stays incidental.
STREAM_CHUNK = 2000

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


# ─── Where snapshots live ─────────────────────────────────────────────────────


def snapshots_dir(budget_id: UUID) -> Path:
    """This budget's folder inside the backups volume both compose files
    already mount into the API container."""
    return Path(settings.BACKUPS_DIR) / "budgets" / str(budget_id)


def slugify(name: str) -> str:
    slug = _SLUG_STRIP.sub("-", name.lower()).strip("-")[:40].strip("-")
    return slug or "budget"


def snapshot_filename(budget_name: str, when: datetime | None = None) -> str:
    stamp = (when or datetime.now(tz=UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{slugify(budget_name)}-{stamp}{SNAPSHOT_SUFFIX}"


def snapshot_path(budget_id: UUID, name: str) -> Path:
    """The file a client named, once it is proven to be a filename.

    Uses the same guard as the whole-app backups — a name that arrives over
    HTTP is a string, not a path, and there is one implementation of that.
    """
    from igab.services.backup_service import safe_backup_filename

    checked = safe_backup_filename(name)
    if not checked.endswith(SNAPSHOT_SUFFIX):
        raise InvariantViolation(f"Not a budget snapshot file name: {name}")
    return snapshots_dir(budget_id) / checked


def list_snapshots(budget_id: UUID) -> list[dict[str, Any]]:
    """Kept snapshots for one budget, newest first."""
    try:
        entries = list(os.scandir(snapshots_dir(budget_id)))
    except OSError:
        return []
    files = [
        {
            "name": entry.name,
            "size_bytes": entry.stat().st_size,
            "modified_at": datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC),
        }
        for entry in entries
        if entry.is_file() and entry.name.endswith(SNAPSHOT_SUFFIX)
    ]
    files.sort(key=lambda f: f["modified_at"], reverse=True)
    return files


def delete_snapshot(budget_id: UUID, name: str) -> None:
    path = snapshot_path(budget_id, name)
    try:
        path.unlink()
    except FileNotFoundError as e:
        raise NotFoundError("snapshot", name) from e


# ─── Schema version ───────────────────────────────────────────────────────────


async def current_revision(session: AsyncSession) -> str:
    """The migration this database is at, straight from alembic's own table.

    ``to_regclass`` first rather than catching the error: a database built
    outside alembic has no such table, and in Postgres a failed statement
    aborts the whole transaction — so asking politely is the only way to ask
    without breaking the caller's unit of work.
    """
    exists = await session.execute(text("SELECT to_regclass('alembic_version')"))
    if exists.scalar_one_or_none() is None:
        return ""
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    row = result.scalar_one_or_none()
    return str(row) if row else ""


def migration_history() -> tuple[str, ...]:
    """Every revision this installation knows, oldest first.

    Read from the migration scripts, which is why it lives here and not in
    ``snapshot_format``: judging whether a file is *older* than the one
    meaning-changing migration needs the ordering, and the ordering is on
    disk. An installation that ships without the scripts gets an empty
    history, and the compatibility check then declines to judge age rather
    than guessing.
    """
    try:
        from alembic.script import ScriptDirectory

        import igab

        script_dir = Path(igab.__file__).parents[2] / "alembic"
        script = ScriptDirectory(str(script_dir))
        return tuple(reversed([rev.revision for rev in script.walk_revisions()]))
    except Exception:
        return ()


# ─── Export ───────────────────────────────────────────────────────────────────


async def _budget_row(session: AsyncSession, budget_id: UUID) -> Any:
    budgets = Base.metadata.tables["budgets"]
    result = await session.execute(
        select(budgets.c.id, budgets.c.name).where(budgets.c.id == budget_id)
    )
    row = result.one_or_none()
    if row is None:
        raise NotFoundError("budget", str(budget_id))
    return row


async def _attachment_count(session: AsyncSession, budget_id: UUID) -> int:
    attachments = Base.metadata.tables["transaction_attachments"]
    result = await session.execute(
        select(func.count())
        .select_from(attachments)
        .where(budget_predicate(attachments, budget_id))
    )
    return int(result.scalar_one())


async def export_budget_snapshot(
    session: AsyncSession,
    budget_id: UUID,
    out: BinaryIO,
    *,
    app_version: str,
    alembic_revision: str,
) -> SnapshotManifest:
    """Write one budget into ``out`` as an ``.igab.zip``, and return what the
    manifest says about it.

    ``out`` must be seekable — a NamedTemporaryFile, not a socket. The caller
    hands the finished file to FileResponse, which gets Content-Length for
    free; a StreamingResponse would give that up and buy nothing.
    """
    budget = await _budget_row(session, budget_id)

    columns: dict[str, list[str]] = {}
    row_counts: dict[str, int] = {}

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in carried_tables():
            columns[table.name] = list(exported_columns(table))
            row_counts[table.name] = await _write_table(archive, session, table, budget_id)

        manifest = SnapshotManifest(
            format=FORMAT,
            format_version=VERSION,
            alembic_revision=alembic_revision,
            app_version=app_version,
            exported_at=datetime.now(tz=UTC).isoformat(),
            source_budget_id=str(budget.id),
            budget_name=budget.name,
            columns=columns,
            row_counts=row_counts,
            omitted_tables=dict(SNAPSHOT_OMITTED),
            attachments=AttachmentSummary(
                included=False,
                omitted_count=await _attachment_count(session, budget_id),
            ),
        )
        # Written last because the row counts are only known now, but still its
        # own member — a reader gets the whole verdict in one seek, without
        # touching a data row.
        archive.writestr(MANIFEST_MEMBER, json.dumps(manifest.to_dict(), indent=2))

    return manifest


async def _write_table(
    archive: zipfile.ZipFile, session: AsyncSession, table: Any, budget_id: UUID
) -> int:
    stmt = (
        select(table)
        .where(budget_predicate(table, budget_id))
        # Deterministic order makes two snapshots of one budget diffable.
        .order_by(*table.primary_key.columns)
        .execution_options(yield_per=STREAM_CHUNK)
    )
    count = 0
    with archive.open(f"tables/{table.name}.ndjson", "w") as member:
        result = await session.stream(stmt)
        async for row in result.mappings():
            line = json.dumps(encode_row(table, dict(row)), separators=(",", ":"))
            member.write(line.encode("utf-8") + b"\n")
            count += 1
    return count


# ─── Reading a file back ──────────────────────────────────────────────────────


def read_manifest(path: Path) -> SnapshotManifest:
    """The manifest alone, without reading a single data row.

    Every failure here is someone's upload, so each one is a 400 with a
    sentence rather than a traceback.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open(MANIFEST_MEMBER) as member:
                raw = json.load(member)
    except zipfile.BadZipFile as e:
        raise InvariantViolation("That file is not a zip archive.") from e
    except KeyError as e:
        raise InvariantViolation(
            "That zip has no manifest.json, so it is not a budget snapshot."
        ) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise InvariantViolation("The snapshot's manifest is not readable JSON.") from e
    if not isinstance(raw, dict):
        raise InvariantViolation("The snapshot's manifest is not an object.")
    return SnapshotManifest.from_dict(raw)


def iter_rows(archive: zipfile.ZipFile, table_name: str) -> Iterator[dict[str, Any]]:
    """One table member, decoded from NDJSON one line at a time.

    A generator rather than a list: a 100k-transaction member is the whole
    point of the line-per-row format, and materializing it here would give
    that back.
    """
    try:
        member = archive.open(f"tables/{table_name}.ndjson")
    except KeyError:
        return
    with member:
        for number, line in enumerate(member, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as e:
                raise InvariantViolation(
                    f"{table_name}.ndjson line {number} is not valid JSON."
                ) from e


def table_rows(archive: zipfile.ZipFile, table_name: str) -> list[dict[str, Any]]:
    """Every row of one table member. For the small ones — and for tests."""
    return list(iter_rows(archive, table_name))


# ─── Import ───────────────────────────────────────────────────────────────────


class SnapshotIncompatible(IGABError):
    """The file cannot be read by this installation. Carries every reason, so
    the UI can show them all rather than the first one."""

    def __init__(self, reasons: Sequence[str]) -> None:
        super().__init__(" ".join(reasons) or "This snapshot cannot be imported.")
        self.reasons = list(reasons)


class SnapshotIntegrityError(IGABError):
    """A reference in the file points at a row the file does not contain.

    Loud on purpose. The alternative — writing NULL and carrying on — produces
    a budget that looks imported and is quietly missing its links, which is
    the failure mode this whole feature exists to rule out.
    """


#: Rows per INSERT. Matches SnapshotRepository._BULK_CHUNK: big enough that a
#: large import is not a million round trips, small enough that the resident
#: cost stays a chunk rather than a budget.
IMPORT_CHUNK = 1000


@dataclass(frozen=True)
class ImportPlan:
    """The only real difference between the two ways in.

    ``remap`` — a new budget. Every id is replaced, which is what makes a
    duplicate a separate thing rather than a second name for the same rows.

    ``preserve`` — restore in place. Ids are kept, which is what a restore
    *should* mean: attachment paths on disk, bookmarks, and anything else
    holding a transaction id still resolve afterwards.
    """

    id_strategy: str = "remap"
    redact: Mapping[tuple[str, str], Any] = field(default_factory=dict)


@dataclass
class ImportReport:
    budget_id: UUID
    budget_name: str
    row_counts: dict[str, int]
    #: Receipts the file does not carry. Always the whole count for an
    #: import-as-new; for a restore, only those that could not be put back.
    attachments_omitted: int
    #: Receipts a restore could not re-attach, because the transaction they
    #: hung on is not in the snapshot.
    attachments_dropped: int = 0
    warnings: list[str] = field(default_factory=list)


async def import_snapshot_as_new_budget(
    session: AsyncSession,
    path: Path,
    *,
    user_id: UUID,
    name: str | None = None,
) -> ImportReport:
    """Load a snapshot into a brand-new budget owned by ``user_id``.

    Everything after the validation below runs inside the caller's request
    transaction, which ``get_session`` rolls back on any exception. That *is*
    the atomicity guarantee — a failure half way through leaves the database
    exactly as it was, with no extra machinery.
    """
    manifest, verdict = await validate_snapshot(session, path)

    with zipfile.ZipFile(path) as archive:
        _check_members(archive, manifest)
        base = (name or manifest.budget_name or "Imported budget").strip()
        resolved = await unique_budget_name(session, user_id, base)
        # A savepoint, so "all of it or none of it" is a property of the
        # import rather than of whoever opened the session. get_session
        # rolls back on the way out too; this makes the guarantee hold for
        # any other caller, and makes it observable.
        async with session.begin_nested():
            report = await _load(
                session,
                archive,
                plan_for(manifest, None),
                owner_user_id=user_id,
                budget_name=resolved,
            )
    report.warnings = list(verdict.warnings)
    report.attachments_omitted = manifest.attachments.omitted_count
    return report


async def validate_snapshot(
    session: AsyncSession, path: Path
) -> tuple[SnapshotManifest, Compatibility]:
    """Read the manifest and decide whether the file can be read at all.

    Nothing is created and nothing is destroyed by this — that is the point.
    The YNAB route sets the precedent: parse and validate before the first
    write, so a bad file costs a 400 rather than a half-imported budget.
    """
    manifest = read_manifest(path)
    verdict = check_compatibility(
        manifest,
        current_revision=await current_revision(session),
        revision_history=migration_history(),
    )
    if not verdict.ok:
        raise SnapshotIncompatible(verdict.refusals)
    return manifest, verdict


def _check_members(archive: zipfile.ZipFile, manifest: SnapshotManifest) -> None:
    """Every table the manifest declares is present, and nothing else is.

    An unexpected member is not a curiosity: it means the file was assembled
    by something other than this app, and the rows it holds would be silently
    ignored by a loader that only reads what the manifest lists.
    """
    present = {
        item[len("tables/") : -len(".ndjson")]
        for item in archive.namelist()
        if item.startswith("tables/") and item.endswith(".ndjson")
    }
    declared = set(manifest.columns)

    missing = sorted(declared - present)
    if missing:
        raise InvariantViolation(
            f"The snapshot's manifest lists {', '.join(missing)}, but the file "
            f"does not contain them."
        )
    unexpected = sorted(present - declared)
    if unexpected:
        raise InvariantViolation(
            f"The snapshot contains {', '.join(unexpected)}, which its manifest does not declare."
        )
    if "budgets" not in declared:
        raise InvariantViolation("The snapshot carries no budget row.")


async def _load(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    plan: ImportPlan,
    *,
    owner_user_id: UUID | None = None,
    budget_name: str | None = None,
    target_budget_id: UUID | None = None,
) -> ImportReport:
    """The shared core of both ways in: build the id map, insert, then link."""
    budgets = Base.metadata.tables["budgets"]
    source_rows = table_rows(archive, "budgets")
    if len(source_rows) != 1:
        raise InvariantViolation(
            f"A snapshot holds exactly one budget; this one holds {len(source_rows)}."
        )
    source = source_rows[0]

    remap = _build_remap(archive, plan, target_budget_id=target_budget_id, source=source)
    budget_id = remap["budgets"][str(source["id"])]

    row = decode_row(budgets, source)
    if target_budget_id is None:
        if owner_user_id is None or budget_name is None:
            raise InvariantViolation(
                "A snapshot landing in a new budget needs an owner and a name."
            )
        row["id"] = budget_id
        # Never the file's user_id: the person importing owns what they
        # import, and the exporter may not exist on this installation.
        row["user_id"] = owner_user_id
        row["name"] = budget_name
        await session.execute(insert(budgets).values(**row))
        grant_owner(session, budget_id, owner_user_id)
        await session.flush()
        name = str(row["name"])
    else:
        # The budget row survives a restore, and only the settings the file
        # carries are applied to it. Not the name and not the owner — see
        # RESTORED_BUDGET_COLUMNS.
        settings_from_file = {
            column: value for column, value in row.items() if column in RESTORED_BUDGET_COLUMNS
        }
        await session.execute(
            update(budgets).where(budgets.c.id == budget_id).values(**settings_from_file)
        )
        name = str(
            (
                await session.execute(select(budgets.c.name).where(budgets.c.id == budget_id))
            ).scalar_one()
        )

    counts: dict[str, int] = {"budgets": 1}
    for table in carried_tables():
        if table.name == "budgets":
            continue
        counts[table.name] = await _insert_table(session, archive, table, remap, plan)

    for table in carried_tables():
        if deferred_columns(table):
            await _link_deferred(session, archive, table, remap)

    # AFTER the rows, never before. The YNAB importer seeds first, and copying
    # that here collides with the snapshot's own builtin rows on
    # uq_account_type_budget_key. Run last and both calls are idempotent *and*
    # repair a snapshot taken before a new builtin type or system tag existed.
    await ensure_account_types_seeded(session, budget_id)
    await seed_system_tags(session, budget_id)

    return ImportReport(
        budget_id=budget_id,
        budget_name=name,
        row_counts=counts,
        attachments_omitted=0,
    )


def _build_remap(
    archive: zipfile.ZipFile,
    plan: ImportPlan,
    *,
    target_budget_id: UUID | None,
    source: Mapping[str, Any],
) -> dict[str, dict[str, UUID]]:
    """Every old id in the file, mapped to the id it will have.

    Built in full before the first INSERT rather than as rows go in, because
    the graph is not a tree: ``guide_bindings`` sorts before ``categories``
    but points at one. ~20 MB of UUIDs at 100k transactions, and unavoidable
    for a correct remap.
    """
    remap: dict[str, dict[str, UUID]] = {}
    for table in carried_tables():
        ids: dict[str, UUID] = {}
        primary = list(table.primary_key.columns)
        # Association tables (category_tags, payee_tags) have composite keys
        # and nothing references them, so they need no map.
        if len(primary) == 1 and primary[0].name == "id":
            for row in iter_rows(archive, table.name):
                old = str(row["id"])
                ids[old] = uuid4() if plan.id_strategy == "remap" else UUID(old)
        remap[table.name] = ids

    if target_budget_id is not None:
        remap["budgets"][str(source["id"])] = target_budget_id
    return remap


def _reference_target(table: Any, column: Any, raw: Mapping[str, Any]) -> str | None:
    """Which table this column's value addresses, if any.

    Foreign keys come from metadata; the columns that address a row *without*
    a foreign key come from budget_scope's declarations — which is exactly why
    those declarations are data and not prose.
    """
    for fk in column.foreign_keys:
        return str(fk.column.table.name)

    key = (table.name, column.name)
    if key in SOFT_REFERENCES:
        return SOFT_REFERENCES[key]
    if key in POLYMORPHIC_REFERENCES:
        type_column, targets = POLYMORPHIC_REFERENCES[key]
        discriminator = raw.get(type_column)
        if discriminator is None:
            return None
        target = targets.get(str(discriminator))
        if target is None:
            raise SnapshotIntegrityError(
                f"{table.name}.{type_column} is {discriminator!r}, which names "
                f"no table this version of IGAB knows."
            )
        return target
    return None


def _translate(
    table: Any, raw: Mapping[str, Any], remap: dict[str, dict[str, UUID]], plan: ImportPlan
) -> dict[str, Any]:
    """One row from the file, ready to insert."""
    row = decode_row(table, raw)

    own = remap.get(table.name) or {}
    if "id" in row and own:
        row["id"] = own[str(raw["id"])]

    for column in table.columns:
        if column.name == "id" or column.name not in row or row[column.name] is None:
            continue
        target = _reference_target(table, column, raw)
        if target is None:
            continue
        row[column.name] = _resolve(table, column, target, row[column.name], remap)

    # Self-references are filled by the second pass: the rows they point at
    # may not be in yet, and foreign keys here are checked per statement.
    for column in deferred_columns(table):
        if column.name in row:
            row[column.name] = None

    for (table_name, column_name), value in plan.redact.items():
        if table_name == table.name and column_name in row:
            row[column_name] = value

    return row


def _resolve(
    table: Any, column: Any, target: str, value: Any, remap: dict[str, dict[str, UUID]]
) -> UUID:
    known = remap.get(target)
    if known is None:
        raise SnapshotIntegrityError(
            f"{table.name}.{column.name} points into {target}, which a snapshot does not carry."
        )
    try:
        return known[str(value)]
    except KeyError:
        raise SnapshotIntegrityError(
            f"{table.name}.{column.name} points at {target} {value}, which is not in the file."
        ) from None


async def _insert_table(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    table: Any,
    remap: dict[str, dict[str, UUID]],
    plan: ImportPlan,
) -> int:
    """Core inserts, in chunks, with no ORM objects.

    100k Transaction instances in an identity map would be the whole memory
    budget on their own, and none of the ORM's services are wanted here: these
    rows are already exactly what they should be.
    """
    chunk: list[dict[str, Any]] = []
    total = 0
    for raw in iter_rows(archive, table.name):
        chunk.append(_translate(table, raw, remap, plan))
        if len(chunk) >= IMPORT_CHUNK:
            await session.execute(insert(table), chunk)
            total += len(chunk)
            chunk = []
    if chunk:
        await session.execute(insert(table), chunk)
        total += len(chunk)
    return total


async def _link_deferred(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    table: Any,
    remap: dict[str, dict[str, UUID]],
) -> None:
    """Second pass: fill the columns that point back at this same table.

    Re-reads the member rather than buffering pass one, so this stays O(chunk)
    like everything else.
    """
    columns = deferred_columns(table)
    statement = (
        update(table)
        .where(table.c.id == bindparam("b_id"))
        .values({column.name: bindparam(f"b_{column.name}") for column in columns})
    )
    chunk: list[dict[str, Any]] = []
    for raw in iter_rows(archive, table.name):
        if all(raw.get(column.name) is None for column in columns):
            continue
        params: dict[str, Any] = {"b_id": remap[table.name][str(raw["id"])]}
        for column in columns:
            value = raw.get(column.name)
            params[f"b_{column.name}"] = (
                None if value is None else _resolve(table, column, table.name, value, remap)
            )
        chunk.append(params)
        if len(chunk) >= IMPORT_CHUNK:
            await session.execute(statement, chunk)
            chunk = []
    if chunk:
        await session.execute(statement, chunk)


# ─── Restore in place ─────────────────────────────────────────────────────────


class PreSnapshotUnavailable(IGABError):
    """The safety copy could not be written, so the restore did not start.

    A silent no-op here is the whole trust failure this feature exists to
    prevent: "we took a backup first" has to be true or said out loud.
    """


#: Left alone by a restore. Membership is authorization — a restore must not
#: un-share a shared budget or lock its owner out of it.
PRESERVED_ON_RESTORE: Mapping[str, str] = MappingProxyType(
    {
        "budget_members": "Membership is authorization. Restoring last month's "
        "file must not un-share a shared budget or remove the person doing it.",
    }
)

#: What a restore takes from the file's budget row. Everything else on that
#: row stays as it is — the id (so links, bookmarks and the frontend's stored
#: currentBudgetId still resolve), and deliberately **not** the name or the
#: owner: restoring a name risks colliding with uq_budget_user_name and
#: silently renaming the budget the person just picked out of a list.
RESTORED_BUDGET_COLUMNS = frozenset(
    {
        "currency_code",
        "number_format",
        "date_format",
        "time_format",
        "import_summary",
        "import_reviewed_at",
    }
)


def plan_for(manifest: SnapshotManifest, target_budget_id: UUID | None) -> ImportPlan:
    """One rule, asked once: did this file leave the budget it is landing in?

    If it did, ids are kept — that is what a restore should mean, and what
    keeps attachment paths and anything else holding a transaction id
    resolving afterwards. If it did not, every id is replaced (its originals
    are still in use in the budget it came from) and the bank link is dropped
    (two accounts on one simplefin_account_id means one sync writes the same
    rows into both).
    """
    if target_budget_id is not None and manifest.source_budget_id == str(target_budget_id):
        return ImportPlan(id_strategy="preserve", redact={})
    return ImportPlan(id_strategy="remap", redact=REDACT_ON_NEW_BUDGET)


async def write_kept_snapshot(
    session: AsyncSession, budget_id: UUID, *, app_version: str
) -> tuple[Path, SnapshotManifest]:
    """Export a budget into its own folder on the backups volume.

    Written under a temporary name and renamed on success, so a failed export
    never leaves a half-written file in the list. Shared by "keep a snapshot"
    and by the safety copy a restore takes first — one way to put a snapshot
    on disk.
    """
    directory = snapshots_dir(budget_id)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".partial", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tmp_path.open("wb") as handle:
            manifest = await export_budget_snapshot(
                session,
                budget_id,
                handle,
                app_version=app_version,
                alembic_revision=await current_revision(session),
            )
        final = directory / snapshot_filename(manifest.budget_name)
        tmp_path.replace(final)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return final, manifest


async def restore_snapshot_into_budget(
    session: AsyncSession,
    path: Path,
    *,
    budget_id: UUID,
    confirm_name: str,
    app_version: str,
    pre_snapshot: bool = True,
) -> ImportReport:
    """Replace a budget's contents with a snapshot's, keeping the budget.

    The id survives, so sharing survives and the frontend's persisted
    currentBudgetId still resolves — MainLayout bounces to the selector when
    it does not, which is exactly what a new-id restore would trigger.
    """
    manifest, verdict = await validate_snapshot(session, path)

    target = await _budget_row(session, budget_id)
    if confirm_name.strip() != target.name:
        raise InvariantViolation(
            f"Type the budget's name exactly to confirm. This budget is called {target.name!r}."
        )

    if pre_snapshot:
        try:
            await write_kept_snapshot(session, budget_id, app_version=app_version)
        except OSError as e:
            raise PreSnapshotUnavailable(
                "A copy of this budget could not be saved before restoring, so "
                "nothing was changed. Check that the backups volume is mounted "
                "and writable."
            ) from e

    plan = plan_for(manifest, budget_id)
    with zipfile.ZipFile(path) as archive:
        _check_members(archive, manifest)
        async with session.begin_nested():
            # Only worth holding when the ids come back: a foreign snapshot
            # remaps every transaction, so no receipt could be re-attached.
            held = (
                await _read_attachments(session, budget_id)
                if plan.id_strategy == "preserve"
                else []
            )
            await _clear_budget(session, budget_id)
            report = await _load(session, archive, plan, target_budget_id=budget_id)
            report.attachments_dropped = await _reattach(session, held)
    report.warnings = list(verdict.warnings)
    report.attachments_omitted = manifest.attachments.omitted_count
    return report


async def _clear_budget(session: AsyncSession, budget_id: UUID) -> None:
    """Everything this budget owns, in an order the foreign keys allow.

    Children first, and the budgets row itself is never touched — that is what
    makes the id survive. Deleting the derived cache here is also what makes
    the rebuild happen: absence of budget_snapshot_meta *is* the invalidation,
    and db/invalidation's hooks short-circuit on the Core statements this
    module uses, so nothing else would have signalled it.
    """
    for table in delete_order():
        if table.name in PRESERVED_ON_RESTORE:
            continue
        await session.execute(delete(table).where(budget_predicate(table, budget_id)))


async def _read_attachments(session: AsyncSession, budget_id: UUID) -> list[dict[str, Any]]:
    """Attachment rows, held aside while the budget is cleared.

    A snapshot does not carry receipts — the bytes are not in the file — but
    they are still this budget's data, and a restore that keeps every
    transaction id keeps the transactions those receipts hang on. Deleting
    them would destroy the only link to files that are still on disk and
    still correct.

    Held in memory rather than joined around, because the rows go away with
    their transactions the moment the delete pass runs: attachments cascade
    from transactions, so skipping the explicit delete would not have saved
    them either.
    """
    attachments = Base.metadata.tables["transaction_attachments"]
    rows = await session.execute(
        select(attachments).where(budget_predicate(attachments, budget_id))
    )
    return [dict(row) for row in rows.mappings()]


async def _reattach(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """Put back the receipts whose transaction came back. Returns how many
    could not be — their transaction is not in the snapshot, so there is
    nothing left for them to hang on."""
    if not rows:
        return 0
    attachments = Base.metadata.tables["transaction_attachments"]
    transactions = Base.metadata.tables["transactions"]
    wanted = {row["transaction_id"] for row in rows}
    alive = set(
        (await session.execute(select(transactions.c.id).where(transactions.c.id.in_(wanted))))
        .scalars()
        .all()
    )
    keep = [row for row in rows if row["transaction_id"] in alive]
    for start in range(0, len(keep), IMPORT_CHUNK):
        await session.execute(insert(attachments), keep[start : start + IMPORT_CHUNK])
    return len(rows) - len(keep)
