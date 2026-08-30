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
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from igab.config import settings
from igab.db.budget_scope import budget_predicate
from igab.db.models import Base
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.domain.snapshot_format import (
    FORMAT,
    SNAPSHOT_OMITTED,
    VERSION,
    AttachmentSummary,
    SnapshotManifest,
    carried_tables,
    encode_row,
    exported_columns,
)

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


def table_rows(archive: zipfile.ZipFile, table_name: str) -> Sequence[dict[str, Any]]:
    """Every row of one table member, decoded from NDJSON.

    Kept here rather than in the reader loop so the import half of this
    service and the tests read rows the same way.
    """
    try:
        member = archive.open(f"tables/{table_name}.ndjson")
    except KeyError:
        return []
    with member:
        rows = []
        for number, line in enumerate(member, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                raise InvariantViolation(
                    f"{table_name}.ndjson line {number} is not valid JSON."
                ) from e
        return rows
