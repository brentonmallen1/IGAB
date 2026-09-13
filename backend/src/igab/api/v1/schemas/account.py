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
    # None = use the type's default_counts_as_savings
    counts_as_savings: bool | None = None
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
    #: Whether transfers with this off-budget asset count as saving. A type
    #: change leaves it alone, the same as `on_budget`.
    counts_as_savings: bool | None = None
    is_closed: bool | None = None
    note: str | None = None
    sort_order: int | None = None
    #: Reference numbers, sent in the clear over TLS and stored encrypted
    #: (services/secrets.py). Null clears; omitted leaves as is.
    account_number: str | None = Field(default=None, max_length=64)
    routing_number: str | None = Field(default=None, max_length=64)


class AccountResponse(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    account_type: str
    on_budget: bool
    #: Required: served from the column, and a path that forgot it must raise
    #: rather than report a car as savings.
    counts_as_savings: bool
    classification: str | None
    is_closed: bool
    sort_order: int
    note: str | None
    #: The masked display's clear part; the numbers themselves come only from
    #: GET /accounts/{id}/secrets.
    account_number_last4: str | None = None
    has_routing_number: bool = False
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
    #: Authorised by the bank, not yet posted. NOT a term in
    #: `balance = cleared + uncleared` — pending money is in no money
    #: aggregate until it posts (see txn_filters.PENDING_ROW), which is
    #: exactly why the register needs it stated: the rows are visible and
    #: count for nothing.
    pending_balance: Decimal = Decimal("0")
    uncategorized_count: int = 0

    model_config = {"from_attributes": True}


class AccountSecretsResponse(ApiModel):
    """The decrypted reference numbers, on demand and never in a list."""

    account_number: str | None
    routing_number: str | None
