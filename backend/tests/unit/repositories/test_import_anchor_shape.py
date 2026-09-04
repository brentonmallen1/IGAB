"""What an import anchor is made of — the rule three writers used to each
hold a copy of.

The importer, the sample-budget generator and the scenario applier had
already drifted: the importer skipped a zero reserve row, the other two
wrote one, and a scenario therefore pinned an anchored state no real import
could produce. These are pure-shape tests; the round trip through Postgres
lives in `tests/integration/test_ynab_anchor.py`.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from igab.db.models import ImportAnchor
from igab.repositories.import_anchor_repo import (
    BudgetAnchor,
    _assemble,
    anchor_rows,
    category_opening,
)

D = Decimal
JUL, AUG = date(2026, 7, 1), date(2026, 8, 1)
BUDGET, CAT, OTHER_CAT, CARD = (uuid.uuid4() for _ in range(4))


def _rows(**kw):
    return anchor_rows(
        BUDGET,
        JUL,
        available=kw.get("available", {}),
        reserve=kw.get("reserve", {}),
        uncovered=kw.get("uncovered", {}),
    )


class TestWhichRowsGetWritten:
    def test_a_zero_available_is_written(self):
        """An envelope YNAB showed at zero is a position, not an absence —
        and the rows are how a walk learns the budget is anchored at all."""
        rows = _rows(available={CAT: D("0")})
        assert [(r.kind, r.category_id, r.amount) for r in rows] == [("available", CAT, D("0"))]

    def test_a_zero_card_leg_is_not(self):
        """A card with neither reserve nor uncovered debt has nothing to
        seed; truncation keys off the budget's anchor month, never off a
        row's presence."""
        rows = _rows(available={CAT: D("0")}, reserve={CARD: D("0")}, uncovered={CARD: D("0")})
        assert [r.kind for r in rows] == ["available"]

    def test_a_negative_reserve_is_written(self):
        """Non-zero, not positive: a card YNAB left with a negative CCP
        Available is exactly the position anchoring exists to carry."""
        rows = _rows(reserve={CARD: D("-40")})
        assert [(r.kind, r.account_id, r.amount) for r in rows] == [("reserve", CARD, D("-40"))]

    def test_every_row_carries_the_opening_month_and_one_target(self):
        rows = _rows(available={CAT: D("15")}, reserve={CARD: D("150")}, uncovered={CARD: D("400")})
        assert {r.month for r in rows} == {JUL}
        assert all((r.category_id is None) != (r.account_id is None) for r in rows)
        assert all(r.budget_id == BUDGET for r in rows)


class TestAssemblingTheSeeds:
    def test_no_rows_is_an_unanchored_budget(self):
        assert _assemble([]) is None

    def test_the_boundary_is_the_month_after_the_openings(self):
        anchor = _assemble(_rows(available={CAT: D("15")}))
        assert anchor is not None
        assert anchor.month == AUG
        assert anchor.openings.opening_month == JUL

    def test_rows_become_the_three_seed_maps(self):
        anchor = _assemble(
            _rows(
                available={CAT: D("15"), OTHER_CAT: D("0")},
                reserve={CARD: D("150")},
                uncovered={CARD: D("400")},
            )
        )
        assert anchor is not None
        assert anchor.openings.available_by_category == {CAT: D("15"), OTHER_CAT: D("0")}
        assert anchor.openings.reserve_by_card == {CARD: D("150")}
        assert anchor.openings.uncovered_by_card == {CARD: D("400")}

    def test_two_months_in_one_budget_raises_rather_than_picking_one(self):
        """An anchor is written once, in one statement, at one month. Two
        would mean picking from an unordered query — and every envelope
        figure moves with that choice."""
        rows = _rows(available={CAT: D("15")}) + anchor_rows(
            BUDGET, AUG, available={OTHER_CAT: D("5")}, reserve={}, uncovered={}
        )
        with pytest.raises(ValueError, match="written once"):
            _assemble(rows)

    def test_the_month_does_not_depend_on_row_order(self):
        rows = _rows(available={CAT: D("15")}, reserve={CARD: D("150")})
        assert _assemble(rows) == _assemble(list(reversed(rows)))


class TestTheCategorySeed:
    def test_none_for_an_unanchored_budget(self):
        assert category_opening(None, CAT) is None

    def test_a_category_the_anchor_never_named_opens_at_zero(self):
        """Not None: the truncation still applies. A category YNAB showed at
        zero and one the anchor skipped are the same position."""
        anchor = _assemble(_rows(available={CAT: D("15")}))
        assert category_opening(anchor, OTHER_CAT) == (JUL, D("0"))

    def test_a_named_category_opens_at_its_figure(self):
        anchor = _assemble(_rows(available={CAT: D("15")}))
        assert category_opening(anchor, CAT) == (JUL, D("15"))

    def test_the_seed_is_the_domain_objects_own_derivation(self):
        """One implementation: the repository delegates to `AnchorOpenings`,
        which the generator's verification and the probe read too."""
        anchor = _assemble(_rows(available={CAT: D("15")}))
        assert anchor is not None
        assert category_opening(anchor, CAT) == anchor.openings.opening_for(CAT)


def test_import_anchor_rows_are_model_instances():
    assert all(isinstance(r, ImportAnchor) for r in _rows(available={CAT: D("1")}))
    assert isinstance(_assemble(_rows(available={CAT: D("1")})), BudgetAnchor)
