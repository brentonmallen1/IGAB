import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AttachmentRotateRequest(BaseModel):
    degrees: Literal[90, 180, 270]


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    width: int | None
    height: int | None
    created_at: datetime
