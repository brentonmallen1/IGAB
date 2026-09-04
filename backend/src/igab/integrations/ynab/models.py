from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from igab.domain.dates import add_months, month_start


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
    seed reads, and `activity` is YNAB's own answer, kept for checking ours
    against. `available` is likewise advisory in every month but one: at the
    month before `plan_boundary` it becomes the import anchor — YNAB's own
    displayed position, written once as `ImportAnchor` rows so the walks
    start from it instead of re-deriving pre-anchor history."""

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


def plan_boundary(plan_rows: Sequence[YNABPlanRow], today: date) -> date | None:
    """The anchor boundary B for an export: the last plan month at or before
    today, or the export's first month when every month it carries is ahead
    of today.

    The one spelling of the rule — the parity check, the layout seed, the
    anchor writer and the import preview all call this, because two of them
    once spelled it differently (one clamped by today, one did not) and the
    difference only shows on an export carrying future assignment months.

    **B is always a month the export actually carries.** The obvious spelling,
    `month_start(min(today, max(month)))`, is not: an export budgeted ahead
    into December with nothing planned since June names September, which no
    plan row mentions. `_seed_arrangement` then matches no row and every
    group lands at sort_order 0 (the regression it exists to prevent), and
    the anchor seed reads an empty month. Picking from the months present
    keeps the clamp — never lay out or anchor on a future month — without
    inventing one.

    Openings are taken at B−1, the last *complete* YNAB month; the walks
    re-derive months >= B so the current month stays live for new rows. See
    `anchor_month` for the boundary the anchor itself can use, which is this
    one only when B−1 is also in the export.
    None means the export has no Plan.csv — a register-only file imports
    unanchored, and the walks run from zero exactly as before this feature.
    """
    if not plan_rows:
        return None
    months = {month_start(row.month) for row in plan_rows}
    past = [m for m in months if m <= month_start(today)]
    return max(past) if past else min(months)


def anchor_month(plan_rows: Sequence[YNABPlanRow], today: date) -> date | None:
    """B, but only when the export carries the complete month before it.

    The anchor seeds from B−1's figures, so a boundary whose previous month
    the file never mentions cannot be anchored on — a budget younger than one
    complete YNAB month, or an export that starts at B. Both the import
    preview and `_write_anchor` ask this, so the screen never promises an
    anchor the import then declines to write.
    """
    boundary = plan_boundary(plan_rows, today)
    if boundary is None:
        return None
    opening = add_months(boundary, -1)
    return boundary if any(month_start(row.month) == opening for row in plan_rows) else None
