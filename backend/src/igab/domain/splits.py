"""Whether a split's legs add up to its parent.

A split parent's amount must equal the sum of its children exactly. That
equality is what lets the rest of the app choose freely between summing parent
rows and summing leaf rows — see PARENT_ROW and LEAF in txn_filters.py — and
every account balance in the app depends on it.

This lives here rather than in `money.py`, which is scoped to validating a
single amount at the boundary. A split predicate is a relation *between*
amounts.

**No tolerance.** The check used to admit a 0.001 drift on the two creation
paths while `IntegrityService` compared exactly, so the creation paths
manufactured rows the integrity report then flagged forever. Amounts are
`Numeric(19,4)` columns and arrive through `Money`, which already rejects more
than four decimal places and anything non-finite; Decimal addition of such
values is exact. A tolerance here buys nothing and costs the invariant.

The one place slack is legitimate is coercing an LLM's arithmetic before it
becomes a ledger row — see `ai_draft_service`. Tolerate the model; never
tolerate the ledger.
"""

from collections.abc import Iterable, Sequence
from decimal import Decimal

from igab.domain.exceptions import InvariantViolation


def split_sum(legs: Iterable[Decimal]) -> Decimal:
    """Total of the legs, exact."""
    return sum(legs, Decimal("0"))


def split_balances(total: Decimal, legs: Sequence[Decimal]) -> bool:
    """Do the legs sum to the parent exactly?

    An empty leg list never balances, even against a zero parent: a split with
    no lines is a broken row, which is what IntegrityService reports it as.
    """
    if not legs:
        return False
    return split_sum(legs) == total


def require_split_balances(total: Decimal, legs: Sequence[Decimal]) -> None:
    """Raise unless the legs sum to the parent exactly."""
    if not legs:
        raise InvariantViolation("A split needs at least one line")
    actual = split_sum(legs)
    if actual != total:
        raise InvariantViolation(f"Split amounts {actual} do not sum to transaction amount {total}")
