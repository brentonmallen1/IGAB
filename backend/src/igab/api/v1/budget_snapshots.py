"""Per-budget snapshots: download one, keep one, list them, throw one away.

The whole-application backup lives in ``backups.py`` and is exactly that —
every budget on the installation in one pg_dump. These are the other thing: a
file that holds one budget, which is what makes "show me the backups for the
budget I am in" answerable at all.

Its own module rather than more of the already-long ``budgets.py``, following
``budget_members.py`` / ``budget_filters.py`` / ``budget_views.py``.

**Owner, not member, to export.** A snapshot is the input to "create a budget
*I* own containing your data" — the same class of decision as deleting a
budget, which this codebase already reserves for owners. A member who wants
the numbers has ``/{budget_id}/reports/export`` under BudgetAccess.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from igab.api.route import CommitRoute
from igab.api.v1.schemas.budget_snapshots import (
    SnapshotCreated,
    SnapshotFile,
    SnapshotImportResult,
    SnapshotInspection,
)
from igab.dependencies import (
    BudgetAccess,
    BudgetOwnerAccess,
    CurrentUser,
    SessionDep,
    get_budget_service,
    get_category_repo,
)
from igab.domain.snapshot_format import check_compatibility
from igab.repositories.category_repo import CategoryRepository
from igab.services import budget_export, budget_snapshot
from igab.services.budget_service import BudgetService
from igab.services.update_service import current_version

router = APIRouter(route_class=CommitRoute)


MEDIA_TYPE = "application/zip"


async def _write_snapshot(session: AsyncSession, budget_id, destination: Path):
    """Serialize the budget into ``destination`` and return its manifest."""
    with destination.open("wb") as handle:
        return await budget_snapshot.export_budget_snapshot(
            session,
            budget_id,
            handle,
            app_version=current_version(),
            alembic_revision=await budget_snapshot.current_revision(session),
        )


@router.get("/budgets/{budget_id}/snapshot")
async def download_snapshot(budget_id: BudgetOwnerAccess, session: SessionDep) -> FileResponse:
    """Export this budget and hand it straight to the browser.

    Written to a temporary file rather than held in memory: a 25 MB `bytes`
    doubles peak memory for nothing, and FileResponse gets Content-Length for
    free.
    """
    with tempfile.NamedTemporaryFile(suffix=budget_snapshot.SNAPSHOT_SUFFIX, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        manifest = await _write_snapshot(session, budget_id, tmp_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path=tmp_path,
        media_type=MEDIA_TYPE,
        filename=budget_snapshot.snapshot_filename(manifest.budget_name),
        background=BackgroundTask(tmp_path.unlink, missing_ok=True),
    )


@router.post(
    "/budgets/{budget_id}/snapshots",
    response_model=SnapshotCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(budget_id: BudgetOwnerAccess, session: SessionDep) -> SnapshotCreated:
    """Export this budget and keep the file on the server.

    Same serializer as the download, a different destination: the backups
    volume, under this budget's own folder, so the list below is genuinely
    per-budget.
    """
    final, manifest = await budget_snapshot.write_kept_snapshot(
        session, budget_id, app_version=current_version()
    )
    return SnapshotCreated(
        name=final.name,
        size_bytes=final.stat().st_size,
        budget_name=manifest.budget_name,
        exported_at=manifest.exported_at,
        row_counts=dict(manifest.row_counts),
        attachments_omitted=manifest.attachments.omitted_count,
    )


@router.get("/budgets/{budget_id}/snapshots", response_model=list[SnapshotFile])
async def list_snapshots(budget_id: BudgetAccess) -> list[SnapshotFile]:
    return [SnapshotFile(**row) for row in budget_snapshot.list_snapshots(budget_id)]


@router.get("/budgets/{budget_id}/snapshots/{name}")
async def download_kept_snapshot(budget_id: BudgetOwnerAccess, name: str) -> FileResponse:
    path = budget_snapshot.snapshot_path(budget_id, name)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return FileResponse(path=path, media_type=MEDIA_TYPE, filename=path.name)


@router.delete("/budgets/{budget_id}/snapshots/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snapshot(budget_id: BudgetOwnerAccess, name: str) -> None:
    budget_snapshot.delete_snapshot(budget_id, name)


async def inspect_snapshot_file(tmp_path: Path, session: AsyncSession) -> SnapshotInspection:
    """One reading of "what does this file say, and can this installation
    import it". The inspect endpoint and the unified import preview
    (budgets.py) both serve exactly this — a second copy would be two
    verdicts on one file."""
    manifest = budget_snapshot.read_manifest(tmp_path)
    verdict = check_compatibility(
        manifest,
        current_revision=await budget_snapshot.current_revision(session),
        revision_history=budget_snapshot.migration_history(),
    )
    return SnapshotInspection(
        format=manifest.format,
        format_version=manifest.format_version,
        alembic_revision=manifest.alembic_revision,
        app_version=manifest.app_version,
        exported_at=manifest.exported_at,
        budget_name=manifest.budget_name,
        source_budget_id=manifest.source_budget_id,
        row_counts=dict(manifest.row_counts),
        attachments_omitted=manifest.attachments.omitted_count,
        ok=verdict.ok,
        refusals=list(verdict.refusals),
        warnings=list(verdict.warnings),
    )


@router.post("/budgets/snapshot/inspect", response_model=SnapshotInspection)
async def inspect_snapshot(
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile,
) -> SnapshotInspection:
    """What a file says about itself, and whether this installation can read
    it — without writing a single row.

    Any user may ask: it reads the manifest of a file they already hold, and
    tells them nothing about this installation's data.
    """
    with tempfile.NamedTemporaryFile(suffix=budget_snapshot.SNAPSHOT_SUFFIX, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
    try:
        return await inspect_snapshot_file(tmp_path, session)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post(
    "/budgets/import-snapshot",
    response_model=SnapshotImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_snapshot(
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile,
    name: Annotated[str | None, Form()] = None,
) -> SnapshotImportResult:
    """Load a snapshot into a **new** budget owned by the caller.

    Any user may import: the result is their own budget, built from a file
    they already hold. Nothing is written until the manifest has been read and
    accepted, and everything after that is inside this request's transaction —
    a failure half way through leaves the database exactly as it was.
    """
    with tempfile.NamedTemporaryFile(suffix=budget_snapshot.SNAPSHOT_SUFFIX, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
    try:
        report = await budget_snapshot.import_snapshot_as_new_budget(
            session, tmp_path, user_id=current_user.id, name=name
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return SnapshotImportResult(
        budget_id=str(report.budget_id),
        budget_name=report.budget_name,
        row_counts=report.row_counts,
        attachments_omitted=report.attachments_omitted,
        warnings=report.warnings,
    )


# Deliberately absent from the change log (see change_log.py's exclusion
# list): a restore replaces every table INCLUDING change_log itself — a
# record of it could only ever be destroyed by the thing it records. The
# snapshot file operations above are filesystem metadata with no budget row
# to restore.
@router.post("/budgets/{budget_id}/snapshot/restore", response_model=SnapshotImportResult)
async def restore_snapshot(
    budget_id: BudgetOwnerAccess,
    session: SessionDep,
    file: UploadFile,
    confirm_name: Annotated[str, Form()],
    pre_snapshot: Annotated[bool, Form()] = True,
) -> SnapshotImportResult:
    """Replace this budget's contents with a snapshot's, keeping the budget.

    Destructive and confirmed by typing the budget's name, not by ticking a
    box. A copy of the current state is taken first by default; if that copy
    cannot be written the restore does not start, because "we backed it up
    first" has to be true rather than hoped for.
    """
    with tempfile.NamedTemporaryFile(suffix=budget_snapshot.SNAPSHOT_SUFFIX, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
    try:
        report = await budget_snapshot.restore_snapshot_into_budget(
            session,
            tmp_path,
            budget_id=budget_id,
            confirm_name=confirm_name,
            app_version=current_version(),
            pre_snapshot=pre_snapshot,
        )
    except budget_snapshot.PreSnapshotUnavailable as e:
        # 409, not the 400 an IGABError would get: nothing about the request
        # is wrong, the server is not in a state to do it safely.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    finally:
        tmp_path.unlink(missing_ok=True)

    return SnapshotImportResult(
        budget_id=str(report.budget_id),
        budget_name=report.budget_name,
        row_counts=report.row_counts,
        attachments_omitted=report.attachments_omitted,
        attachments_dropped=report.attachments_dropped,
        warnings=report.warnings,
    )


@router.get("/budgets/{budget_id}/export")
async def export_budget(
    budget_id: BudgetAccess,
    session: SessionDep,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    format: str = "ynab",
) -> FileResponse:
    """This budget as a readable, portable file.

    BudgetAccess rather than owner: a member can already export the register
    through /{budget_id}/reports/export, and this is the same data in a better
    shape. The snapshot beside it is owner-only because it is the input to
    "create a budget I own containing your data" — a different question.
    """
    if format != "ynab":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown export format {format!r}. The only shape is 'ynab'.",
        )

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tmp_path.open("wb") as handle:
            manifest = await budget_export.export_budget_ynab(
                session,
                budget_service,
                category_repo,
                budget_id,
                handle,
                app_version=current_version(),
                exported_at=datetime.now(tz=UTC).isoformat(),
            )
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    name = budget_snapshot.slugify(str(manifest["budget_name"]))
    return FileResponse(
        path=tmp_path,
        media_type=MEDIA_TYPE,
        filename=f"{name}-export.zip",
        background=BackgroundTask(tmp_path.unlink, missing_ok=True),
    )
