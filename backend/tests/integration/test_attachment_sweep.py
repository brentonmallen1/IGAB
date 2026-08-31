"""Attachment sweep: grace-period cleanup for deleted transactions and
removal of on-disk files no attachment row references."""

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

import igab.config
from igab.db.models import Transaction, TransactionAttachment
from igab.tasks.attachment_sweep import (
    DELETED_TXN_GRACE_DAYS,
    sweep_deleted_transaction_attachments,
    sweep_orphaned_attachment_files,
)

from .factories import create_account, create_budget, create_transaction, create_user


@pytest.fixture
def attachments_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(igab.config.settings, "ATTACHMENTS_DIR", str(tmp_path))
    return tmp_path


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    return budget, account


async def _add_attachment(
    db_session, attachments_dir: Path, txn: Transaction
) -> tuple[TransactionAttachment, Path, Path]:
    """Create an attachment row plus its file + thumbnail on disk, mirroring
    the layout AttachmentService.upload produces."""
    filename = f"{uuid.uuid4()}.webp"
    rel_dir = (
        Path(str(txn.date.year)) / f"{txn.date.month:02d}" / f"{txn.date.day:02d}" / str(txn.id)
    )
    abs_dir = attachments_dir / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    file_path = abs_dir / filename
    thumb_path = abs_dir / f"thumb_{filename}"
    file_path.write_bytes(b"image-bytes")
    thumb_path.write_bytes(b"thumb-bytes")

    attachment = TransactionAttachment(
        transaction_id=txn.id,
        filename=filename,
        original_filename="receipt.jpg",
        content_type="image/webp",
        file_size=len(b"image-bytes"),
        storage_path=str(rel_dir / filename),
    )
    db_session.add(attachment)
    await db_session.flush()
    return attachment, file_path, thumb_path


async def _set_updated_at(db_session, txn: Transaction, *, days_ago: int) -> None:
    await db_session.execute(
        update(Transaction)
        .where(Transaction.id == txn.id)
        .values(updated_at=datetime.now(UTC) - timedelta(days=days_ago))
    )


async def _attachment_rows(db_session) -> list[TransactionAttachment]:
    result = await db_session.execute(select(TransactionAttachment))
    return list(result.scalars().all())


class TestSweepDeletedTransactionAttachments:
    async def test_removes_files_and_rows_after_grace(self, db_session, attachments_dir):
        budget, account = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 7, 1), is_deleted=True
        )
        _, file_path, thumb_path = await _add_attachment(db_session, attachments_dir, txn)
        await _set_updated_at(db_session, txn, days_ago=DELETED_TXN_GRACE_DAYS + 1)

        swept = await sweep_deleted_transaction_attachments(db_session)

        assert swept == 1
        assert not file_path.exists()
        assert not thumb_path.exists()
        assert not file_path.parent.exists()  # per-transaction dir pruned
        assert await _attachment_rows(db_session) == []

    async def test_keeps_attachments_within_grace(self, db_session, attachments_dir):
        budget, account = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 8, 1), is_deleted=True
        )
        _, file_path, thumb_path = await _add_attachment(db_session, attachments_dir, txn)
        await _set_updated_at(db_session, txn, days_ago=DELETED_TXN_GRACE_DAYS - 1)

        swept = await sweep_deleted_transaction_attachments(db_session)

        assert swept == 0
        assert file_path.exists()
        assert thumb_path.exists()
        assert len(await _attachment_rows(db_session)) == 1

    async def test_never_touches_live_transactions(self, db_session, attachments_dir):
        budget, account = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-10.00", date(2025, 1, 1), is_deleted=False
        )
        _, file_path, _ = await _add_attachment(db_session, attachments_dir, txn)
        # Even an ancient updated_at must not matter for a live transaction
        await _set_updated_at(db_session, txn, days_ago=400)

        swept = await sweep_deleted_transaction_attachments(db_session)

        assert swept == 0
        assert file_path.exists()
        assert len(await _attachment_rows(db_session)) == 1

    async def test_deleted_transaction_without_attachments_is_noop(
        self, db_session, attachments_dir
    ):
        budget, account = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 6, 1), is_deleted=True
        )
        await _set_updated_at(db_session, txn, days_ago=DELETED_TXN_GRACE_DAYS + 5)

        assert await sweep_deleted_transaction_attachments(db_session) == 0

    async def test_missing_file_still_removes_row(self, db_session, attachments_dir):
        """File already gone from disk (manual cleanup, lost volume) — the row
        must still be swept rather than erroring forever."""
        budget, account = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 7, 1), is_deleted=True
        )
        _, file_path, thumb_path = await _add_attachment(db_session, attachments_dir, txn)
        file_path.unlink()
        thumb_path.unlink()
        await _set_updated_at(db_session, txn, days_ago=DELETED_TXN_GRACE_DAYS + 1)

        swept = await sweep_deleted_transaction_attachments(db_session)

        assert swept == 1
        assert await _attachment_rows(db_session) == []


