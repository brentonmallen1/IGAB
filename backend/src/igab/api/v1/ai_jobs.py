import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from igab.api.v1.attachments import ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE
from igab.api.v1.schemas.ai_job import (
    ActiveCountResponse,
    AIJobListResponse,
    AIJobResponse,
    NLDraft,
    NLParseRequest,
    NLParseResponse,
)
from igab.db.models import AIJob
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    SessionDep,
    get_account_repo,
    get_ai_job_repo,
    get_ai_service,
    get_settings_service,
    get_transaction_service,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.ai_job_repo import AIJobRepository
from igab.services.ai_draft_service import AIDraftService, parse_extraction
from igab.services.ai_service import AIService
from igab.services.settings_service import SettingsService
from igab.services.transaction_service import TransactionService
from igab.tasks.ai_worker import ai_worker, cleanup_staging, staging_dir

router = APIRouter()


async def _get_owned_job(repo: AIJobRepository, job_id: uuid.UUID, budget_id: uuid.UUID) -> AIJob:
    job = await repo.get(job_id)
    if job is None or str(job.budget_id) != str(budget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    return job


def _parse_client_today(value: str | None) -> date:
    if not value:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="client_today must be an ISO date (YYYY-MM-DD)",
        )


@router.post(
    "/{budget_id}/ai/receipts",
    response_model=AIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_receipt(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
    settings_svc: Annotated[SettingsService, Depends(get_settings_service)],
    file: UploadFile = File(...),
    account_id: uuid.UUID = Form(...),
    client_today: str | None = Form(None),
) -> AIJobResponse:
    """Queue a receipt photo for AI extraction. Returns immediately; the
    worker creates a needs-review transaction with the image attached."""
    if not await settings_svc.get("ollama_host"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not configured — set a host in Settings → AI",
        )

    account = await account_repo.get(account_id)
    if account is None or str(account.budget_id) != str(budget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed",
        )
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 20MB)",
        )

    # Fail fast with a clear message when the configured model definitely
    # lacks vision. Unknown (older Ollama, server down) lets the job try.
    supported, model = await ai_svc.check_vision_support()
    if supported is False:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Model '{model}' does not support vision — enable a vision model in Settings → AI"
            ),
        )

    today = _parse_client_today(client_today)
    job_id = uuid.uuid4()
    original_filename = file.filename or "receipt.jpg"

    stage_dir = staging_dir(job_id)
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / original_filename).write_bytes(content)

    job = await job_repo.create(
        id=job_id,
        budget_id=budget_id,
        kind="receipt",
        status="queued",
        payload={
            "account_id": str(account_id),
            "original_filename": original_filename,
            "content_type": file.content_type or "image/jpeg",
            "staged_path": f"ai_staging/{job_id}/{original_filename}",
            "client_today": today.isoformat(),
        },
    )
    # Commit before waking the worker — it reads from its own session and
    # must see the row (get_session would otherwise commit after we return).
    await session.commit()
    ai_worker.notify()
    return AIJobResponse.from_job(job)


