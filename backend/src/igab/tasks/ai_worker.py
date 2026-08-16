"""In-process asyncio worker for the ai_jobs queue.

A single long-lived loop (not an APScheduler job — the scheduler keeps its
cron work) claims queued jobs one at a time and processes them. Local Ollama
serializes inference anyway, so sequential processing wastes nothing; the
FOR UPDATE SKIP LOCKED claim in the repo keeps the door open for concurrency
later.

Jobs live in Postgres, so restarts lose nothing: startup_recovery() resets
rows stuck in 'processing' by a crash and the loop picks up queued work.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from igab.config import settings as app_settings
from igab.db.models import AIJob, Transaction
from igab.domain.exceptions import InvariantViolation

logger = logging.getLogger(__name__)

RETRY_BASE_DELAY_S = 30
POLL_INTERVAL_S = 15
SHUTDOWN_GRACE_S = 10

FAILURE_STUB_MEMO = "Receipt scan failed — enter details from the image"


class NonRetryableJobError(Exception):
    """Permanent input problem (missing file, deleted account, no vision
    support). Goes straight to 'error' without burning retries."""


def staging_dir(job_id: uuid.UUID) -> Path:
    return Path(app_settings.ATTACHMENTS_DIR) / "ai_staging" / str(job_id)


def cleanup_staging(job_id: uuid.UUID) -> None:
    shutil.rmtree(staging_dir(job_id), ignore_errors=True)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, NonRetryableJobError):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, httpx.TransportError):  # timeouts, connect errors, etc.
        return True
    # Model output quality: bad JSON or an extraction that failed validation
    # (zero total, garbage amount). Non-deterministic — worth another attempt.
    if isinstance(exc, (json.JSONDecodeError, ValueError, InvariantViolation)):
        return True
    return False


def _draft_result_json(draft) -> dict:
    return {
        "extraction": draft.raw,
        "draft": {
            "payee": draft.payee_name,
            "amount": str(draft.amount),
            "date": draft.date.isoformat(),
            "category": draft.category_name,
            "memo": draft.memo,
            "confidence": draft.confidence,
        },
        "suggested_split": (
            [{"category": s.category_name, "amount": str(s.amount)} for s in draft.suggested_split]
            if draft.suggested_split
            else None
        ),
    }


def _build_services(session: AsyncSession):
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.attachment_repo import AttachmentRepository
    from igab.repositories.category_repo import CategoryRepository
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.settings_repo import SettingsRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.ai_draft_service import AIDraftService
    from igab.services.ai_service import AIService
    from igab.services.attachment_service import AttachmentService
    from igab.services.settings_service import SettingsService
    from igab.services.transaction_service import TransactionService

    txn_svc = TransactionService(
        session,
        TransactionRepository(session),
        AccountRepository(session),
        CategoryRepository(session),
        PayeeRepository(session),
    )
    return {
        "ai": AIService(session, SettingsService(SettingsRepository(session))),
        "transactions": txn_svc,
        "drafts": AIDraftService(txn_svc),
        "attachments": AttachmentService(AttachmentRepository(session)),
    }


async def process_one_job(session: AsyncSession, job: AIJob) -> None:
    """Process a claimed job in the given session. Raises on failure; the
    caller decides retry vs terminal. Standalone so tests can drive it
    directly without the loop."""
    if job.kind == "receipt":
        await _process_receipt(session, job)
    else:
        raise NonRetryableJobError(f"Job kind '{job.kind}' has no async processor")


async def _process_receipt(session: AsyncSession, job: AIJob) -> None:
    from igab.services.ai_draft_service import parse_extraction
    from igab.services.ai_service import prepare_image_for_model

    payload = job.payload or {}
    staged_rel = payload.get("staged_path")
    staged = Path(app_settings.ATTACHMENTS_DIR) / staged_rel if staged_rel else None
    file_bytes: bytes | None = None
    if staged is not None and staged.exists():
        file_bytes = staged.read_bytes()
    elif job.attachment_id is not None:
        # Retry after a terminal failure: staging was consumed when the image
        # was attached to the stub — read the stored attachment instead.
        from igab.repositories.attachment_repo import AttachmentRepository

        attachment = await AttachmentRepository(session).get_by_id(job.attachment_id)
        if attachment is not None and attachment.storage_path:
            stored = Path(app_settings.ATTACHMENTS_DIR) / attachment.storage_path
            if stored.exists():
                file_bytes = stored.read_bytes()
    if file_bytes is None:
        raise NonRetryableJobError("Receipt image is missing")

    svcs = _build_services(session)
    account_id = uuid.UUID(payload["account_id"])
    account = await svcs["transactions"].account_repo.get(account_id)
    if account is None or str(account.budget_id) != str(job.budget_id):
        raise NonRetryableJobError("Account for this receipt no longer exists")

    supported, model = await svcs["ai"].check_vision_support()
    job.model = model  # Record which model processed this job
    if supported is False:
        raise NonRetryableJobError(
            f"Model '{model}' does not support vision — set a vision model in Settings → AI"
        )

    client_today = (
        date.fromisoformat(payload["client_today"])
        if payload.get("client_today")
        else datetime.now(UTC).date()
    )

    image_b64 = prepare_image_for_model(file_bytes)

    # Cheap gate before the expensive structured extraction: a photo of the
    # dog isn't a receipt. Not-a-receipt is terminal — the failure path still
    # creates the $0 stub with the image so the user can decide.
    # Inconclusive (None) proceeds: the gate must never block a real receipt.
    if await svcs["ai"].is_receipt_image(image_b64) is False:
        raise NonRetryableJobError(
            "The image doesn't appear to be a receipt — created an empty "
            "transaction with the image attached for manual entry"
        )

    try:
        raw = await svcs["ai"].extract_receipt(job.budget_id, image_b64, client_today)
    finally:
        # Persist the exact prompt/flags for debugging — also when the call
        # fails, so a bad extraction can be replayed outside the app.
        if svcs["ai"].last_request is not None:
            job.result = {"request": svcs["ai"].last_request}

    categories = await svcs["transactions"].category_repo.get_all_with_group_names(job.budget_id)
    draft = parse_extraction(
        raw,
        kind="receipt",
        client_today=client_today,
        category_names=[(cat.name, group) for cat, group in categories],
    )

    txn: Transaction | None = None
    if job.transaction_id is not None:
        # A prior run already produced a transaction (failure stub, or a done
        # job being reprocessed): refresh it in place while it still belongs
        # to the AI pipeline.
        txn = await _apply_draft_to_existing(svcs, job, draft)
        if txn is None:
            # The transaction was deleted since — start over with a fresh one.
            # The old attachment belongs to the deleted row, so re-attach too.
            job.transaction_id = None
            job.attachment_id = None
    if txn is None:
        txn = await svcs["drafts"].create_transaction(
            job.budget_id, account_id, draft, created_via="ai_receipt"
        )

    if job.attachment_id is None:
        attachment = await svcs["attachments"].upload(
            txn,
            file_bytes,
            payload.get("original_filename") or "receipt.jpg",
            payload.get("content_type") or "image/jpeg",
        )
        job.attachment_id = attachment.id

    result = _draft_result_json(draft)
    if svcs["ai"].last_request is not None:
        result["request"] = svcs["ai"].last_request
    job.result = result
    job.transaction_id = txn.id
    job.status = "done"
    job.error = None
    job.finished_at = datetime.now(UTC)
    session.add(job)
    await session.flush()
    cleanup_staging(job.id)


async def _apply_draft_to_existing(svcs: dict, job: AIJob, draft) -> Transaction | None:
    """Refresh the job's existing transaction (a failure stub, or the result
    of a done job being reprocessed) with a freshly extracted draft.

    Returns None when the transaction was deleted so the caller can create a
    replacement. An approved or cleared transaction belongs to the user —
    refuse rather than overwrite."""
    from igab.services.transaction_service import TransactionCreate, TransactionUpdate

    txn_svc = svcs["transactions"]
    txn = await txn_svc.transaction_repo.get(job.transaction_id)
    if txn is None:
        return None
    if txn.approved or txn.cleared != "uncleared":
        raise NonRetryableJobError(
            "The transaction for this receipt was already approved or cleared"
            " — edit it directly, or delete it first to reprocess from scratch"
        )

    payee = await txn_svc._resolve_payee(
        job.budget_id,
        TransactionCreate(
            account_id=txn.account_id,
            date=draft.date,
            amount=draft.amount,
            payee_name=draft.payee_name,
        ),
    )
    category_id = await svcs["drafts"].resolve_category(job.budget_id, draft.category_name)
    return await txn_svc.update(
        job.budget_id,
        txn.id,
        TransactionUpdate(
            date=draft.date,
            amount=draft.amount,
            payee_id=payee.id if payee else None,
            category_id=category_id,
            memo=draft.memo,
        ),
    )


async def record_job_failure(session: AsyncSession, job: AIJob, exc: Exception) -> None:
    """Retry with backoff when the error is transient and attempts remain;
    otherwise terminal — for receipts, the $0 stub keeps the image reachable."""
    job.error = f"{type(exc).__name__}: {exc}"[:2000]
    if _is_retryable(exc) and job.attempts < job.max_attempts:
        job.status = "queued"
        delay = RETRY_BASE_DELAY_S * (2 ** (job.attempts - 1))
        job.available_at = datetime.now(UTC) + timedelta(seconds=delay)
    else:
        job.status = "error"
        job.finished_at = datetime.now(UTC)
        if job.kind == "receipt":
            try:
                await _create_failure_stub(session, job)
            except Exception:
                logger.exception("ai_worker: failure stub creation failed for %s", job.id)
    session.add(job)
    await session.flush()


async def _create_failure_stub(session: AsyncSession, job: AIJob) -> None:
    """Terminal receipt failure: still create a $0 needs-review transaction
    with the image attached, so the receipt is never stranded and the user
    can finish it by hand in the review modal."""
    from decimal import Decimal

    from igab.services.transaction_service import TransactionCreate

    if job.transaction_id is not None:
        return
    payload = job.payload or {}
    staged_rel = payload.get("staged_path")
    staged = Path(app_settings.ATTACHMENTS_DIR) / staged_rel if staged_rel else None

    svcs = _build_services(session)
    account_id = uuid.UUID(payload["account_id"])
    account = await svcs["transactions"].account_repo.get(account_id)
    if account is None or str(account.budget_id) != str(job.budget_id):
        return  # nothing to hang the stub on

    client_today = (
        date.fromisoformat(payload["client_today"])
        if payload.get("client_today")
        else datetime.now(UTC).date()
    )
    txn = await svcs["transactions"].create(
        job.budget_id,
        TransactionCreate(
            account_id=account_id,
            date=client_today,
            amount=Decimal("0"),
            memo=FAILURE_STUB_MEMO,
            approved=False,
            created_via="ai_receipt",
        ),
    )
    job.transaction_id = txn.id
    if staged is not None and staged.exists():
        attachment = await svcs["attachments"].upload(
            txn,
            staged.read_bytes(),
            payload.get("original_filename") or "receipt.jpg",
            payload.get("content_type") or "image/jpeg",
        )
        job.attachment_id = attachment.id
        cleanup_staging(job.id)
    session.add(job)
    await session.flush()


class AIJobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()

    def notify(self) -> None:
        """Wake the loop — called by submit/retry endpoints after commit."""
        self._wake.set()

    async def startup_recovery(self) -> None:
        from igab.db.session import AsyncSessionLocal
        from igab.repositories.ai_job_repo import AIJobRepository

        async with AsyncSessionLocal() as session:
            try:
                count = await AIJobRepository(session).reset_stale_processing()
                await session.commit()
                if count:
                    logger.info("ai_worker: re-queued %d stale processing job(s)", count)
            except Exception:
                await session.rollback()
                logger.exception("ai_worker: startup recovery failed")

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="ai-job-worker")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=SHUTDOWN_GRACE_S)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=POLL_INTERVAL_S)
            except TimeoutError:
                pass
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                await self._drain()
            except Exception:
                # The loop must survive anything — errors are recorded per-job.
                logger.exception("ai_worker: drain crashed")

    async def _drain(self) -> None:
        while not self._stop.is_set():
            if not await self._claim_and_process_next():
                break

    async def _claim_and_process_next(self) -> bool:
        from igab.db.session import AsyncSessionLocal
        from igab.repositories.ai_job_repo import AIJobRepository

        async with AsyncSessionLocal() as session:
            repo = AIJobRepository(session)
            job = await repo.claim_next()
            if job is None:
                await session.rollback()
                return False
            job.status = "processing"
            job.attempts += 1
            job.started_at = datetime.now(UTC)
            session.add(job)
            await session.commit()
            job_id = job.id

        # Fresh session per job so a processing failure's rollback can never
        # undo the claim above or leak into API request sessions.
        async with AsyncSessionLocal() as session:
            repo = AIJobRepository(session)
            job = await repo.get_or_raise(job_id)
            try:
                await process_one_job(session, job)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                await self._record_failure(job_id, exc)
        return True

    async def _record_failure(self, job_id: uuid.UUID, exc: Exception) -> None:
        from igab.db.session import AsyncSessionLocal
        from igab.repositories.ai_job_repo import AIJobRepository

        logger.warning("ai_worker: job %s failed: %s", job_id, exc)
        async with AsyncSessionLocal() as session:
            try:
                repo = AIJobRepository(session)
                job = await repo.get(job_id)
                if job is None:
                    return
                await record_job_failure(session, job, exc)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("ai_worker: could not record failure for %s", job_id)


ai_worker = AIJobWorker()


async def sweep_orphaned_staging() -> None:
    """Daily sweep: staging dirs whose job vanished (crash between file write
    and row insert, or manual DB surgery) get removed."""
    from sqlalchemy import select

    from igab.db.models import AIJob
    from igab.db.session import AsyncSessionLocal

    root = Path(app_settings.ATTACHMENTS_DIR) / "ai_staging"
    if not root.is_dir():
        return
    dir_ids: set[str] = {p.name for p in root.iterdir() if p.is_dir()}
    if not dir_ids:
        return
    valid_ids: list[uuid.UUID] = []
    for name in dir_ids:
        try:
            valid_ids.append(uuid.UUID(name))
        except ValueError:
            continue
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AIJob.id).where(AIJob.id.in_(valid_ids)))
        known = {str(r) for r in result.scalars().all()}
    for name in dir_ids:
        if name not in known:
            shutil.rmtree(root / name, ignore_errors=True)
