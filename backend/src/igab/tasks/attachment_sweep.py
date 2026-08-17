"""Daily attachment cleanup.

Transactions are soft-deleted, so the ORM cascade on Transaction.attachments
never fires and receipt files would otherwise sit on disk forever. Files are
kept for a grace period after the transaction is deleted so a future
undo/restore can bring the images back, then swept for good.

A second pass removes files on disk that no attachment row references at all
(crashes between file write and row insert, historical deletions from before
this sweep existed).
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.config import settings
from igab.db.models import Transaction, TransactionAttachment

logger = logging.getLogger(__name__)

# How long attachment files of a deleted transaction survive on disk.
# soft_delete() stamps updated_at, and a deleted transaction can no longer be
# edited, so updated_at is the deletion time.
DELETED_TXN_GRACE_DAYS = 30

# Never touch files younger than this: an upload writes the file before its
# row is committed, so a brand-new file may legitimately have no row yet.
ORPHAN_MIN_AGE = timedelta(days=1)


async def sweep_deleted_transaction_attachments(session: AsyncSession) -> int:
    """Remove files + rows for attachments whose transaction was soft-deleted
    more than DELETED_TXN_GRACE_DAYS ago. Returns number of attachments swept."""
    from igab.repositories.attachment_repo import AttachmentRepository
    from igab.services.attachment_service import AttachmentService

    cutoff = datetime.now(UTC) - timedelta(days=DELETED_TXN_GRACE_DAYS)
    swept = 0
    result = await session.execute(
        select(TransactionAttachment, Transaction)
        .join(Transaction, TransactionAttachment.transaction_id == Transaction.id)
        .where(Transaction.is_deleted == True, Transaction.updated_at < cutoff)  # noqa: E712
    )
    service = AttachmentService(AttachmentRepository(session))
    for attachment, txn in result.all():
        try:
            await service.delete(attachment, txn)
            swept += 1
        except OSError:
            logger.exception(
                "attachment_sweep: could not delete files for attachment %s", attachment.id
            )
    await session.commit()
    if swept:
        logger.info("attachment_sweep: removed %d attachment(s) of deleted transactions", swept)
    return swept


async def sweep_orphaned_attachment_files(session: AsyncSession) -> int:
    """Remove attachment files on disk that no TransactionAttachment row
    references. Returns number of files removed."""
    base = Path(settings.ATTACHMENTS_DIR)
    if not base.is_dir():
        return 0

    result = await session.execute(select(TransactionAttachment.storage_path))
    referenced: set[str] = set()
    for storage_path in result.scalars():
        if not storage_path:
            continue
        referenced.add(storage_path)
        p = Path(storage_path)
        referenced.add(str(p.parent / f"thumb_{p.name}"))

    now = datetime.now(UTC)
    removed = 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        # ai_staging has its own lifecycle (see ai_worker.sweep_orphaned_staging)
        if rel.parts and rel.parts[0] == "ai_staging":
            continue
        if str(rel) in referenced:
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if now - mtime < ORPHAN_MIN_AGE:
                continue
            path.unlink()
            removed += 1
        except OSError:
            logger.exception("attachment_sweep: could not remove orphaned file %s", path)

    # Prune now-empty date/transaction directories, deepest first
    for path in sorted(base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and path.name != "ai_staging":
            try:
                path.rmdir()
            except OSError:
                pass
    if removed:
        logger.info("attachment_sweep: removed %d orphaned file(s)", removed)
    return removed


async def sweep_attachments() -> None:
    from igab.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await sweep_deleted_transaction_attachments(session)
        await sweep_orphaned_attachment_files(session)
