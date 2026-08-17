import datetime
import uuid
from typing import Any

from pydantic import BaseModel


class ChangeOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    batch_id: uuid.UUID | None
    source: str
    undone_at: datetime.datetime | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class ChangeListResponse(BaseModel):
    changes: list[ChangeOut]
    total: int


class UndoResult(BaseModel):
    undone_change_ids: list[uuid.UUID]
