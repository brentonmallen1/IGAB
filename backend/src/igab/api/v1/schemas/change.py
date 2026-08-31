import datetime
import uuid
from typing import Any

from igab.api.v1.schemas.base import ApiModel


class ChangeOut(ApiModel):
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
    #: Actor — None for system/AI changes (render the source instead).
    user_id: uuid.UUID | None = None
    user_display_name: str | None = None

    model_config = {"from_attributes": True}


class ChangeListResponse(ApiModel):
    changes: list[ChangeOut]
    total: int


class UndoResult(ApiModel):
    undone_change_ids: list[uuid.UUID]
