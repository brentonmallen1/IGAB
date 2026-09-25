import uuid
from typing import Literal

from igab.api.v1.schemas.base import ApiModel
from igab.repositories.category_filters import SavingsMode, SavingsRole

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
    #: The rows its checklist draws ticked — carrying it, or a tag that implies
    #: it (`category_filters.ticked_on_checklist`) — so the number a person
    #: clicks is the number of ticks they then see.
    category_count: int = 0
    #: False for a tag the app sets itself (`tag_hints.DERIVED_KEYS` — the
    #: wishlist's), which the membership endpoints refuse. The Tags panel offers
    #: its checklist only where this is true.
    hand_settable: bool


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


class MembershipTagOut(ApiModel):
    id: uuid.UUID
    name: str
    system_key: str | None
    #: Carrying it makes a category a savings category
    #: (`category_filters.SAVINGS_CATEGORY_KEYS`), so each checked row says how
    #: its money counts as saved.
    savings_tag: bool


class MembershipCategoryOut(ApiModel):
    """One row of a tag's checklist — every taggable category, member or not."""

    id: uuid.UUID
    name: str
    group_id: uuid.UUID
    group_name: str
    is_archived: bool
    #: Carries this tag itself — the half a person can untick.
    member: bool
    #: The name of a tag on this category that implies this one
    #: (`domain.tag_implication`): "Essential" on the Cost of living checklist,
    #: "Emergency fund" on the Savings one. The row counts as tagged whatever
    #: `member` says, so the checklist draws it ticked and locked, and a save
    #: naming it is refused. Required: a path that forgets it must fail, not
    #: draw an implied row as an unticked one.
    implied_by: str | None
    #: `category_filters.SAVINGS_ROLE` as it stands — 'none' for a category
    #: that is not a savings category.
    savings_role: SavingsRole
    #: The stored choice; None lets the tags decide (the role is the default).
    savings_mode: SavingsMode | None


class TagMembershipOut(ApiModel):
    tag: MembershipTagOut
    categories: list[MembershipCategoryOut]


class TagMembershipUpdate(ApiModel):
    """A diff against the checklist as loaded, not the full member set: two
    screens editing different rows of one tag do not undo each other."""

    add: list[uuid.UUID] = []
    remove: list[uuid.UUID] = []
    #: Category id → how its money counts as saved; null = back to the default.
    savings_modes: dict[uuid.UUID, SavingsMode | None] = {}
