"""Shaping a budget move into a line a person can read."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from igab.domain.drains import GONE_LABEL, TBA_LABEL, drains_total, shape_drains


@dataclass
class Move:
    id: UUID
    month: date
    created_at: datetime
    amount: Decimal
    from_category_id: UUID | None
    to_category_id: UUID | None


BIKE, DINING = uuid4(), uuid4()
NAMES = {BIKE: "Bike Fund", DINING: "Dining Out"}
WHEN = datetime(2026, 8, 12, 9, 30)


def move(amount: str, frm: UUID | None, to: UUID | None) -> Move:
    return Move(uuid4(), date(2026, 8, 1), WHEN, Decimal(amount), frm, to)


def test_names_both_sides():
    [d] = shape_drains([move("60", BIKE, DINING)], NAMES)
    assert (d.from_name, d.to_name, d.amount) == ("Bike Fund", "Dining Out", Decimal("60.00"))


def test_money_released_to_the_pool_says_so():
    [d] = shape_drains([move("25", BIKE, None)], NAMES)
    assert d.to_name == TBA_LABEL
    assert d.to_category_id is None


def test_a_move_from_the_pool_is_not_a_drain():
    assert shape_drains([move("100", None, BIKE)], NAMES) == []


def test_a_deleted_category_is_named_as_such():
    [d] = shape_drains([move("5", BIKE, uuid4())], NAMES)
    assert d.to_name == GONE_LABEL


def test_total_and_cents():
    drains = shape_drains([move("10.005", BIKE, DINING), move("20", BIKE, None)], NAMES)
    assert drains_total(drains) == Decimal("30.00")
    assert drains_total([]) == Decimal("0")
