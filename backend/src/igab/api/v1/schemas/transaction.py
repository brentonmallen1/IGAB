import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel

from igab.domain.enums import UserClearedStatus
from igab.domain.money import Money


class SplitCreate(BaseModel):
    amount: Money
    category_id: uuid.UUID | None = None
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    memo: str | None = None


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    date: datetime.date
    amount: Money
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: UserClearedStatus = UserClearedStatus.UNCLEARED
    approved: bool = True
    transfer_account_id: uuid.UUID | None = None
    splits: list[SplitCreate] | None = None


class TransactionUpdate(BaseModel):
    """PATCH body: omitted fields are untouched; an explicit null clears the
    nullable fields (category_id, payee_id, memo)."""

    date: datetime.date | None = None
    amount: Money | None = None
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: UserClearedStatus | None = None
    approved: bool | None = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    date: datetime.date
    entered_date: datetime.date | None = None
    amount: Decimal
    payee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    memo: str | None
    cleared: str
    approved: bool
    transfer_id: uuid.UUID | None
    parent_transaction_id: uuid.UUID | None
    is_split: bool
    import_id: str | None
    import_description: str | None
    sync_id: str | None
    sync_source: str | None
    has_sync_source: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class BulkClearedUpdate(BaseModel):
    transaction_ids: list[uuid.UUID]
    cleared: UserClearedStatus


class BulkCategorize(BaseModel):
    transaction_ids: list[uuid.UUID]
    category_id: uuid.UUID


class BulkDelete(BaseModel):
    transaction_ids: list[uuid.UUID]


class BulkApprove(BaseModel):
    transaction_ids: list[uuid.UUID]


class BulkItemFailure(BaseModel):
    id: uuid.UUID
    reason: str


class BulkActionResult(BaseModel):
    updated: list[uuid.UUID]
    failed: list[BulkItemFailure]


class PendingReviewCount(BaseModel):
    unapproved: int
    uncategorized: int
    unapproved_only: int = 0
    uncategorized_only: int = 0
    both: int = 0
    total: int = 0


class MergeTransactionsRequest(BaseModel):
    transaction_ids: list[uuid.UUID]
    survivor_id: uuid.UUID | None = None


class SimilarTransactionResponse(BaseModel):
    id: uuid.UUID
    date: datetime.date
    amount: Decimal
    payee_id: uuid.UUID | None
    memo: str | None
    cleared: str
    import_description: str | None

    model_config = {"from_attributes": True}


class PayeeCreate(BaseModel):
    name: str


class PayeeUpdate(BaseModel):
    name: str | None = None
    default_category_id: uuid.UUID | None = None
    mapping_samples: str | None = None


class PayeeResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    default_category_id: uuid.UUID | None
    transfer_account_id: uuid.UUID | None
    mapping_samples: str | None

    model_config = {"from_attributes": True}


class PayeeWithCount(PayeeResponse):
    transaction_count: int


class PayeeMergeRequest(BaseModel):
    target_id: uuid.UUID
