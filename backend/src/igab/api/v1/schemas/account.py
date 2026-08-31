import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel

# The registry key of an account type — built-in or user-defined. Existence is
# validated per budget at the endpoint (account_type_service.resolve_type);
# the pattern only rejects shapes that could never be a key.
AccountTypeKey = Field(pattern=r"^[a-z0-9_]{1,30}$")


class AccountCreate(ApiModel):
    name: str
    account_type: str = AccountTypeKey
    # None = use the type's default_on_budget
    on_budget: bool | None = None
    note: str | None = None
    sort_order: int = 0


class AccountUpdate(ApiModel):
    name: str | None = None
    #: The day this account joined the budget — see `Account.budget_start_date`.
    #: Omitted leaves it alone; an explicit null clears it back to "treat all
    #: history as budgeted". Both are meaningful, which is why the endpoint
    #: keeps it in the null-allowed set beside `note`.
    budget_start_date: date | None = None
    account_type: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,30}$")
    on_budget: bool | None = None
    is_closed: bool | None = None
    note: str | None = None
    sort_order: int | None = None


class AccountResponse(ApiModel):
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
    #: Rows before this are opening position: not auto-categorized on first
    #: sync, and not flagged as needing a category. Null on every account that
    #: has never been asked, which behaves exactly as before the field existed.
    budget_start_date: date | None = None
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
