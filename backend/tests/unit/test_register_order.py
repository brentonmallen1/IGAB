"""The register's default order: the state ladder, server side.

`shared/register_order_cases.json` is the same table the client's
`registerOrder.test.ts` runs. The server decides which rows a page even
contains, the client re-sorts the pages it has; if the two ladders disagree a
row changes place as you scroll, which is the whole reason the table is shared
rather than written twice.

What this pins is the *ordering*, not just the numbers: the rungs that matter
are the ones where a row matches two at once — a reconciled row that is still
unfiled, an imported row that is reconciled and unapproved.
"""

import json
from pathlib import Path

import pytest

from igab.repositories.txn_filters import REGISTER_LADDER, register_rank

CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "register_order_cases.json").read_text()
)


def test_the_ladder_is_the_one_in_the_shared_table():
    """The fixture's ranks are indexes into this ladder, so a rung renamed or
    reordered here without the table is a silent re-numbering of every case."""
    assert [name for name, _, _ in REGISTER_LADDER] == CASES["ladder"]


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["note"])
def test_shared_register_order_cases(case):
    assert register_rank(case) == case["rank"]


def test_reconciled_is_the_floor():
    """The ask, stated once: nothing ranks below a settled row."""
    settled = {"cleared": "reconciled", "approved": True, "needs_category": False}
    assert register_rank(settled) == len(REGISTER_LADDER) - 1


def test_an_unknown_state_sorts_below_everything_rather_than_beside_reconciled():
    """`else_` is one past the last rung on purpose — a state nobody has taught
    the ladder about must not quietly join the finished work."""
    assert register_rank({"cleared": "voided", "approved": True, "needs_category": False}) == len(
        REGISTER_LADDER
    )
