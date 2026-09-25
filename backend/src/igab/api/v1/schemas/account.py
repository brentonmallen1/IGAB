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
    #: Omitted or null starts false. True is refused unless the account is an
    #: off-budget asset that counts as savings (`EMERGENCY_FUND_ACCOUNT_SHAPE`).
    counts_toward_emergency_fund: bool | None = None
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
    #: True is refused unless the account, with this request's other fields
    #: applied, is an off-budget asset that counts as savings.
    counts_toward_emergency_fund: bool | None = None
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
    #: The stored choice. Required for the reason `counts_as_savings` is. Whether
    #: the balance is counted is `txn_filters.EMERGENCY_FUND_ACCOUNT`, which also
    #: requires the account to still have the shape the flag was set on.
    counts_toward_emergency_fund: bool
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
    #: When the bank computed `simplefin_balance`. Null on an account synced
    #: before the column existed, or whose bridge omitted `balance-date`.
    simplefin_balance_date: datetime | None = None
    # Computed
    balance: Decimal = Decimal("0")
    #: `simplefin_balance - cleared_balance`, signed, or null when the bank
    #: has reported nothing. Served rather than computed on the client because
    #: the sync decides on the same rule whether a run is degraded
    #: (domain.bank_balance).
    bank_drift: Decimal | None = None
    #: Why the two figures differ: "agree" | "unposted" | "stale" |
    #: "unexplained", or null when the bank has reported nothing. The whole
    #: point of the banner — only "unexplained" means rows may be missing,
    #: and the other two used to be reported as if they did.
    bank_drift_reason: str | None = None
    #: The part of `bank_drift` that `bank_unposted_cleared` does not account
    #: for. Signed, same frame as `bank_drift`.
    bank_drift_unexplained: Decimal | None = None
    #: Cleared money the bank has not posted against — the ledger running
    #: ahead of the feed, which is the ordinary result of ticking a hold the
    #: bank's own site already shows as posted.
    bank_unposted_cleared: Decimal | None = None
    #: Whether the sync would call this gap a fault. Served rather than
    #: re-derived from `bank_drift_reason` and `last_reconciled_at` on the
    #: client, because the sync decides it (domain.bank_balance) and a page
    #: that reached its own verdict would be free to disagree with the badge.
    bank_drift_is_fault: bool = False
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
