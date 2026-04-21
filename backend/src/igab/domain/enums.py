from enum import StrEnum


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    TRACKING = "tracking"


class ClearedStatus(StrEnum):
    PENDING = "pending"
    UNCLEARED = "uncleared"
    CLEARED = "cleared"
    RECONCILED = "reconciled"


class TargetType(StrEnum):
    NEEDED_FOR_SPENDING = "needed_for_spending"
    SAVINGS_BALANCE = "savings_balance"
    MONTHLY_FUNDING = "monthly_funding"
    WEEKLY_FUNDING = "weekly_funding"


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
