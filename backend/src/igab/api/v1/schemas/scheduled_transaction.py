import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel
from igab.domain.enums import ScheduleFrequency


class ScheduledTransactionCreate(ApiModel):
    account_id: uuid.UUID
    amount: Decimal
    #: The enum, not `str`: the column stayed a string for years and a typo
    #: here became a schedule the arithmetic silently never advanced.
    frequency: ScheduleFrequency
    start_date: date
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    end_date: date | None = None
    auto_create: bool = False
    days_before_reminder: int = Field(default=3, ge=0)
    #: Twice-monthly only: the other day of the month (the first is the
    #: start date's day). Validated together in domain/schedule.py.
    second_day_of_month: int | None = Field(default=None, ge=1, le=31)
    #: A scheduled transfer: entering it materializes both legs.
    transfer_account_id: uuid.UUID | None = None


class ScheduledTransactionUpdate(ApiModel):
    """Omitted fields stay untouched; an explicit null clears the nullable
    ones (the route reads `model_fields_set`). `exclude_none` used to make
    an end date, a category or a memo impossible to remove."""

    account_id: uuid.UUID | None = None
    amount: Decimal | None = None
    frequency: ScheduleFrequency | None = None
    start_date: date | None = None
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    end_date: date | None = None
    auto_create: bool | None = None
    days_before_reminder: int | None = Field(default=None, ge=0)
    next_occurrence_date: date | None = None
    second_day_of_month: int | None = Field(default=None, ge=1, le=31)
    transfer_account_id: uuid.UUID | None = None


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
    second_day_of_month: int | None
    transfer_account_id: uuid.UUID | None
    #: Non-null on a schedule an import created (a future-dated YNAB row).
    import_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