@router.get("/{budget_id}/ai/jobs", response_model=AIJobListResponse)
async def list_jobs(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
    status_filter: str | None = None,
    kind: str | None = None,
    transaction_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AIJobListResponse:
    jobs, total = await job_repo.list_for_budget(
        budget_id,
        status=status_filter,
        kind=kind,
        transaction_id=transaction_id,
        limit=min(limit, 200),
        offset=offset,
    )
    return AIJobListResponse(jobs=[AIJobResponse.from_job(j) for j in jobs], total_count=total)


@router.get("/{budget_id}/ai/jobs/active-count", response_model=ActiveCountResponse)
async def active_job_count(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> ActiveCountResponse:
    return ActiveCountResponse(count=await job_repo.active_count(budget_id))


@router.get("/{budget_id}/ai/jobs/{job_id}", response_model=AIJobResponse)
async def get_job(
    budget_id: BudgetAccess,
    job_id: uuid.UUID,
    current_user: CurrentUser,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> AIJobResponse:
    job = await _get_owned_job(job_repo, job_id, budget_id)
    return AIJobResponse.from_job(job)


@router.post("/{budget_id}/ai/jobs/{job_id}/retry", response_model=AIJobResponse)
async def retry_job(
    budget_id: BudgetAccess,
    job_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> AIJobResponse:
    job = await _get_owned_job(job_repo, job_id, budget_id)
    if job.status != "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed jobs can be retried",
        )
    job.status = "queued"
    job.attempts = 0
    job.error = None
    job.finished_at = None
    job.available_at = datetime.now(UTC)
    session.add(job)
    await session.commit()
    ai_worker.notify()
    return AIJobResponse.from_job(job)


@router.post("/{budget_id}/ai/jobs/{job_id}/reprocess", response_model=AIJobResponse)
async def reprocess_job(
    budget_id: BudgetAccess,
    job_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> AIJobResponse:
    """Re-queue a completed job to run again with the current model settings.
    Useful after changing models or for getting better results on a failed extraction."""
    job = await _get_owned_job(job_repo, job_id, budget_id)
    if job.status not in ("done", "error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed jobs can be reprocessed",
        )
    job.status = "queued"
    job.attempts = 0
    job.error = None
    job.result = None
    job.model = None  # Will be set when the new model processes it
    job.started_at = None
    job.finished_at = None
    job.available_at = datetime.now(UTC)
    session.add(job)
    await session.commit()
    ai_worker.notify()
    return AIJobResponse.from_job(job)


@router.delete("/{budget_id}/ai/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    budget_id: BudgetAccess,
    job_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> None:
    """Remove a job from the log (and its staged file). Never touches the
    transaction it may have created."""
    job = await _get_owned_job(job_repo, job_id, budget_id)
    if job.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a job while it is processing",
        )
    await session.delete(job)
    await session.flush()
    cleanup_staging(job_id)


@router.post("/{budget_id}/ai/parse-transaction", response_model=NLParseResponse)
async def parse_nl_transaction(
    budget_id: BudgetAccess,
    body: NLParseRequest,
    current_user: CurrentUser,
    session: SessionDep,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
    ai_svc: Annotated[AIService, Depends(get_ai_service)],
    txn_svc: Annotated[TransactionService, Depends(get_transaction_service)],
) -> NLParseResponse:
    """Parse free text into a transaction draft, inline (interactive).

    Records an ai_jobs row for the audit log; the draft feeds the existing
    add-transaction flow, which links back via ai_job_id on create."""
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="text is required"
        )
    today = _parse_client_today(body.client_today)

    job = await job_repo.create(
        budget_id=budget_id,
        kind="nl_parse",
        status="processing",
        attempts=1,
        started_at=datetime.now(UTC),
        payload={"text": text, "client_today": today.isoformat()},
    )

    try:
        raw = await ai_svc.parse_nl_transaction(budget_id, text, today)
        categories = await txn_svc.category_repo.get_all_with_group_names(budget_id)
        draft = parse_extraction(
            raw,
            kind="nl_parse",
            client_today=today,
            category_names=[(cat.name, group) for cat, group in categories],
        )
    except Exception as exc:
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"[:2000]
        if ai_svc.last_request is not None:
            job.result = {"request": ai_svc.last_request}
        job.finished_at = datetime.now(UTC)
        session.add(job)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not parse that into a transaction — try rephrasing",
        )

    category_id = await AIDraftService(txn_svc).resolve_category(budget_id, draft.category_name)
    job.status = "done"
    job.finished_at = datetime.now(UTC)
    result: dict = {
        "extraction": draft.raw,
        "draft": {
            "payee": draft.payee_name,
            "amount": str(draft.amount),
            "date": draft.date.isoformat(),
            "category": draft.category_name,
            "memo": draft.memo,
            "confidence": draft.confidence,
        },
    }
    if ai_svc.last_request is not None:
        result["request"] = ai_svc.last_request
    job.result = result
    session.add(job)
    await session.commit()

    return NLParseResponse(
        job_id=job.id,
        draft=NLDraft(
            payee=draft.payee_name,
            amount=str(draft.amount),
            date=draft.date.isoformat(),
            category_id=category_id,
            category_name=draft.category_name if category_id else None,
            memo=draft.memo,
            confidence=draft.confidence,
        ),
    )
