import uuid
from datetime import datetime

from pydantic import BaseModel


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime


class UUIDModel(BaseModel):
    id: uuid.UUID

    model_config = {"from_attributes": True}
