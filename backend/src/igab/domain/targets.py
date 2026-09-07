"""Pure target rules that are not arithmetic over a row: the legacy type
mapping the migration and the snapshot importer both apply, and when an unmet
target is "pending" rather than "underfunded".

Both are here rather than in `TargetService` because they have callers that
have no service — an Alembic migration states the mapping in SQL and a test
pins that SQL against this function; the snapshot importer normalises rows
before any service sees them.
"""

from datetime import date

from igab.domain.dates import month_start
from igab.domain.enums import TargetType

#: The type consolidated away. Undated it was `monthly_funding` (a flat
#: monthly duty); dated it was `savings_balance` with a date (reach a
#: balance by then). Kept as a constant so the two readers of old data name
#: the same string.
LEGACY_NEEDED_FOR_SPENDING = "needed_for_spending"


def normalize_legacy_target(target_type: str, target_date: date | None) -> str:
    """The current type for a stored `target_type`, mapping the retired one
    to what it always computed as. Pass-through for everything else — an
    unknown type is left for validation to refuse, not silently retyped."""
    if target_type == LEGACY_NEEDED_FOR_SPENDING:
        return TargetType.SAVINGS_BALANCE if target_date else TargetType.MONTHLY_FUNDING
    return target_type


def is_pending(month: date, today: date, effective_day: int) -> bool:
    """Whether an unmet target in `month` is still waiting for its funding
    day rather than overdue for it.

    - A month before today's: never — its day came and went.
    - Today's month: pending until `effective_day` arrives (on the day
      itself it is underfunded).
    - A later month: always — its day has not come. One meaning of pending,
      chosen over "future months read underfunded" so that looking ahead
      does not paint every row red; the Pending quick filter keeps
      assign-ahead planning findable.
    """
    viewed = month_start(month)
    current = month_start(today)
    if viewed < current:
        return False
    if viewed > current:
        return True
    return today.day < effective_day
