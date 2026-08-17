import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

# payload keys safe to expose to the client (staged_path stays internal)
PUBLIC_PAYLOAD_KEYS = ("account_id", "original_filename", "content_type", "text", "client_today")


class AIJobResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    kind: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    model: str | None
    attempts: int
    max_attempts: int
    transaction_id: uuid.UUID | None
    # The linked transaction has since been deleted — the log entry outlives it
    transaction_removed: bool = False
    attachment_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_job(cls, job, *, transaction_removed: bool = False) -> "AIJobResponse":
        payload = job.payload or {}
        return cls(
            id=job.id,
            budget_id=job.budget_id,
            kind=job.kind,
            status=job.status,
            payload={k: payload[k] for k in PUBLIC_PAYLOAD_KEYS if k in payload},
            result=job.result,
            error=job.error,
            model=job.model,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            transaction_id=job.transaction_id,
            transaction_removed=transaction_removed,
            attachment_id=job.attachment_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class AIJobListResponse(BaseModel):
    jobs: list[AIJobResponse]
    total_count: int


class ActiveCountResponse(BaseModel):
    count: int


class NLParseRequest(BaseModel):
    text: str
    client_today: str | None = None  # ISO date from the browser (TZ-correct "today")


class NLDraft(BaseModel):
    payee: str | None
    amount: str  # signed decimal string, outflow-negative
    date: str
    category_id: uuid.UUID | None
    category_name: str | None
    memo: str | None
    confidence: float


class NLParseResponse(BaseModel):
    job_id: uuid.UUID
    draft: NLDraft
