"""Ordering rules for the lists a user arranges by hand — category groups,
categories, wishes, projects.

Pure: a repository loads the live rows and writes the positions; this decides
what the new order *is*, so every branch is a one-line test and the rule
exists once for every list that needs it.
"""

from collections.abc import Iterable, Sequence
from uuid import UUID

from igab.domain.exceptions import InvariantViolation


def renumber(ids: Iterable[UUID]) -> dict[UUID, int]:
    """Contiguous positions in the given order — what a reorder writes."""
    return {item_id: position for position, item_id in enumerate(ids)}


def merge_reorder(
    live: Sequence[tuple[UUID, bool]],
    given: Sequence[UUID],
    *,
    noun: str,
    plural: str | None = None,
    scope: str = "budget",
) -> list[UUID]:
    """The complete new order of `live` after the user reordered `given`.

    `live` is every current row as `(id, omittable)` in its current order;
    `given` is the client's list — the rows it showed, in the order the user
    chose. A row the client may omit (a hidden group, a hidden category, the
    Income group the grid never draws) keeps its old slot among the others,
    so it reappears where the user left it when it is shown again.

    Everything else is refused: a duplicate, an id this list does not own, or
    a required row missing — that last one is the stale client (a row added
    in another tab), which must fail loudly rather than shuffle rows the user
    never saw.
    """
    plural = plural or f"{noun}s"
    given_set = set(given)
    if len(given) != len(given_set):
        raise InvariantViolation(f"Reorder must list each {noun} at most once")
    live_ids = {row_id for row_id, _ in live}
    if given_set - live_ids:
        raise InvariantViolation(f"Reorder names a {noun} this {scope} does not have")
    required = {row_id for row_id, omittable in live if not omittable}
    if required - given_set:
        raise InvariantViolation(f"Reorder must list each of this {scope}'s visible {plural}")

    # Omitted rows hold their old slot; the given ids fill the rest in order.
    slots: list[UUID | None] = [None if row_id in given_set else row_id for row_id, _ in live]
    it = iter(given)
    return [slot if slot is not None else next(it) for slot in slots]
