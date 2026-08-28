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


class TagSuggestionOut(BaseModel):
    """A system tag this category's names point at, which it does not carry.

    Served rather than computed on the client because the server already
    decides it — the YNAB importer writes tags from the same table. A second
    spelling in TypeScript would be free to disagree with the one that runs at
    import time, and the two would drift silently.
    """

    category_id: uuid.UUID
    system_key: str
    #: The category's own name or its group's — whichever triggered the hint.
    matched_on: str
    #: True when the importer would have written this one. False means it is
    #: offered here and nowhere else.
    applied_on_import: bool


class CategoryTagsUpdate(BaseModel):
    category_id: uuid.UUID
    #: The category's FULL intended tag set. `set_category_tags` is a replace,
    #: so a partial list silently drops the tags it omits.
    tag_ids: list[uuid.UUID]


class BulkSetCategoryTagsRequest(BaseModel):
    updates: list[CategoryTagsUpdate]
