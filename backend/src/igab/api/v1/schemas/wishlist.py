import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Money = Decimal


class FundingIn(BaseModel):
    """Where a wish's money lives.

    `own` makes a category of its own in the Wishlist group with a savings
    goal equal to the cost (and an optional date); `existing` points at any
    category; `none` leaves it for later.
    """

    mode: Literal["own", "existing", "none"] = "none"
    category_id: uuid.UUID | None = None
    want_by: date | None = None

    @model_validator(mode="after")
    def shape(self) -> "FundingIn":
        if self.mode == "existing" and self.category_id is None:
            raise ValueError("existing funding needs a category_id")
        return self


class WishCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cost: Money = Field(default=Decimal("0"), ge=0)
    url: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0)
    cooling_days: int | None = Field(default=None, ge=0, le=365)
    funding: FundingIn = Field(default_factory=FundingIn)


class WishUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cost: Money | None = Field(default=None, ge=0)
    url: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0)
    status: Literal["open", "done", "dropped"] | None = None
    cooling_until: date | None = None
    #: `existing` or `none` — an envelope of its own is chosen at creation.
    funding: FundingIn | None = None


class FundingOut(BaseModel):
    mode: Literal["own", "existing", "none"]
    category_id: uuid.UUID | None
    category_name: str | None
    inherited: bool
    owns_envelope: bool
    target_date: date | None


class ReachOut(BaseModel):
    state: Literal["now", "months", "no_rate", "unlinked"]
    months: int | None
    date: date | None
    ahead_cost: Decimal
    progress: Decimal


class WishOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    url: str | None
    notes: str | None
    cost: Decimal
    priority: int
    status: Literal["open", "done", "dropped"]
    funding: FundingOut
    cooling_until: date | None
    cooling: bool
    last_affirmed_at: datetime | None
    review_due: bool
    done_at: date | None
    created_at: datetime
    reach: ReachOut | None


class ProjectSummaryOut(BaseModel):
    item_count: int
    open_count: int
    total_cost: Decimal
    affordable_now: int
    funded_by: date | None
    state: Literal["now", "months", "no_rate", "unlinked", "mixed", "complete", "empty"]
    complete: bool


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    category_id: uuid.UUID | None
    category_name: str | None
    notes: str | None
    sort_order: int
    summary: ProjectSummaryOut


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class WishReorder(BaseModel):
    item_ids: list[uuid.UUID]


class ProjectReorder(BaseModel):
    project_ids: list[uuid.UUID]


class WishlistSettingsOut(BaseModel):
    cooling_days: int
    review_after_days: int


class WishlistSettingsUpdate(BaseModel):
    cooling_days: int | None = Field(default=None, ge=0, le=365)
    review_after_days: int | None = Field(default=None, ge=7, le=365)


class EnvelopeOut(BaseModel):
    category_id: uuid.UUID
    name: str
    available: Decimal


class DeleteWishResponse(BaseModel):
    """The envelope the wish owned, if any, so the client can offer to
    delete it too through the ordinary category-delete flow."""

    envelope: EnvelopeOut | None


class DrainMoveOut(BaseModel):
    move_id: uuid.UUID
    month: date
    date: datetime
    amount: Decimal
    from_category_id: uuid.UUID
    from_name: str
    to_category_id: uuid.UUID | None
    to_name: str
    affected: list["DrainAffectedOut"]


class DrainAffectedOut(BaseModel):
    item_id: uuid.UUID
    name: str
    months_further: Decimal | None


class DrainsOut(BaseModel):
    month: date
    total: Decimal
    moves: list[DrainMoveOut]


class StillWantedOut(BaseModel):
    count: int
    of: int
    #: The window, in months — served so the client's copy has one source.
    months: int


class WishlistResponse(BaseModel):
    enabled: bool
    items: list[WishOut]
    history: list[WishOut]
    projects: list[ProjectOut]
    still_wanted: StillWantedOut
    review_due_count: int
    settings: WishlistSettingsOut
    drains: DrainsOut | None
