import uuid
from typing import Literal

from pydantic import BaseModel

TagColorSlot = Literal["red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"]


class TagCreate(BaseModel):
    name: str
    color_slot: TagColorSlot | None = None


class TagUpdate(BaseModel):
    name: str | None = None
    color_slot: TagColorSlot | None = None


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    system_key: str | None
    color_slot: str | None
    category_count: int = 0
    payee_count: int = 0

    model_config = {"from_attributes": True}


class TagOutSimple(BaseModel):
    id: uuid.UUID
    name: str
    system_key: str | None
    color_slot: str | None

    model_config = {"from_attributes": True}


class SetTagsRequest(BaseModel):
    tag_ids: list[uuid.UUID]
