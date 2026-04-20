import enum


class AccountType(str, enum.Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    TRACKING = "tracking"


class ClearedStatus(str, enum.Enum):
    PENDING = "pending"
    UNCLEARED = "uncleared"
    CLEARED = "cleared"
    RECONCILED = "reconciled"


class TargetType(str, enum.Enum):
    NEEDED_FOR_SPENDING = "needed_for_spending"
    SAVINGS_BALANCE = "savings_balance"
    MONTHLY_FUNDING = "monthly_funding"
    WEEKLY_FUNDING = "weekly_funding"


class ScheduleFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    TWICE_MONTHLY = "twice_monthly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ImportSource(str, enum.Enum):
    SIMPLEFIN = "simplefin"
    CSV = "csv"
    YNAB = "ynab"
    MANUAL = "manual"


class OverspendingHandling(str, enum.Enum):
    ALLOW = "allow"
    WARN = "warn"
