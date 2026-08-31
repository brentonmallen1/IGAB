import uuid
from datetime import date, datetime
from decimal import Decimal

from igab.api.v1.schemas.base import ApiModel


class ScheduledTransactionCreate(ApiModel):
    account_id: uuid.UUID
    amount: Decimal
    frequency: str
    start_date: date
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    end_date: date | None = None
    auto_create: bool = False
    days_before_reminder: int = 3


class ScheduledTransactionUpdate(ApiModel):
    amount: Decimal | None = None
    frequency: str | None = None
    start_date: date | None = None
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    end_date: date | None = None
    auto_create: bool | None = None
    days_before_reminder: int | None = None
    next_occurrence_date: date | None = None


class ScheduledTransactionResponse(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    payee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    memo: str | None
    frequency: str
    start_date: date
    end_date: date | None
    auto_create: bool
    days_before_reminder: int
    next_occurrence_date: date
    last_created_date: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
