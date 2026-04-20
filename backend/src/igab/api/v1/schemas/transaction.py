import datetime
import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from igab.domain.enums import ClearedStatus


class SplitCreate(BaseModel):
    amount: Decimal
    category_id: Optional[uuid.UUID] = None
    payee_id: Optional[uuid.UUID] = None
    payee_name: Optional[str] = None
    memo: Optional[str] = None


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    date: datetime.date
    amount: Decimal
    payee_id: Optional[uuid.UUID] = None
    payee_name: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    memo: Optional[str] = None
    cleared: ClearedStatus = ClearedStatus.UNCLEARED
    approved: bool = True
    transfer_account_id: Optional[uuid.UUID] = None
    splits: Optional[list[SplitCreate]] = None


class TransactionUpdate(BaseModel):
    date: Optional[datetime.date] = None
    amount: Optional[Decimal] = None
    payee_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    memo: Optional[str] = None
    cleared: Optional[ClearedStatus] = None
    approved: Optional[bool] = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    date: datetime.date
    amount: Decimal
    payee_id: Optional[uuid.UUID]
    category_id: Optional[uuid.UUID]
    memo: Optional[str]
    cleared: str
    approved: bool
    transfer_id: Optional[uuid.UUID]
    parent_transaction_id: Optional[uuid.UUID]
    is_split: bool
    import_id: Optional[str]
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
    name: Optional[str] = None
    default_category_id: Optional[uuid.UUID] = None


class PayeeResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    default_category_id: Optional[uuid.UUID]
    transfer_account_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class PayeeWithCount(PayeeResponse):
    transaction_count: int


class PayeeMergeRequest(BaseModel):
    target_id: uuid.UUID
