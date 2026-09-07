"""Pure target rules that are not arithmetic over a row: the legacy type
mapping the migration and the snapshot importer both apply, and when an unmet
target is "pending" rather than "underfunded".

Both are here rather than in `TargetService` because they have callers that
have no service — an Alembic migration states the mapping in SQL and a test
pins that SQL against this function; the snapshot importer normalises rows
before any service sees them.
"""

from datetime import date

from igab.domain.dates import month_end, month_start
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


#: The funding day a person may pick, 1-31. It used to stop at 28 — the last
#: day present in every month — because the comparison below had no clamp, so a
#: day of 30 would never arrive in February and the target would read "pending"
#: all month and never nag. Clamping the comparison is the fix; capping the
#: input was guarding it from the outside, and 28 is a strange thing to have to
#: explain to someone who is paid on the 30th.
MAX_FUNDING_DAY = 31


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

    `effective_day` is clamped to the month's real length, so "check after the
    31st" means the 31st, or the last day of a month that has no 31st. Without
    that, a day past 28 simply never arrives in February.
    """
    viewed = month_start(month)
    current = month_start(today)
    if viewed < current:
        return False
    if viewed > current:
        return True
    return today.day < min(effective_day, month_end(current).day)
