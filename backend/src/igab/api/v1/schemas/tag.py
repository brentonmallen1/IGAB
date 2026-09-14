import uuid
from typing import Literal

from igab.api.v1.schemas.base import ApiModel

TagColorSlot = Literal["red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"]


class TagCreate(ApiModel):
    name: str
    color_slot: TagColorSlot | None = None


class TagUpdate(ApiModel):
    name: str | None = None
    color_slot: TagColorSlot | None = None


class TagOut(ApiModel):
    id: uuid.UUID
    name: str
    system_key: str | None
    color_slot: str | None
    category_count: int = 0

    model_config = {"from_attributes": True}


class TagOutSimple(ApiModel):
    id: uuid.UUID
    name: str
    system_key: str | None
    color_slot: str | None

    model_config = {"from_attributes": True}


class SetTagsRequest(ApiModel):
    tag_ids: list[uuid.UUID]


class TagSuggestionOut(ApiModel):
    """A system tag this category's names point at, which it does not carry.

    Served rather than computed on the client because the rule is the
    server's (`domain.tag_hints`), and a second spelling in TypeScript would be
    free to disagree with it silently.
    """

    category_id: uuid.UUID
    system_key: str
    #: The category's own name or its group's — whichever triggered the hint.
    matched_on: str
    #: Whether an import writes this one. Always False now — nothing is
    #: written from a name — and kept so the review's shape does not move.
    applied_on_import: bool


class CategoryTagsUpdate(ApiModel):
    category_id: uuid.UUID
    #: The category's FULL intended tag set. `set_category_tags` is a replace,
    #: so a partial list silently drops the tags it omits.
    tag_ids: list[uuid.UUID]


class BulkSetCategoryTagsRequest(ApiModel):
    updates: list[CategoryTagsUpdate]
