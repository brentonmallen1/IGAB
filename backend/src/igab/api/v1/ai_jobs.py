import uuid
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from igab.api.route import CommitRoute
from igab.api.v1.attachments import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE,
    TOO_LARGE_DETAIL,
)
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
    get_attachment_repo,
    get_settings_service,
    get_transaction_repo,
    get_transaction_service,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.ai_job_repo import AIJobRepository
from igab.repositories.attachment_repo import AttachmentRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.ai_draft_service import AIDraftService, parse_extraction
from igab.services.ai_service import AIService
from igab.services.settings_service import SettingsService
from igab.services.transaction_service import TransactionService
from igab.tasks.ai_worker import ai_worker, cleanup_staging, staging_dir
from igab.utils.clock import recorded_on

router = APIRouter(route_class=CommitRoute)


async def _get_owned_job(repo: AIJobRepository, job_id: uuid.UUID, budget_id: uuid.UUID) -> AIJob:
    job = await repo.get(job_id)
    if job is None or str(job.budget_id) != str(budget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    return job


async def _removed_transaction_ids(repo: AIJobRepository, jobs: list[AIJob]) -> set[uuid.UUID]:
    """Transaction ids referenced by these jobs that no longer resolve."""
    txn_ids = list({j.transaction_id for j in jobs if j.transaction_id is not None})
    if not txn_ids:
        return set()
    existing = await repo.existing_transaction_ids(txn_ids)
    return {tid for tid in txn_ids if tid not in existing}


def _safe_filename(name: str | None) -> str:
    """Reduce an uploaded filename to a bare basename that cannot escape a directory.

    Starlette hands back the Content-Disposition filename verbatim, so this is
    attacker-controlled, and joining it onto a Path is what makes that dangerous:
    `Path(base) / "../../x"` walks out of the staging directory, and worse, an
    absolute component discards `base` entirely — `Path("/a/b") / "/etc/cron.d/x"`
    is just `/etc/cron.d/x`. Either one turns a receipt upload into an arbitrary
    file write.

    PurePosixPath().name keeps the last component and drops any directory part;
    backslashes are folded too, since they are not separators on POSIX and would
    otherwise survive into the stored name. "..", "/" and "" all reduce to
    nothing, hence the fallback.
    """
    candidate = PurePosixPath(name or "").name.replace("\\", "_").strip()
    # PurePosixPath("..").name is ".." rather than "", and `stage_dir / ".."`
    # is the parent directory — a failed write rather than an escaped one, but
    # not something to hand to the filesystem either.
    if candidate in {"", ".", ".."}:
        return "receipt.jpg"
    return candidate


def _parse_client_today(value: str | None) -> date:
    """The multipart spelling of `ClientDated`: this endpoint takes Form
    fields, so the date arrives as a string and is parsed by hand rather than
    by pydantic. The ranking itself is `clock.recorded_on`, so the receipt
    flow and the asset/liability bodies cannot drift about which clock wins.
    """
    if not value:
        return recorded_on(None, None)
    try:
        return recorded_on(None, date.fromisoformat(value))
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
    attachment_repo: Annotated[AttachmentRepository, Depends(get_attachment_repo)],
    settings_svc: Annotated[SettingsService, Depends(get_settings_service)],
    file: UploadFile = File(...),
    account_id: uuid.UUID = Form(...),
    client_today: str | None = Form(None),
) -> AIJobResponse:
    """Queue a receipt photo for AI extraction. Returns immediately; the
    worker creates a needs-review transaction with the image attached.

    Deliberately does NOT check whether the model can do vision. This used to
    reject the upload with a 422 before anything was persisted, which
    destroyed the photo — the user had nothing to retry and no record it ever
    happened. Every model/availability problem now belongs to the worker,
    which already degrades correctly: a terminal failure still produces a $0
    needs-review transaction with the image attached (_create_failure_stub),
    so a receipt is never stranded. Only malformed requests are rejected here.
    """
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
            detail=TOO_LARGE_DETAIL,
        )

    # Submitting the same receipt twice would double-count the expense. Unlike
    # the capability gate this endpoint used to have, refusing here loses
    # nothing: the image is demonstrably already in the budget, and the
    # response carries the transaction so the client can offer to open it.
    duplicate = await attachment_repo.find_duplicate_in_budget(
        budget_id, sha256(content).hexdigest()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "You've already added this receipt",
                "transaction_id": str(duplicate.transaction_id),
            },
        )

    today = _parse_client_today(client_today)
    job_id = uuid.uuid4()
    original_filename = _safe_filename(file.filename)

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
    # must see the row. `CommitRoute` commits too, but only once this handler
    # returns, and `notify()` happens inside it. This one stays.
    #
    # It was also the first sighting of the wider defect: the original comment
    # here read "get_session would otherwise commit after we return", which is
    # true of every mutating route in the app, not just this one. See
    # `igab.api.route`.
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
    removed = await _removed_transaction_ids(job_repo, jobs)
    return AIJobListResponse(
        jobs=[
            AIJobResponse.from_job(j, transaction_removed=j.transaction_id in removed) for j in jobs
        ],
        total_count=total,
    )


@router.get("/{budget_id}/ai/jobs/active-count", response_model=ActiveCountResponse)
async def active_job_count(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> ActiveCountResponse:
    """Badge counts: work in flight, and work waiting for the user."""
    return ActiveCountResponse(
        count=await job_repo.active_count(budget_id),
        needs_review=await txn_repo.count_ai_needs_review(budget_id),
    )


@router.get("/{budget_id}/ai/jobs/{job_id}", response_model=AIJobResponse)
async def get_job(
    budget_id: BudgetAccess,
    job_id: uuid.UUID,
    current_user: CurrentUser,
    job_repo: Annotated[AIJobRepository, Depends(get_ai_job_repo)],
) -> AIJobResponse:
    job = await _get_owned_job(job_repo, job_id, budget_id)
    removed = await _removed_transaction_ids(job_repo, [job])
    return AIJobResponse.from_job(job, transaction_removed=job.transaction_id in removed)


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


# The job lifecycle (retry, reprocess, delete) is deliberately absent from
# the change log (see change_log.py's exclusion list): job rows are worker
# state whose fields the worker overwrites at will — undoing a retry would
# fight the queue, not restore budget data. What a job DID to the budget —
# the transaction it created — records through TransactionService as
# source="ai" and undoes like any other row.
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
