import uuid
from datetime import datetime

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel
from igab.domain.enums import AccountClassification


class AccountTypeCreate(ApiModel):
    label: str = Field(min_length=1, max_length=50)
    classification: AccountClassification
    default_on_budget: bool = False
    description: str | None = None


class AccountTypeUpdate(ApiModel):
    label: str | None = Field(default=None, min_length=1, max_length=50)
    classification: AccountClassification | None = None
    default_on_budget: bool | None = None
    description: str | None = None
    sort_order: int | None = None


class AccountTypeResponse(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    key: str
    label: str
    classification: str
    default_on_budget: bool
    description: str | None
    is_system: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
