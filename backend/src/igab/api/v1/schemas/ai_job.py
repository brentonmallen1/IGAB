import uuid
from datetime import date, datetime
from typing import Any

from igab.api.v1.schemas.base import ApiModel
from igab.domain.money import Money

# payload keys safe to expose to the client (staged_path stays internal)
PUBLIC_PAYLOAD_KEYS = ("account_id", "original_filename", "content_type", "text", "client_today")


class ReceiptBankMatch(ApiModel):
    """The existing row a waiting receipt matches, named well enough to
    recognise: where, when, how much."""

    id: uuid.UUID
    account_id: uuid.UUID
    date: date
    amount: Money

    model_config = {"from_attributes": True}


class AIJobResponse(ApiModel):
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
    #: The linked transaction has since been deleted — the log entry outlives
    #: it. Derived from the served `transaction_account_id` (NULL exactly when
    #: the job's transaction is not live), not asked separately: it was once
    #: its own query, run by the list and detail endpoints only, so retry and
    #: reprocess reported a deleted row as present.
    transaction_removed: bool
    #: Is the transaction this job created still waiting for the user?
    #:
    #: Required, not optional. The AI Activity page files rows into "Needs your
    #: approval" or History by this, and a default would file waiting work as
    #: done — silently, which is the failure worth being loud about. Populate
    #: it with `AIJobRepository.with_review` (or `get_with_review`).
    needs_review: bool
    #: Which account the created transaction is in now — None when there is no
    #: transaction (still queued, or deleted since).
    #:
    #: The review list names it, so a receipt filed against the wrong account
    #: is visible before it is approved rather than after someone goes looking
    #: through the registers. Populated by the same loader as `needs_review`,
    #: whose required-ness is what makes a forgotten loader fail loudly: None
    #: here is a real answer and cannot be told apart from an unloaded one.
    transaction_account_id: uuid.UUID | None
    #: Which category the created transaction is filed in now
    #: (`AIJob.transaction_category_id`). None: uncategorized, a split parent,
    #: or no transaction. The review list names it beside the model's own pick
    #: (`result.draft.category`), which is left as the model gave it.
    transaction_category_id: uuid.UUID | None
    #: The created transaction is a split parent, so its category is its lines'
    #: and cannot be set here. False with no transaction. Required, and
    #: non-null: a path that skipped the loader fails validation rather than
    #: reading a split as uncategorized.
    transaction_is_split: bool
    #: Which account owns the card ending printed on the receipt, as of now
    #: (`AIJob.card_ending_account_id`). None: no ending on the receipt, or
    #: none on file. Beside `transaction_account_id` it says whether the scan
    #: sits in the account whose card paid.
    card_ending_account_id: uuid.UUID | None
    #: For a receipt waiting for an account: the one row in the budget it
    #: could be the paper for (`receipt_placement.bank_match`), asked at
    #: read time because the bank's row usually arrives after the photo.
    #: None for every other job, and when no row — or more than one — fits.
    bank_match: ReceiptBankMatch | None = None
    attachment_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_job(cls, job, *, bank_match=None) -> "AIJobResponse":
        payload = job.payload or {}
        if job.needs_review is None:
            raise RuntimeError(
                "AIJob.needs_review was not loaded — query through "
                "AIJobRepository.with_review or get_with_review. Serving a "
                "default here would report waiting work as done."
            )
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
            transaction_removed=(
                job.transaction_id is not None and job.transaction_account_id is None
            ),
            needs_review=job.needs_review,
            transaction_account_id=job.transaction_account_id,
            transaction_category_id=job.transaction_category_id,
            transaction_is_split=job.transaction_is_split,
            card_ending_account_id=job.card_ending_account_id,
            bank_match=ReceiptBankMatch.model_validate(bank_match) if bank_match else None,
            attachment_id=job.attachment_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class AIJobListResponse(ApiModel):
    jobs: list[AIJobResponse]
    total_count: int


class ActiveCountResponse(ApiModel):
    #: Jobs queued or processing right now.
    count: int
    #: AI-created transactions still awaiting review, plus receipts waiting
    #: for an account. Drives the header badge
    #: after the work finishes — `count` alone drops to zero at exactly the
    #: moment there is something for the user to look at.
    needs_review: int = 0


class NLParseRequest(ApiModel):
    text: str
    client_today: str | None = None  # ISO date from the browser (TZ-correct "today")


class NLDraft(ApiModel):
    payee: str | None
    amount: str  # signed decimal string, outflow-negative
    date: str
    category_id: uuid.UUID | None
    category_name: str | None
    memo: str | None
    confidence: float


class NLParseResponse(ApiModel):
    job_id: uuid.UUID
    draft: NLDraft
