import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel

from igab.domain.enums import ClearedStatus


class SplitCreate(BaseModel):
    amount: Decimal
    category_id: uuid.UUID | None = None
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    memo: str | None = None


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    date: datetime.date
    amount: Decimal
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: ClearedStatus = ClearedStatus.UNCLEARED
    approved: bool = True
    transfer_account_id: uuid.UUID | None = None
    splits: list[SplitCreate] | None = None


class TransactionUpdate(BaseModel):
    date: datetime.date | None = None
    amount: Decimal | None = None
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: ClearedStatus | None = None
    approved: bool | None = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    date: datetime.date
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
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class BulkClearedUpdate(BaseModel):
    transaction_ids: list[uuid.UUID]
    cleared: ClearedStatus


class BulkCategorize(BaseModel):
    transaction_ids: list[uuid.UUID]
    category_id: uuid.UUID


class BulkDelete(BaseModel):
    transaction_ids: list[uuid.UUID]


class PayeeCreate(BaseModel):
    name: str


class PayeeUpdate(BaseModel):
    name: str | None = None
    default_category_id: uuid.UUID | None = None


class PayeeResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    default_category_id: uuid.UUID | None
    transfer_account_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class PayeeWithCount(PayeeResponse):
    transaction_count: int


class PayeeMergeRequest(BaseModel):
    target_id: uuid.UUID
