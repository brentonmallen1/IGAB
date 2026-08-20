import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# The registry key of an account type — built-in or user-defined. Existence is
# validated per budget at the endpoint (account_type_service.resolve_type);
# the pattern only rejects shapes that could never be a key.
AccountTypeKey = Field(pattern=r"^[a-z0-9_]{1,30}$")


class AccountCreate(BaseModel):
    name: str
    account_type: str = AccountTypeKey
    # None = use the type's default_on_budget
    on_budget: bool | None = None
    note: str | None = None
    sort_order: int = 0


class AccountUpdate(BaseModel):
    name: str | None = None
    account_type: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,30}$")
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
    classification: str | None
    is_closed: bool
    sort_order: int
    note: str | None
    last_reconciled_at: datetime | None
    last_reconciled_balance: Decimal | None
    created_at: datetime
    updated_at: datetime
    # SimpleFIN sync
    simplefin_account_id: str | None = None
    simplefin_account_name: str | None = None
    simplefin_sync_enabled: bool = True
    first_sync_complete: bool = False
    last_simplefin_sync_at: datetime | None = None
    simplefin_balance: Decimal | None = None
    # Computed
    balance: Decimal = Decimal("0")
    cleared_balance: Decimal = Decimal("0")
    uncleared_balance: Decimal = Decimal("0")
    uncategorized_count: int = 0

    model_config = {"from_attributes": True}
