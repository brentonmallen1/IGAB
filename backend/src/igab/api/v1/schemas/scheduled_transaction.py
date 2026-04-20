import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ScheduledTransactionCreate(BaseModel):
    account_id: uuid.UUID
    amount: Decimal
    frequency: str
    start_date: date
    payee_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    memo: Optional[str] = None
    end_date: Optional[date] = None
    auto_create: bool = False
    days_before_reminder: int = 3


class ScheduledTransactionUpdate(BaseModel):
    amount: Optional[Decimal] = None
    frequency: Optional[str] = None
    start_date: Optional[date] = None
    payee_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    memo: Optional[str] = None
    end_date: Optional[date] = None
    auto_create: Optional[bool] = None
    days_before_reminder: Optional[int] = None
    next_occurrence_date: Optional[date] = None


class ScheduledTransactionResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    payee_id: Optional[uuid.UUID]
    category_id: Optional[uuid.UUID]
    memo: Optional[str]
    frequency: str
    start_date: date
    end_date: Optional[date]
    auto_create: bool
    days_before_reminder: int
    next_occurrence_date: date
    last_created_date: Optional[date]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
