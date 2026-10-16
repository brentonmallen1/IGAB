"""What the spending-shaped reports mean by their words, without a database.

The row set is `txn_filters.SPENDING_ROW` with `counted_classes`; this holds
the few pure rules the reports built on those rows share, so a word means one
thing on every tab that uses it.
"""

from collections.abc import Iterable
from decimal import Decimal

#: What a line of spending with no category is called, wherever a report
#: lists categories or groups. Its id is None, and a drill opens it by
#: `no_category`, never by an empty id list — that filters nothing and lists
#: the whole window.
UNCATEGORIZED = "Uncategorized"

#: The other reasons a row can have no category, for a rollup that groups
#: every row rather than only spending (`txn_query.GROUPABLE`). Only rows that
#: need a category (`txn_filters.NEEDS_CATEGORY`) may be called
#: `UNCATEGORIZED`: a rollup that filed a tracking account's market
#: adjustments there reported "Uncategorized" at three times a month's
#: spending, while the register's Uncategorized filter listed none of them.
#: A transfer between the user's own accounts needs no envelope.
TRANSFER_LABEL = "Transfer"
#: A row on a tracking account, which the budget never counts.
OFF_BUDGET_LABEL = "Off-budget"
#: Anything else with no category that still needs none — a row before its
#: account's budget start, a card's opening-balance correction.
NO_CATEGORY_LABEL = "No category"


def spent(amounts: Iterable[Decimal]) -> Decimal:
    """Spending from signed row amounts: outflows are stored negative, so the
    figure is their sum, sign-flipped, **net of refunds**.

    A category whose refunds exceed its purchases in a window comes out
    negative, and stays negative. Reports show it signed rather than dropping
    or clamping it: the total above them includes it, and a list that hid it
    would not add up to that total.
    """
    return -sum(amounts, Decimal("0"))


#: The fewest months a payee must appear in to be called recurring, however
#: short the window. Two months is a coincidence, not a habit.
RECURRING_FLOOR_MONTHS = 3


def recurring_months(window_months: int) -> int | None:
    """How many of the window's months a payee must appear in to be
    recurring: at least half of them, and never fewer than
    `RECURRING_FLOOR_MONTHS`. None when the window is too short to tell —
    the page says "needs 3+ months" rather than calling nothing recurring.

    A fixed three used to decide it whatever the window, so over two years a
    payee seen in three scattered months was "recurring", and over three
    months only a payee seen in every one of them was.
    """
    if window_months < RECURRING_FLOOR_MONTHS:
        return None
    return max(RECURRING_FLOOR_MONTHS, -(-window_months // 2))
