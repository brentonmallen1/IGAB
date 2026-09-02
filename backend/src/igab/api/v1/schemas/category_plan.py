"""Category planner schemas: the plan document, its CRUD, and apply-targets.

The payload is stored verbatim as JSONB and validated here on every write.
Amounts are **integer cents** — JSONB cannot carry Decimal, ints round-trip
exactly, and the client does its arithmetic in cents already.

Storage is draft-permissive on purpose: the planner autosaves on every
keystroke, so an empty row name, a missing amount, or a dangling
``category_id`` must be storable. Strictness lives in the apply-targets
classification, which reports such rows instead of failing on them.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from igab.api.v1.schemas.base import ApiModel

#: $100 billion in cents — a bound against nonsense, not a business rule.
MAX_CENTS = 10**13

Cadence = Literal["weekly", "biweekly", "semimonthly", "monthly"]


class PlanItem(ApiModel):
    id: uuid.UUID
    #: A live budget category this row is linked to; None for a free-form row.
    #: Checked for shape only — apply-time classification owns validity.
    category_id: uuid.UUID | None = None
    #: Display name. For linked rows a snapshot of the category's name (the
    #: fallback if the category is later deleted); may be "" for a draft row.
    name: str = Field(max_length=200)
    due_day: int | None = Field(default=None, ge=1, le=31)
    #: None means "not entered yet" — never coerced to zero.
    amount_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)


class PlanPaycheck(ApiModel):
    id: uuid.UUID
    #: None means "use the even split of the monthly take-home".
    income_override_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    items: list[PlanItem] = Field(default_factory=list, max_length=100)


class PlanPayload(ApiModel):
    schema_version: Literal[1] = 1
    monthly_income_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    cadence: Cadence = "biweekly"
    #: Overrides the count the cadence implies (a 3-paycheck month). The
    #: `paychecks` array is the truth; this is remembered for the header UI.
    paycheck_count_override: int | None = Field(default=None, ge=1, le=10)
    paychecks: list[PlanPaycheck] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_ids(self) -> "PlanPayload":
        paycheck_ids = [p.id for p in self.paychecks]
        if len(set(paycheck_ids)) != len(paycheck_ids):
            raise ValueError("paycheck ids must be unique within a plan")
        item_ids = [i.id for p in self.paychecks for i in p.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("item ids must be unique within a plan")
        return self


class PlanCreate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    payload: PlanPayload | None = None


class PlanPut(ApiModel):
    payload: PlanPayload


class PlanRename(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class PlanDuplicate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class PlanSummaryOut(ApiModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlanOut(PlanSummaryOut):
    payload: PlanPayload


# ── apply targets ─────────────────────────────────────────────────────────────

ApplyKind = Literal[
    "set_target",  # linked or name-matched category with no target yet
    "update_target",  # …with a monthly_funding target already
    "create_category",  # free-form row: new category in the "Planned" group
    "skip_existing_type",  # target of another type is kept, flagged with it
    "skip_invalid_link",  # category_id foreign, deleted, or not assignable
    "skip_draft",  # no amount, or free-form with no name
]


class ApplyEntryOut(ApiModel):
    kind: ApplyKind
    #: Category name (resolved) or the row's own name for creates/drafts.
    name: str
    category_id: uuid.UUID | None
    #: The monthly-funding amount that would be (or was) set; None on skips.
    amount: Decimal | None
    #: For skip_existing_type: the target type being kept.
    existing_target_type: str | None
    #: The plan rows feeding this entry (rows naming one category are summed).
    item_ids: list[uuid.UUID]


class ApplyPreviewOut(ApiModel):
    entries: list[ApplyEntryOut]
    targets_set: int
    targets_updated: int
    categories_created: int
    skipped_existing_type: int
    skipped_invalid_link: int
    skipped_draft: int


class ApplyResultOut(ApplyPreviewOut):
    #: The plan after apply — created/adopted categories are linked back into
    #: it, which is what makes a second apply update instead of duplicate.
    plan: PlanOut
