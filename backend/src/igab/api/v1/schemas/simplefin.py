import uuid
from datetime import datetime

from pydantic import BaseModel


class SimpleFINSetupRequest(BaseModel):
    setup_token: str


class SimpleFINUpdateRequest(BaseModel):
    sync_interval_hours: int


class SimpleFINConnectionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    last_sync_at: datetime | None
    sync_interval_hours: int
    requests_today: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LinkSimpleFINRequest(BaseModel):
    simplefin_account_id: str


class SyncResult(BaseModel):
    imported: int
    skipped: int
    error: str | None = None
