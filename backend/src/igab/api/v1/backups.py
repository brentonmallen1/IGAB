from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials

from igab.api.v1.schemas.backups import (
    BackupFile,
    BackupJob,
    BackupsOverview,
    BackupStatus,
    JobStarted,
    RestoreRequest,
)
from igab.config import settings
from igab.dependencies import AdminUser, bearer_scheme
from igab.domain.exceptions import AuthenticationError
from igab.services import backup_service
from igab.services.auth_service import decode_token

router = APIRouter()


async def _verify_token_only(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> None:
    """Signature/expiry check without a DB round-trip.

    The status endpoint must keep answering while a restore has the
    database torn down, so it cannot use the normal user lookup. Known
    tradeoff: a deactivated user's unexpired token can still read backup
    status — read-only and low-sensitivity, accepted so restore progress
    stays observable.
    """
    try:
        decode_token(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def _require_agent() -> None:
    online, _ = backup_service.agent_status()
    if not online:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The backup service is not running. It is part of the production "
                "compose profile (db-backup container)."
            ),
        )


def _require_idle() -> None:
    if backup_service.job_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A backup job is already in progress",
        )


@router.get("/backups", response_model=BackupsOverview)
async def list_backups(current_user: AdminUser) -> BackupsOverview:
    online, last_seen = backup_service.agent_status()
    job = backup_service.read_job_status()
    return BackupsOverview(
        agent_online=online,
        agent_last_seen=last_seen,
        maintenance=backup_service.maintenance_active(),
        queued=backup_service.command_pending(),
        job=BackupJob(**job) if job else None,
        files=[BackupFile(**f) for f in backup_service.list_backup_files()],
    )


@router.get("/backups/status", response_model=BackupStatus)
async def backup_status(
    _token: Annotated[None, Depends(_verify_token_only)],
) -> BackupStatus:
    """Job progress — DB-free so it works mid-restore."""
    online, _ = backup_service.agent_status()
    job = backup_service.read_job_status()
    return BackupStatus(
        agent_online=online,
        maintenance=backup_service.maintenance_active(),
        queued=backup_service.command_pending(),
        job=BackupJob(**job) if job else None,
    )


@router.post("/backups/run", response_model=JobStarted)
async def run_backup(current_user: AdminUser) -> JobStarted:
    """Ask the agent to run a backup cycle now."""
    _require_agent()
    _require_idle()
    return JobStarted(job_id=backup_service.write_command("backup"))


@router.post("/backups/restore", response_model=JobStarted)
async def restore_backup(body: RestoreRequest, current_user: AdminUser) -> JobStarted:
    """Restore the database from a backup — REPLACES all current data.

    The app enters maintenance mode and restarts itself when the agent
    finishes; the client should poll /backups/status and then /health.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restore must be explicitly confirmed",
        )
    name = backup_service.safe_backup_filename(body.file)
    files = {f["name"]: f for f in backup_service.list_backup_files()}
    file = files.get(name)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")
    if file["kind"] == "attachments":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attachment archives are restored from the CLI (see README → Backups)",
        )
    if file["encrypted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This backup is age-encrypted and the server has no private key "
                "(by design). Restore it from the CLI: just restore <file>"
            ),
        )
    _require_agent()
    _require_idle()
    job_id = backup_service.write_command("restore", file=name, pre_backup=body.pre_backup)
    await backup_service.enter_maintenance_and_watch()
    return JobStarted(job_id=job_id)


@router.get("/backups/{name}/download")
async def download_backup(name: str, current_user: AdminUser) -> FileResponse:
    """Hand a whole-application backup to the browser.

    Served straight from BACKUPS_DIR, which the API container already mounts,
    so this works while the agent is offline — the agent makes backups, it is
    not needed to read one. `.age` files download fine; they are already
    encrypted, which is the point of them.
    """
    checked = backup_service.safe_backup_filename(name)
    if checked not in {f["name"] for f in backup_service.list_backup_files()}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")
    return FileResponse(
        path=Path(settings.BACKUPS_DIR) / checked,
        media_type="application/octet-stream",
        filename=checked,
    )
