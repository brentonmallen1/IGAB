import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from igab.domain.enums import AccountType


class AccountCreate(BaseModel):
    name: str
    account_type: AccountType
    on_budget: bool = True
    note: str | None = None
    sort_order: int = 0


class AccountUpdate(BaseModel):
    name: str | None = None
    on_budget: bool | None = None
    is_closed: bool | None = None
    note: str | None = None
    sort_order: int | None = None


class AccountResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    account_type: str
    on_budget: bool
    is_closed: bool
    sort_order: int
    note: str | None
    last_reconciled_at: datetime | None
    last_reconciled_balance: Decimal | None
    created_at: datetime
    updated_at: datetime
    # Computed
    balance: Decimal = Decimal("0")
    cleared_balance: Decimal = Decimal("0")
    uncleared_balance: Decimal = Decimal("0")
    uncategorized_count: int = 0

    model_config = {"from_attributes": True}
