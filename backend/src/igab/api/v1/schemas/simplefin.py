import uuid
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel


class SimpleFINSetupRequest(BaseModel):
    setup_token: str


class SimpleFINUpdateRequest(BaseModel):
    sync_interval_hours: int | None = None
    sync_enabled: bool | None = None
    daily_sync_time: time | None = None


class SimpleFINConnectionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    last_sync_at: datetime | None
    sync_interval_hours: int
    sync_enabled: bool
    daily_sync_time: time | None
    global_requests_today: int
    account_requests_today: int
    last_sync_error: str | None
    last_sync_error_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LinkSimpleFINRequest(BaseModel):
    simplefin_account_id: str
    simplefin_account_name: str | None = None


class SyncResult(BaseModel):
    imported: int
    skipped: int
    cleared: int = 0
    removed_pending: int = 0
    error: str | None = None
    global_used: int | None = None
    global_remaining: int | None = None
    account_used: int | None = None
    account_remaining: int | None = None


class RateLimitStatus(BaseModel):
    global_used: int
    global_remaining: int
    account_used: int
    account_remaining: int
    can_sync_global: bool
    can_sync_account: bool
    resets_at: str


class AccountSyncStatusResponse(BaseModel):
    account_id: uuid.UUID
    simplefin_account_id: str | None
    simplefin_sync_enabled: bool
    first_sync_complete: bool
    last_simplefin_sync_at: datetime | None
    simplefin_balance: Decimal | None

    model_config = {"from_attributes": True}


class TransactionMatchResponse(BaseModel):
    id: uuid.UUID
    synced_transaction_id: uuid.UUID
    manual_transaction_id: uuid.UUID
    confidence_score: Decimal
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
