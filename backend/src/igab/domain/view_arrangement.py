"""Where a budget view puts each category. One rule, run on both sides.

The budget page arranges its grid with the client's `groupByView` as the user
searches and filters, before any round-trip; the reports arrange the same
view on the server. The rule therefore exists twice, and the two copies are
held together by `shared/view_arrangement_cases.json`, which
`viewGrouping.test.ts` and `tests/unit/test_view_arrangement.py` both run.
They had drifted: the server honoured `hide_unassigned` on a view with no
groups, so one view drew a populated budget page and a blank spending report.

Pure: takes the view's own facts and returns the arranger. Reading the view
from the database stays in `ReportService._view_arrangement`.
"""

from collections.abc import Callable, Hashable, Mapping
from typing import Protocol

#: Bucket for categories a view has not placed. A string, not a UUID, so it
#: cannot collide with a real group id. The client's `UNASSIGNED_GROUP_ID`.
UNASSIGNED_VIEW_GROUP = "__unassigned__"


class Placement[G: Hashable](Protocol):
    @property
    def group_id(self) -> G | None: ...

    @property
    def is_hidden(self) -> bool: ...


def arrange_by_view[C: Hashable, G: Hashable](
    *,
    hide_unassigned: bool,
    group_names: Mapping[G, str],
    placements: Mapping[C, Placement[G]],
) -> Callable[[C], tuple[str, str] | None]:
    """`category_id -> (group_id, group_name)`, or None for a category the
    view leaves out.

    Hidden placements are dropped, even with no group. Unplaced categories,
    and placements with no group, fall to "Unassigned" unless the view hides
    those too — except on a view with no groups, where every category is
    unassigned and honouring `hide_unassigned` would show nothing at all.
    """
    hide = hide_unassigned and bool(group_names)

    def arrange(category_id: C) -> tuple[str, str] | None:
        placement = placements.get(category_id)
        if placement is not None and placement.is_hidden:
            return None
        group_id = placement.group_id if placement else None
        if group_id is None:
            return None if hide else (UNASSIGNED_VIEW_GROUP, "Unassigned")
        return str(group_id), group_names.get(group_id, "Unassigned")

    return arrange
