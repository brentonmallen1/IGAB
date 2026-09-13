"""Answers for the Guide's money explorer, with the classifier doing the deciding.

`domain/money_moves.py` knows what a hypothetical move's legs look like; the
class of each leg is asked of Postgres through `literal_class_query`, which is
the shipped rule ladder over literal booleans. No row is written.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.activity_class import (
    ActivityClass,
    ActivityReason,
    LegFacts,
    literal_class_query,
)
from igab.domain.money_moves import (
    SHAPES,
    Figures,
    Move,
    MoveExplanation,
    ShapeInfo,
    explain_move,
    figures,
    leg_facts,
    legs,
    month_buckets,
)


@dataclass(frozen=True)
class MonthExplanation:
    moves: list[MoveExplanation]
    class_totals: dict[str, Decimal]
    figures: Figures


@dataclass(frozen=True)
class ShapeExplanation:
    shape: ShapeInfo
    money_in: MoveExplanation
    money_out: MoveExplanation


class MoneyMovesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Per request: a month of moves repeats the same few leg shapes.
        self._classified: dict[LegFacts, tuple[ActivityClass, ActivityReason]] = {}

    async def classify(self, facts: LegFacts) -> tuple[ActivityClass, ActivityReason]:
        if facts not in self._classified:
            row = (await self.session.execute(literal_class_query(facts))).one()
            self._classified[facts] = (ActivityClass(row.cls), ActivityReason(row.reason))
        return self._classified[facts]

    async def explain(self, move: Move) -> MoveExplanation:
        classes = [await self.classify(leg_facts(leg)) for leg in legs(move)]
        return explain_move(move, classes)

    async def month(self, moves: Sequence[Move]) -> MonthExplanation:
        explained = [await self.explain(move) for move in moves]
        buckets = month_buckets(explained)
        return MonthExplanation(
            moves=explained, class_totals=dict(buckets), figures=figures(buckets)
        )

    async def shapes(self) -> list[ShapeExplanation]:
        return [
            ShapeExplanation(
                shape=shape,
                money_in=await self.explain(shape.money_in.move),
                money_out=await self.explain(shape.money_out.move),
            )
            for shape in SHAPES
        ]
