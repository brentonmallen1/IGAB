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
class YNABBudget:
    transactions: list[YNABTransaction] = field(default_factory=list)
    budget_entries: list[YNABBudgetEntry] = field(default_factory=list)
