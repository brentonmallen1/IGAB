from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class YNABSplitLeg:
    category_group: str | None
    category: str | None
    memo: str | None
    amount: Decimal  # negative = outflow, positive = inflow


@dataclass
class YNABTransaction:
    account_name: str
    date: date
    payee: str
    category_group: str | None
    category: str | None
    memo: str | None
    amount: Decimal  # negative = outflow, positive = inflow
    cleared: str
    # Non-empty when this transaction was reassembled from a YNAB split:
    # amount is the sum of the legs and category_group/category are None.
    splits: list[YNABSplitLeg] = field(default_factory=list)


@dataclass
class YNABBudgetEntry:
    month: date
    category_group: str
    category: str
    assigned: Decimal


@dataclass
class YNABPlanRow:
    """One Plan.csv row exactly as exported — every category, every month, in
    YNAB's own display order (not alphabetical). `budget_entries` is the
    non-zero-assigned subset the importer writes; this is what the layout
    seed reads, and `activity`/`available` are YNAB's own answers, kept for
    checking ours against — never imported as state."""

    month: date
    category_group: str
    category: str
    assigned: Decimal
    #: None when the column is blank or unreadable — advisory figures are
    #: dropped rather than invented, and the row still imports.
    activity: Decimal | None
    available: Decimal | None


@dataclass
class YNABBudget:
    transactions: list[YNABTransaction] = field(default_factory=list)
    budget_entries: list[YNABBudgetEntry] = field(default_factory=list)
    plan_rows: list[YNABPlanRow] = field(default_factory=list)
    #: Rows dropped at parse time because their amount could not be read. A
    #: dropped row is visible in the counts; a row imported with a silently
    #: invented zero is not.
    errors: list[str] = field(default_factory=list)
    #: Account name -> (type key, on_budget), from an Accounts.csv member.
    #: Only IGAB's own export carries one; YNAB's does not, and then the
    #: preview falls back to guessing a type from the account's name. Empty
    #: rather than absent so every reader takes the same path.
    account_types: dict[str, tuple[str, bool]] = field(default_factory=dict)
