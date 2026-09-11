"""How concentrated spending is: how few of the largest items make up most of
it. The Pareto report's "80% of Spend" card.

Pure. The client computes the same thing for category and group modes, which
it holds in full; the server computes it for payee mode, because it ranks
every payee and sends only the top 25. `shared/pareto_cases.json` runs
against both, so the two cannot drift.
"""

from collections.abc import Sequence
from decimal import Decimal

#: The share the card is about.
PARETO_SHARE = Decimal("0.8")


def items_to_share(totals: Sequence[Decimal], share: Decimal = PARETO_SHARE) -> int | None:
    """How many of `totals`, largest first, it takes to reach `share` of their
    sum. None when nothing was spent: there is no line to reach."""
    grand = sum(totals, Decimal("0"))
    if grand <= 0:
        return None
    running = Decimal("0")
    for count, total in enumerate(totals, start=1):
        running += total
        if running >= grand * share:
            return count
    return len(totals)
