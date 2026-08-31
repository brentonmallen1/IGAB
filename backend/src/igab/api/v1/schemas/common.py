import uuid
from datetime import datetime

from igab.api.v1.schemas.base import ApiModel


class TimestampMixin(ApiModel):
    created_at: datetime
    updated_at: datetime


class UUIDModel(ApiModel):
    id: uuid.UUID

    model_config = {"from_attributes": True}
