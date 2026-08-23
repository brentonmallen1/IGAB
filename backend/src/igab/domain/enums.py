from enum import StrEnum
from typing import Literal

# Account types are no longer a static enum: each budget carries an
# account_types registry row per type (built-ins seeded from
# igab.domain.account_types, plus user-defined custom types).


class ClearedStatus(StrEnum):
    PENDING = "pending"
    UNCLEARED = "uncleared"
    CLEARED = "cleared"
    RECONCILED = "reconciled"


class UserClearedStatus(StrEnum):
    """Cleared values a user may set directly. `pending` belongs to bank sync;
    `reconciled` is granted only by the reconciliation flow (and removed only
    via the explicit unreconcile action)."""

    UNCLEARED = "uncleared"
    CLEARED = "cleared"


class TargetType(StrEnum):
    NEEDED_FOR_SPENDING = "needed_for_spending"
    SAVINGS_BALANCE = "savings_balance"
    MONTHLY_FUNDING = "monthly_funding"
    WEEKLY_FUNDING = "weekly_funding"


#: The three answers the budget row's pill can show. A Literal rather than a
#: StrEnum because it is a computed verdict that crosses the API to the client,
#: not a stored column — TargetService produces it and the response schema
#: declares it, and this is what stops the two drifting apart.
TargetStatus = Literal["funded", "underfunded", "overfunded"]


class ScheduleFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    TWICE_MONTHLY = "twice_monthly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ImportSource(StrEnum):
    SIMPLEFIN = "simplefin"
    CSV = "csv"
    YNAB = "ynab"
    MANUAL = "manual"


class OverspendingHandling(StrEnum):
    ALLOW = "allow"
    WARN = "warn"


class AccountClassification(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
