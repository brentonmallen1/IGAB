"""Money that left an envelope, as a list a person can read.

A budget move is a fact: an amount, a month, where from, where to. This turns
a row into a line — names on both sides, "To Be Assigned" when the money went
back to the pool — and nothing more. It does not say why the money moved and
never uses the word impulse: the wishlist and the Savings report both read
these lines, and both state the move and let the reader draw the conclusion.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from igab.domain.money import quantize_cents

TBA_LABEL = "To Be Assigned"
GONE_LABEL = "a deleted category"


class MoveLike(Protocol):
    id: UUID
    month: date
    created_at: datetime
    amount: Decimal
    from_category_id: UUID | None
    to_category_id: UUID | None


@dataclass(frozen=True)
class Drain:
    move_id: UUID
    month: date
    date: datetime
    amount: Decimal
    from_category_id: UUID
    from_name: str
    to_category_id: UUID | None
    to_name: str


def shape_drains(
    moves: Iterable[MoveLike], names: Mapping[UUID, str], tba_label: str = TBA_LABEL
) -> list[Drain]:
    """Outflows only: a move with no source envelope came from the pool and
    is not a drain of anything."""
    out: list[Drain] = []
    for move in moves:
        if move.from_category_id is None:
            continue
        out.append(
            Drain(
                move_id=move.id,
                month=move.month,
                date=move.created_at,
                amount=quantize_cents(move.amount),
                from_category_id=move.from_category_id,
                from_name=names.get(move.from_category_id, GONE_LABEL),
                to_category_id=move.to_category_id,
                to_name=(
                    tba_label
                    if move.to_category_id is None
                    else names.get(move.to_category_id, GONE_LABEL)
                ),
            )
        )
    return out


def drains_total(drains: Iterable[Drain]) -> Decimal:
    return sum((d.amount for d in drains), Decimal("0"))
