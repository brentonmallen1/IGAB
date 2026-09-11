"""The view-arrangement rule against the cases the client's `groupByView` runs.

`shared/view_arrangement_cases.json` is `viewGrouping.test.ts`'s list too, so a
change to where a view puts a category that lands on one side fails the other.
The copies were once held together by a comment, and the server honoured
`hide_unassigned` on a view with no groups while the grid did not.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from igab.domain.view_arrangement import arrange_by_view

_SHARED = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "view_arrangement_cases.json").read_text()
)


@pytest.mark.parametrize("case", _SHARED["cases"], ids=[c["name"] for c in _SHARED["cases"]])
def test_the_view_puts_each_category_where_the_grid_does(case):
    arrange = arrange_by_view(
        hide_unassigned=case["hide_unassigned"],
        group_names={g: g.title() for g in case["groups"]},
        placements={
            p["category_id"]: SimpleNamespace(group_id=p["group_id"], is_hidden=p["is_hidden"])
            for p in case["placements"]
        },
    )
    placed = {c: arrange(c) for c in case["categories"]}
    assert {c: (p[0] if p else None) for c, p in placed.items()} == case["expected"]
