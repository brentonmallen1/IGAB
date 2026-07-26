"""Declarative building blocks for the sample budget.

Pure data, no I/O. Every date is relative to a generation anchor so the
sample always ends "today" regardless of when it is created, and every
amount variation comes from cycled lists — no randomness, so two runs with
the same anchor produce identical data.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


def shift_months(anchor: date, months_ago: int) -> tuple[int, int]:
    """(year, month) of the month `months_ago` before the anchor's month."""
    total = anchor.year * 12 + (anchor.month - 1) - months_ago
    return total // 12, total % 12 + 1


@dataclass(frozen=True)
class RelDate:
    """A date expressed relative to the anchor month.

    months_ago=0 is the anchor's own month; negative values reach into the
    future (used for target dates). The day is clamped to the month length.
    """

    months_ago: int
    day: int

    def resolve(self, anchor: date) -> date:
        year, month = shift_months(anchor, self.months_ago)
        day = min(self.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)


@dataclass(frozen=True)
class AccountSpec:
    name: str
    account_type: str
    on_budget: bool = True
    opening_balance: Decimal = Decimal("0")
    sort_order: int = 0


@dataclass(frozen=True)
class TargetSpec:
    target_type: str
    amount: Decimal
    target_date: RelDate | None = None
    repeat_frequency: str | None = None


@dataclass(frozen=True)
class CategorySpec:
    name: str
    target: TargetSpec | None = None
    tags: tuple[str, ...] = ()
    linked_account: str | None = None
    # The zero-based budget assigned each month. When a month's spending would
    # push the envelope negative, the generator tops the assignment up ("money
    # was moved to cover it"), so history never shows accidental overspending.
    # None ⇒ assigned = that month's spending exactly (bill-like categories).
    monthly_budget: Decimal | None = None
    # Exactly one category absorbs the income surplus so TBA lands on the
    # spec's target — the classic "sweep leftovers into savings" habit.
    sweep_remainder: bool = False
    # Present ⇒ this category's current month is assigned exactly this much
    # BELOW its spending to date, guaranteeing one intentional overspend.
    overspend_this_month: Decimal | None = None


@dataclass(frozen=True)
class GroupSpec:
    name: str
    categories: tuple[CategorySpec, ...]
    is_system: bool = False


@dataclass(frozen=True)
class PayeeSpec:
    name: str
    default_category: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SplitLine:
    category: str
    amount: Decimal
    memo: str | None = None


@dataclass(frozen=True)
class MonthlyTxn:
    """One transaction per month on a fixed day. The amount is picked by
    calendar month number, so a 12-entry list yields a stable seasonal
    pattern (e.g. high electric bills every winter).

    When `splits` is non-empty the transaction is a split: the line set is
    cycled by calendar month like `amounts`, and the parent amount is the
    sum of its lines (`amounts` is ignored)."""

    account: str
    payee: str
    category: str | None
    day: int
    amounts: tuple[Decimal, ...] = ()
    memo: str | None = None
    splits: tuple[tuple[SplitLine, ...], ...] = ()


@dataclass(frozen=True)
class WeeklyTxn:
    """Transactions on fixed weekdays (0=Monday). Amounts and payees cycle
    by occurrence index — deterministic jitter and alternating stores."""

    account: str
    payees: tuple[str, ...]
    category: str | None
    weekdays: tuple[int, ...]
    amounts: tuple[Decimal, ...]
    memo: str | None = None


@dataclass(frozen=True)
class OneOffTxn:
    when: RelDate
    account: str
    payee: str
    amount: Decimal
    category: str | None = None
    memo: str | None = None
    splits: tuple[SplitLine, ...] = ()


@dataclass(frozen=True)
class TransferSpec:
    """A recurring monthly transfer. A category is only allowed when exactly
    one side is off-budget (YNAB spending-transfer semantics) and lands on
    the on-budget leg."""

    from_account: str
    to_account: str
    day: int
    amount: Decimal
    category: str | None = None
    memo: str | None = None


@dataclass(frozen=True)
class ScheduledSpec:
    account: str
    amount: Decimal
    frequency: str
    day: int
    payee: str | None = None
    category: str | None = None
    second_day_of_month: int | None = None
    transfer_account: str | None = None
    memo: str | None = None
    # For yearly schedules: how many months ago the last occurrence happened
    # (anchors the cycle so next_occurrence lands mid-window, not a year out).
    last_occurrence_months_ago: int = 0


@dataclass(frozen=True)
class SampleBudgetSpec:
    accounts: tuple[AccountSpec, ...]
    groups: tuple[GroupSpec, ...]
    payees: tuple[PayeeSpec, ...]
    monthly: tuple[MonthlyTxn, ...]
    weekly: tuple[WeeklyTxn, ...]
    one_offs: tuple[OneOffTxn, ...]
    transfers: tuple[TransferSpec, ...]
    scheduled: tuple[ScheduledSpec, ...]
    # (name, color_slot) tags created beyond the seeded system tags
    custom_tags: tuple[tuple[str, str], ...] = ()
    months_of_history: int = 12
    tba_target: Decimal = Decimal("150")
    # Openings and other budget inflows are categorized here (system group)
    income_group: str = "Income"
    opening_income_category: str = "Other Income"
