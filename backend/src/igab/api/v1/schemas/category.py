import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel

from igab.api.v1.schemas.tag import TagOutSimple
from igab.domain.enums import TargetType
from igab.domain.money import Money


class CategoryGroupCreate(BaseModel):
    name: str
    sort_order: int = 0


class CategoryGroupUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    is_hidden: bool | None = None


class CategoryGroupResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    sort_order: int
    is_hidden: bool
    is_system: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    category_group_id: uuid.UUID
    name: str
    sort_order: int = 0
    note: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    note: str | None = None
    is_hidden: bool | None = None
    category_group_id: uuid.UUID | None = None


class CategoryTargetCreate(BaseModel):
    target_type: TargetType
    target_amount: Money
    target_date: datetime.date | None = None
    repeat_frequency: str | None = None


class CategoryTargetResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    target_type: str
    target_amount: Decimal
    target_date: datetime.date | None
    repeat_frequency: str | None

    model_config = {"from_attributes": True}


class CategoryBalance(BaseModel):
    category_id: uuid.UUID
    month: datetime.date
    assigned: Decimal
    activity: Decimal
    available: Decimal


class CategoryResponse(BaseModel):
    id: uuid.UUID
    category_group_id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    sort_order: int
    note: str | None
    is_hidden: bool
    linked_account_id: uuid.UUID | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    tags: list[TagOutSimple] = []

    model_config = {"from_attributes": True}


class BudgetMonthResponse(BaseModel):
    month: datetime.date
    to_be_assigned: Decimal
    total_assigned: Decimal
    total_activity: Decimal
    total_overspent: Decimal
    category_balances: list[CategoryBalance]


class AssignmentUpdate(BaseModel):
    amount: Money


class MoveMoneyRequest(BaseModel):
    """Move money between envelopes; a null side means To-Be-Assigned."""

    from_category_id: uuid.UUID | None = None
    to_category_id: uuid.UUID | None = None
    amount: Money
    month: datetime.date


class BudgetMoveResponse(BaseModel):
    id: uuid.UUID
    month: datetime.date
    from_category_id: uuid.UUID | None
    to_category_id: uuid.UUID | None
    amount: Decimal
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class CategoryHistoryResponse(BaseModel):
    category_id: uuid.UUID
    last_month_assigned: Decimal
    last_month_spent: Decimal
    average_assigned: Decimal
    average_spent: Decimal
    months_included: int


class CategoryHistoryBatchRequest(BaseModel):
    category_ids: list[uuid.UUID]


class AutoAssignRequest(BaseModel):
    category_ids: list[uuid.UUID]
    action: str
    month: datetime.date


class CoverOverspentPreviewItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    overspent: Decimal
    proposed_addition: Decimal
    remaining_after: Decimal


class CoverOverspentPreviewResponse(BaseModel):
    items: list[CoverOverspentPreviewItem]
    total_overspent: Decimal
    total_addition: Decimal
    tba_before: Decimal
    tba_after: Decimal


class CoverOverspentApplyItem(BaseModel):
    category_id: uuid.UUID
    proposed_addition: Money


class CoverOverspentApplyRequest(BaseModel):
    month: datetime.date
    items: list[CoverOverspentApplyItem]


class AssignStrategyTotal(BaseModel):
    strategy: str
    total_amount: Decimal
    total_needed: Decimal | None = None
    to_assign: Decimal
    to_return: Decimal
    affected_count: int


class AssignStrategyTotalsResponse(BaseModel):
    month: datetime.date
    tba: Decimal
    total_overspent: Decimal
    strategies: list[AssignStrategyTotal]


class AssignPreviewItemOut(BaseModel):
    category_id: uuid.UUID
    category_name: str
    current_assigned: Decimal
    delta: Decimal
    new_assigned: Decimal


class AssignPreviewResponse(BaseModel):
    strategy: str
    items: list[AssignPreviewItemOut]
    total_needed: Decimal | None = None
    to_assign: Decimal
    to_return: Decimal
    tba_before: Decimal
    tba_after: Decimal


class AssignApplyRequest(BaseModel):
    month: datetime.date
    strategy: str


class AssignApplyResponse(BaseModel):
    to_assign: Decimal
    to_return: Decimal
    categories_changed: int
    tba_after: Decimal
