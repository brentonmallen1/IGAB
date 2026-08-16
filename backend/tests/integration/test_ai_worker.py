"""Worker job processing: extraction → transaction + attachment, retry
bookkeeping, terminal-failure stub, stub refill on retry, crash recovery."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

import igab.config
from igab.db.models import AIJob, Transaction, TransactionAttachment
from igab.repositories.ai_job_repo import AIJobRepository
from igab.services.ai_service import AIService
from igab.tasks.ai_worker import (
    FAILURE_STUB_MEMO,
    NonRetryableJobError,
    process_one_job,
    record_job_failure,
)

from .factories import create_account, create_budget, create_category, create_category_group

GOOD_EXTRACTION = {
    "payee": "Whole Foods",
    "total": 42.50,
    "date": "2026-08-01",
    "category": "Groceries",
    "confidence": 0.9,
    "memo": None,
    "line_items": [
        {"description": "MILK 2%", "amount": 4.50, "category": "Groceries"},
        {"description": "PAPER TOWELS", "amount": 38.00, "category": "Household"},
    ],
    "suggested_split": [
        {"category": "Groceries", "amount": 4.50},
        {"category": "Household", "amount": 38.00},
    ],
}


def tiny_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def attachments_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(igab.config.settings, "ATTACHMENTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def mock_extraction(monkeypatch):
    monkeypatch.setattr(
        AIService, "check_vision_support", AsyncMock(return_value=(None, "gemma4"))
    )
    monkeypatch.setattr(AIService, "is_receipt_image", AsyncMock(return_value=True))
    mock = AsyncMock(return_value=GOOD_EXTRACTION)
    monkeypatch.setattr(AIService, "extract_receipt", mock)
    return mock


async def _setup(db_session, attachments_dir, *, with_categories: bool = True):
    from .factories import create_user

    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    if with_categories:
        group = await create_category_group(db_session, budget, "Everyday")
        await create_category(db_session, budget, group, "Groceries")
        await create_category(db_session, budget, group, "Household")
    return budget, account


async def _make_job(db_session, attachments_dir, budget, account, **overrides) -> AIJob:
    job_id = uuid.uuid4()
    stage = attachments_dir / "ai_staging" / str(job_id)
    stage.mkdir(parents=True)
    (stage / "receipt.jpg").write_bytes(tiny_jpeg())
    fields = {
        "id": job_id,
        "budget_id": budget.id,
        "kind": "receipt",
        "status": "processing",
        "attempts": 1,
        "payload": {
            "account_id": str(account.id),
            "original_filename": "receipt.jpg",
            "content_type": "image/jpeg",
            "staged_path": f"ai_staging/{job_id}/receipt.jpg",
            "client_today": "2026-08-02",
        },
    }
    fields.update(overrides)
    job = AIJob(**fields)
    db_session.add(job)
    await db_session.flush()
    return job


class TestReceiptSuccess:
    async def test_creates_unapproved_transaction_with_attachment(
        self, db_session, attachments_dir, mock_extraction
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)

        await process_one_job(db_session, job)

        assert job.status == "done"
        assert job.error is None
        txn = await db_session.get(Transaction, job.transaction_id)
        assert txn is not None
        assert txn.approved is False
        assert txn.created_via == "ai_receipt"
        assert txn.amount == Decimal("-42.50")
        assert txn.date == date(2026, 8, 1)
        assert txn.payee_id is not None
        assert txn.category_id is not None

        attachment = await db_session.get(TransactionAttachment, job.attachment_id)
        assert attachment is not None
        assert attachment.transaction_id == txn.id
        assert attachment.storage_path
        assert (attachments_dir / attachment.storage_path).exists()
        # staging cleaned up after success
        assert not (attachments_dir / "ai_staging" / str(job.id)).exists()

    async def test_result_carries_suggested_split(
        self, db_session, attachments_dir, mock_extraction
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        await process_one_job(db_session, job)
        split = job.result["suggested_split"]
        assert [s["category"] for s in split] == ["Groceries", "Household"]
        assert [s["amount"] for s in split] == ["-4.50", "-38.00"]

    async def test_unknown_category_lands_uncategorized(
        self, db_session, attachments_dir, mock_extraction
    ):
        budget, account = await _setup(db_session, attachments_dir, with_categories=False)
        job = await _make_job(db_session, attachments_dir, budget, account)
        await process_one_job(db_session, job)
        txn = await db_session.get(Transaction, job.transaction_id)
        assert txn.category_id is None
        assert job.result["suggested_split"] is None


class TestReceiptFailures:
    async def test_missing_staged_file_is_non_retryable(
        self, db_session, attachments_dir, mock_extraction
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        (attachments_dir / "ai_staging" / str(job.id) / "receipt.jpg").unlink()
        with pytest.raises(NonRetryableJobError, match="image is missing"):
            await process_one_job(db_session, job)

    async def test_no_vision_support_is_non_retryable(
        self, db_session, attachments_dir, monkeypatch
    ):
        monkeypatch.setattr(
            AIService, "check_vision_support", AsyncMock(return_value=(False, "llama3.2"))
        )
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        with pytest.raises(NonRetryableJobError, match="does not support vision"):
            await process_one_job(db_session, job)

    async def test_retryable_failure_requeues_with_backoff(
        self, db_session, attachments_dir
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account, attempts=1)
        before = datetime.now(UTC)
        await record_job_failure(db_session, job, httpx.ConnectError("refused"))
        assert job.status == "queued"
        assert job.error and "refused" in job.error
        assert job.available_at > before
        assert job.transaction_id is None  # no stub while retries remain

    async def test_terminal_failure_creates_stub_with_image(
        self, db_session, attachments_dir
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account, attempts=3)
        await record_job_failure(db_session, job, httpx.ConnectError("refused"))

        assert job.status == "error"
        txn = await db_session.get(Transaction, job.transaction_id)
        assert txn is not None
        assert txn.amount == Decimal("0")
        assert txn.approved is False
        assert txn.created_via == "ai_receipt"
        assert txn.memo == FAILURE_STUB_MEMO
        attachment = await db_session.get(TransactionAttachment, job.attachment_id)
        assert attachment is not None
        assert (attachments_dir / attachment.storage_path).exists()
        assert not (attachments_dir / "ai_staging" / str(job.id)).exists()

    async def test_non_retryable_failure_skips_stub_when_account_gone(
        self, db_session, attachments_dir
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account, attempts=1)
        job.payload = {**job.payload, "account_id": str(uuid.uuid4())}
        await db_session.flush()
        await record_job_failure(db_session, job, NonRetryableJobError("account gone"))
        assert job.status == "error"
        assert job.transaction_id is None


class TestReceiptGate:
    async def test_not_a_receipt_is_terminal_and_skips_extraction(
        self, db_session, attachments_dir, monkeypatch
    ):
        monkeypatch.setattr(
            AIService, "check_vision_support", AsyncMock(return_value=(None, "gemma4"))
        )
        monkeypatch.setattr(AIService, "is_receipt_image", AsyncMock(return_value=False))
        extract = AsyncMock(return_value=GOOD_EXTRACTION)
        monkeypatch.setattr(AIService, "extract_receipt", extract)

        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        with pytest.raises(NonRetryableJobError, match="doesn't appear to be a receipt"):
            await process_one_job(db_session, job)
        extract.assert_not_called()

        # The terminal-failure path then produces the stub with the image
        await record_job_failure(db_session, job, NonRetryableJobError("not a receipt"))
        assert job.status == "error"
        txn = await db_session.get(Transaction, job.transaction_id)
        assert txn is not None
        assert txn.amount == Decimal("0")
        assert job.attachment_id is not None

    async def test_inconclusive_gate_proceeds_to_extraction(
        self, db_session, attachments_dir, monkeypatch
    ):
        monkeypatch.setattr(
            AIService, "check_vision_support", AsyncMock(return_value=(None, "gemma4"))
        )
        monkeypatch.setattr(AIService, "is_receipt_image", AsyncMock(return_value=None))
        monkeypatch.setattr(
            AIService, "extract_receipt", AsyncMock(return_value=GOOD_EXTRACTION)
        )
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        await process_one_job(db_session, job)
        assert job.status == "done"


class TestPDFReceipts:
    async def test_pdf_receipt_processes_end_to_end(
        self, db_session, attachments_dir, mock_extraction
    ):
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "WHOLE FOODS — TOTAL $42.50")
        pdf_bytes = doc.tobytes()
        doc.close()

        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        staged = attachments_dir / "ai_staging" / str(job.id) / "receipt.jpg"
        staged.write_bytes(pdf_bytes)  # payload content_type is sniffed, not trusted
        job.payload = {
            **job.payload,
            "original_filename": "receipt.pdf",
            "content_type": "application/pdf",
        }
        await db_session.flush()

        await process_one_job(db_session, job)

        assert job.status == "done"
        attachment = await db_session.get(TransactionAttachment, job.attachment_id)
        assert attachment.content_type == "application/pdf"
        stored = attachments_dir / attachment.storage_path
        assert stored.suffix == ".pdf"
        assert stored.read_bytes()[:5] == b"%PDF-"
        assert (stored.parent / f"thumb_{stored.name}").exists()


class TestStubRefillOnRetry:
    async def test_retry_fills_untouched_stub(
        self, db_session, attachments_dir, mock_extraction
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account, attempts=3)
        await record_job_failure(db_session, job, httpx.ConnectError("refused"))
        stub_id = job.transaction_id
        attachment_id = job.attachment_id
        assert stub_id is not None

        # user retries: endpoint resets to queued, worker claims → processing.
        # Staging was consumed when the image attached to the stub — the
        # refill path must read the stored attachment instead.
        assert not (attachments_dir / "ai_staging" / str(job.id)).exists()
        job.status = "processing"
        job.attempts = 1
        await db_session.flush()

        await process_one_job(db_session, job)

        assert job.status == "done"
        assert job.transaction_id == stub_id  # same transaction, filled in
        assert job.attachment_id == attachment_id  # no duplicate attachment
        txn = await db_session.get(Transaction, stub_id)
        assert txn.amount == Decimal("-42.50")
        assert txn.payee_id is not None
        attachments = (
            await db_session.execute(
                TransactionAttachment.__table__.select().where(
                    TransactionAttachment.transaction_id == stub_id
                )
            )
        ).fetchall()
        assert len(attachments) == 1

    async def test_retry_overwrites_unapproved_edits(
        self, db_session, attachments_dir, mock_extraction
    ):
        # Retry/Reprocess is an explicit click: while the transaction is still
        # unapproved and uncleared it belongs to the AI pipeline, so even a
        # hand-edited amount gets replaced by the fresh extraction.
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account, attempts=3)
        await record_job_failure(db_session, job, httpx.ConnectError("refused"))

        txn = await db_session.get(Transaction, job.transaction_id)
        txn.amount = Decimal("-99.00")
        job.status = "processing"
        job.attempts = 1
        await db_session.flush()

        await process_one_job(db_session, job)

        assert job.status == "done"
        txn = await db_session.get(Transaction, job.transaction_id)
        assert txn.amount == Decimal("-42.50")

    @pytest.mark.parametrize("edit", ["approved", "cleared"])
    async def test_retry_refuses_approved_or_cleared(
        self, db_session, attachments_dir, mock_extraction, edit
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account, attempts=3)
        await record_job_failure(db_session, job, httpx.ConnectError("refused"))

        txn = await db_session.get(Transaction, job.transaction_id)
        if edit == "approved":
            txn.approved = True
        else:
            txn.cleared = "cleared"
        job.status = "processing"
        job.attempts = 1
        await db_session.flush()

        with pytest.raises(NonRetryableJobError, match="approved or cleared"):
            await process_one_job(db_session, job)


class TestReprocess:
    async def _process_to_done(self, db_session, attachments_dir, budget, account) -> AIJob:
        job = await _make_job(db_session, attachments_dir, budget, account)
        await process_one_job(db_session, job)
        assert job.status == "done"
        return job

    def _reset_like_reprocess_endpoint(self, job: AIJob) -> None:
        # Mirrors POST /ai/jobs/{id}/reprocess: full reset of run state, but
        # transaction_id/attachment_id are kept so the same rows get refreshed.
        job.status = "processing"
        job.attempts = 1
        job.error = None
        job.result = None
        job.model = None

    async def test_reprocess_done_job_updates_same_transaction(
        self, db_session, attachments_dir, mock_extraction
    ):
        budget, account = await _setup(db_session, attachments_dir)
        job = await self._process_to_done(db_session, attachments_dir, budget, account)
        txn_id, attachment_id = job.transaction_id, job.attachment_id

        self._reset_like_reprocess_endpoint(job)
        await db_session.flush()
        await process_one_job(db_session, job)

        assert job.status == "done"
        assert job.transaction_id == txn_id
        assert job.attachment_id == attachment_id
        txn = await db_session.get(Transaction, txn_id)
        assert txn.amount == Decimal("-42.50")
        attachments = (
            await db_session.execute(
                TransactionAttachment.__table__.select().where(
                    TransactionAttachment.transaction_id == txn_id
                )
            )
        ).fetchall()
        assert len(attachments) == 1

    async def test_reprocess_after_delete_creates_fresh_transaction(
        self, db_session, attachments_dir, mock_extraction
    ):
        # The user's bug: delete the AI-created transaction, then hit
        # Reprocess. The job still points at the deleted row — the worker
        # must start over instead of failing "transaction was deleted".
        budget, account = await _setup(db_session, attachments_dir)
        job = await self._process_to_done(db_session, attachments_dir, budget, account)
        old_txn_id, old_attachment_id = job.transaction_id, job.attachment_id

        txn = await db_session.get(Transaction, old_txn_id)
        txn.is_deleted = True
        self._reset_like_reprocess_endpoint(job)
        await db_session.flush()

        await process_one_job(db_session, job)

        assert job.status == "done"
        assert job.transaction_id is not None and job.transaction_id != old_txn_id
        assert job.attachment_id is not None and job.attachment_id != old_attachment_id
        new_txn = await db_session.get(Transaction, job.transaction_id)
        assert new_txn.amount == Decimal("-42.50")
        assert new_txn.is_deleted is False
        attachments = (
            await db_session.execute(
                TransactionAttachment.__table__.select().where(
                    TransactionAttachment.transaction_id == job.transaction_id
                )
            )
        ).fetchall()
        assert len(attachments) == 1


class TestRequestLogging:
    """job.result carries the exact prompt/flags sent to the model — on
    success alongside the extraction, and alone when the call fails."""

    def _patch(self, monkeypatch, *, fail: bool = False):
        monkeypatch.setattr(
            AIService, "check_vision_support", AsyncMock(return_value=(None, "gemma4"))
        )
        monkeypatch.setattr(AIService, "is_receipt_image", AsyncMock(return_value=True))

        async def fake_extract(self, budget_id, image_b64, client_today):
            self.last_request = {
                "prompt": "PROMPT",
                "system": "SYSTEM",
                "model": "gemma4",
                "think": True,
                "format": None,
            }
            if fail:
                raise httpx.ConnectError("refused")
            return GOOD_EXTRACTION

        monkeypatch.setattr(AIService, "extract_receipt", fake_extract)

    async def test_success_result_carries_request(
        self, db_session, attachments_dir, monkeypatch
    ):
        self._patch(monkeypatch)
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        await process_one_job(db_session, job)
        assert job.status == "done"
        assert job.result["request"]["prompt"] == "PROMPT"
        assert job.result["extraction"]["payee"] == "Whole Foods"

    async def test_failed_call_still_persists_request(
        self, db_session, attachments_dir, monkeypatch
    ):
        self._patch(monkeypatch, fail=True)
        budget, account = await _setup(db_session, attachments_dir)
        job = await _make_job(db_session, attachments_dir, budget, account)
        with pytest.raises(httpx.ConnectError):
            await process_one_job(db_session, job)
        assert job.result == {"request": {
            "prompt": "PROMPT",
            "system": "SYSTEM",
            "model": "gemma4",
            "think": True,
            "format": None,
        }}


class TestStartupRecovery:
    async def test_stale_processing_requeued(self, db_session, attachments_dir):
        budget, account = await _setup(db_session, attachments_dir)
        stale = await _make_job(db_session, attachments_dir, budget, account, attempts=2)
        done = await _make_job(
            db_session, attachments_dir, budget, account, status="done", attempts=1
        )
        repo = AIJobRepository(db_session)
        count = await repo.reset_stale_processing()
        assert count == 1
        await db_session.refresh(stale)
        await db_session.refresh(done)
        assert stale.status == "queued"
        assert stale.attempts == 2  # attempts preserved
        assert done.status == "done"

    async def test_claim_next_respects_available_at(self, db_session, attachments_dir):
        from datetime import timedelta

        budget, account = await _setup(db_session, attachments_dir)
        future = await _make_job(
            db_session,
            attachments_dir,
            budget,
            account,
            status="queued",
            available_at=datetime.now(UTC) + timedelta(hours=1),
        )
        ready = await _make_job(
            db_session,
            attachments_dir,
            budget,
            account,
            status="queued",
            available_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        repo = AIJobRepository(db_session)
        claimed = await repo.claim_next()
        assert claimed is not None
        assert claimed.id == ready.id
        assert claimed.id != future.id