def _age_file(path: Path, days: int) -> None:
    past = datetime.now(UTC).timestamp() - days * 86400
    os.utime(path, (past, past))


class TestSweepOrphanedFiles:
    async def test_removes_old_unreferenced_files_and_prunes_dirs(
        self, db_session, attachments_dir
    ):
        orphan_dir = attachments_dir / "2026" / "01" / "02" / str(uuid.uuid4())
        orphan_dir.mkdir(parents=True)
        orphan = orphan_dir / "gone.webp"
        orphan.write_bytes(b"x")
        _age_file(orphan, days=2)

        removed = await sweep_orphaned_attachment_files(db_session)

        assert removed == 1
        assert not orphan.exists()
        assert not orphan_dir.exists()
        assert not (attachments_dir / "2026").exists()

    async def test_keeps_referenced_file_and_its_thumbnail(self, db_session, attachments_dir):
        budget, account = await _setup(db_session)
        txn = await create_transaction(db_session, budget, account, "-5.00", date(2026, 8, 1))
        _, file_path, thumb_path = await _add_attachment(db_session, attachments_dir, txn)
        _age_file(file_path, days=2)
        _age_file(thumb_path, days=2)

        removed = await sweep_orphaned_attachment_files(db_session)

        assert removed == 0
        assert file_path.exists()
        assert thumb_path.exists()

    async def test_keeps_files_younger_than_min_age(self, db_session, attachments_dir):
        fresh = attachments_dir / "2026" / "08" / "16" / str(uuid.uuid4()) / "new.webp"
        fresh.parent.mkdir(parents=True)
        fresh.write_bytes(b"x")  # mtime = now

        removed = await sweep_orphaned_attachment_files(db_session)

        assert removed == 0
        assert fresh.exists()

    async def test_skips_ai_staging(self, db_session, attachments_dir):
        staged = attachments_dir / "ai_staging" / str(uuid.uuid4()) / "receipt.jpg"
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"x")
        _age_file(staged, days=10)

        removed = await sweep_orphaned_attachment_files(db_session)

        assert removed == 0
        assert staged.exists()
        assert staged.parent.exists()

    async def test_missing_base_dir_is_noop(self, db_session, attachments_dir, monkeypatch):
        monkeypatch.setattr(igab.config.settings, "ATTACHMENTS_DIR", str(attachments_dir / "nope"))
        assert await sweep_orphaned_attachment_files(db_session) == 0

    async def test_mixed_orphaned_and_referenced(self, db_session, attachments_dir):
        budget, account = await _setup(db_session)
        txn = await create_transaction(db_session, budget, account, "-5.00", date(2026, 8, 1))
        _, file_path, thumb_path = await _add_attachment(db_session, attachments_dir, txn)
        _age_file(file_path, days=2)
        _age_file(thumb_path, days=2)

        orphan = file_path.parent / "stray.webp"
        orphan.write_bytes(b"x")
        _age_file(orphan, days=2)

        removed = await sweep_orphaned_attachment_files(db_session)

        assert removed == 1
        assert not orphan.exists()
        assert file_path.exists()
        assert thumb_path.exists()
        assert file_path.parent.exists()  # dir kept: still holds referenced files
