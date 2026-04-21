import datetime
import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from igab.domain.enums import TargetType


class CategoryGroupCreate(BaseModel):
    name: str
    sort_order: int = 0


class CategoryGroupUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_hidden: Optional[bool] = None


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
    note: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    note: Optional[str] = None
    is_hidden: Optional[bool] = None
    category_group_id: Optional[uuid.UUID] = None


class CategoryTargetCreate(BaseModel):
    target_type: TargetType
    target_amount: Decimal
    target_date: Optional[datetime.date] = None
    repeat_frequency: Optional[str] = None


class CategoryTargetResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    target_type: str
    target_amount: Decimal
    target_date: Optional[datetime.date]
    repeat_frequency: Optional[str]

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
    note: Optional[str]
    is_hidden: bool
    linked_account_id: Optional[uuid.UUID]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class BudgetMonthResponse(BaseModel):
    month: datetime.date
    to_be_assigned: Decimal
    total_assigned: Decimal
    total_activity: Decimal
    category_balances: list[CategoryBalance]


class AssignmentUpdate(BaseModel):
    amount: Decimal


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


class FillTargetsPreviewItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    current_assigned: Decimal
    proposed_addition: Decimal
    new_assigned: Decimal


class FillTargetsPreviewResponse(BaseModel):
    items: list[FillTargetsPreviewItem]
    total_addition: Decimal
    tba_before: Decimal
    tba_after: Decimal


class FillTargetsApplyRequest(BaseModel):
    month: datetime.date
    items: list[FillTargetsPreviewItem]
