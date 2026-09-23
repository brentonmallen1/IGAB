import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from igab.api.v1.schemas.base import ApiModel, ClientDated
from igab.guide.wishlist import MAX_COOLING_DAYS, MAX_REVIEW_DAYS, MIN_REVIEW_DAYS

Money = Decimal


class FundingIn(ApiModel):
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


class WishCreate(ClientDated):
    """`client_today` is the day the wish is added: what `cooling_days`
    counts from, now and on every later edit that sets the period in days."""

    name: str = Field(min_length=1, max_length=200)
    cost: Money = Field(default=Decimal("0"), ge=0)
    url: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0)
    cooling_days: int | None = Field(default=None, ge=0, le=MAX_COOLING_DAYS)
    funding: FundingIn = Field(default_factory=FundingIn)


class WishUpdate(ClientDated):
    """`client_today` is the person's own date, and a status change stamps it.

    Without it `done_at`/`dropped_at` came from the server's clock, and the
    discipline report buckets "cooled off, then dropped" by comparing that
    date with `cooling_until` — so a drop on the last cooling evening west of
    UTC was filed as a wish that never cooled at all.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    cost: Money | None = Field(default=None, ge=0)
    url: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0)
    #: Pin as a top priority. Capped server-side (PRIORITY_LIMIT); a full
    #: spotlight refuses the pin rather than silently displacing one.
    is_priority: bool | None = None
    status: Literal["open", "done", "dropped"] | None = None
    cooling_until: date | None = None
    #: The cooling-off as a length: this many days after the wish was ADDED,
    #: not after today — so "14" means the same date whenever the edit is
    #: made, and one that is already behind us simply ends the cooling-off.
    #: The other spelling of `cooling_until`; sending both is refused.
    cooling_days: int | None = Field(default=None, ge=0, le=MAX_COOLING_DAYS)
    #: Any of the three modes. `own` on a wish that has no envelope of its
    #: own makes one (named for the wish, with a savings goal of its cost);
    #: on one that already has an envelope it is a no-op, because the budget
    #: page owns that category from the moment it exists.
    funding: FundingIn | None = None

    @model_validator(mode="after")
    def one_cooling_spelling(self) -> "WishUpdate":
        # Presence, not value: `cooling_until: null` (end it) beside a day
        # count is as contradictory as two dates.
        if {"cooling_days", "cooling_until"} <= self.model_fields_set:
            raise ValueError("Set the cooling-off as a date or as days, not both")
        return self


class FundingOut(ApiModel):
    mode: Literal["own", "existing", "none"]
    category_id: uuid.UUID | None
    category_name: str | None
    inherited: bool
    owns_envelope: bool
    target_date: date | None


class ReachOut(ApiModel):
    state: Literal["now", "months", "no_rate", "unlinked"]
    months: int | None
    date: date | None
    ahead_cost: Decimal
    progress: Decimal


class SettlementOut(ApiModel):
    """An ended wish whose own envelope is still standing.

    Served, not derived on the client: `available` is the budget page's
    figure, and whether a goal is still attached is the server's to know.
    Null on `WishOut` once the envelope has been settled or archived, so the
    prompt clears itself rather than needing a flag that could disagree.
    """

    category_id: uuid.UUID
    name: str
    available: Decimal
    has_goal: bool


class WishOut(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    url: str | None
    notes: str | None
    cost: Decimal
    priority: int
    #: Required, not optional: a path that forgets to serialize it must raise,
    #: not quietly report an unpinned wish.
    is_priority: bool
    status: Literal["open", "done", "dropped"]
    funding: FundingOut
    cooling_until: date | None
    cooling: bool
    #: The day the wish was added, as its cooling-off in days counts it —
    #: served because the client cannot recover the person's date from
    #: `created_at`, an instant.
    added_on: date
    last_affirmed_at: datetime | None
    review_due: bool
    done_at: date | None
    dropped_at: date | None
    created_at: datetime
    reach: ReachOut | None
    #: Required, not optional: a path that forgets it would report an
    #: envelope left holding money as settled, which is the bug this field
    #: exists to end.
    settlement: SettlementOut | None


class ProjectSummaryOut(ApiModel):
    item_count: int
    open_count: int
    total_cost: Decimal
    affordable_now: int
    funded_by: date | None
    state: Literal["now", "months", "no_rate", "unlinked", "mixed", "complete", "empty"]
    complete: bool


class ProjectOut(ApiModel):
    id: uuid.UUID
    name: str
    category_id: uuid.UUID | None
    category_name: str | None
    notes: str | None
    sort_order: int
    summary: ProjectSummaryOut


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class WishReorder(ApiModel):
    item_ids: list[uuid.UUID]


class ProjectReorder(ApiModel):
    project_ids: list[uuid.UUID]


class WishlistSettingsOut(ApiModel):
    cooling_days: int
    review_after_days: int


class WishlistSettingsUpdate(ApiModel):
    cooling_days: int | None = Field(default=None, ge=0, le=MAX_COOLING_DAYS)
    review_after_days: int | None = Field(default=None, ge=MIN_REVIEW_DAYS, le=MAX_REVIEW_DAYS)


class SettleRequest(ClientDated):
    """Where an ended wish's envelope money goes, and what becomes of the
    envelope. `destination_category_id` null means Ready to Assign — where
    the category-delete flow and the wishlist off-switch both send it."""

    destination_category_id: uuid.UUID | None = None
    #: Keep the (now empty, goal-less) envelope on the budget page instead of
    #: archiving it — for someone who wants to re-purpose it.
    keep_envelope: bool = False


class EnvelopeOut(ApiModel):
    category_id: uuid.UUID
    name: str
    available: Decimal


class DeleteWishResponse(ApiModel):
    """The envelope the wish owned, if any, so the client can offer to
    delete it too through the ordinary category-delete flow."""

    envelope: EnvelopeOut | None


class DrainMoveOut(ApiModel):
    move_id: uuid.UUID
    month: date
    date: datetime
    amount: Decimal
    from_category_id: uuid.UUID
    from_name: str
    to_category_id: uuid.UUID | None
    to_name: str
    affected: list["DrainAffectedOut"]


class DrainAffectedOut(ApiModel):
    item_id: uuid.UUID
    name: str
    months_further: Decimal | None


class DrainsOut(ApiModel):
    month: date
    total: Decimal
    moves: list[DrainMoveOut]


class StillWantedOut(ApiModel):
    count: int
    of: int
    #: The window, in months — served so the client's copy has one source.
    months: int


class WishlistResponse(ApiModel):
    enabled: bool
    items: list[WishOut]
    history: list[WishOut]
    projects: list[ProjectOut]
    still_wanted: StillWantedOut
    review_due_count: int
    settings: WishlistSettingsOut
    #: The pin cap, served so the client disables the action at the limit
    #: without spelling its own 3.
    priority_limit: int
    #: The longest cooling-off, in days — served for the same reason.
    max_cooling_days: int
    #: The review cadence's bounds, served for the same reason again: the
    #: settings form refuses what the server would refuse, in its own words.
    min_review_days: int
    max_review_days: int
    drains: DrainsOut | None
