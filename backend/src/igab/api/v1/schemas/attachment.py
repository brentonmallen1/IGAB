import uuid
from datetime import datetime
from typing import Literal

from igab.api.v1.schemas.base import ApiModel


class AttachmentRotateRequest(ApiModel):
    degrees: Literal[90, 180, 270]


class AttachmentResponse(ApiModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    width: int | None
    height: int | None
    created_at: datetime
