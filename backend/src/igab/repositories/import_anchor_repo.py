"""Reads, the single write, and the row shape of a budget's import anchor.

Three things live here and nowhere else, because the first draft had each of
them in three places at once:

- `anchor_rows` — what rows an anchor *is* (which kinds are written, which
  zeros are skipped). The importer, the sample-budget generator and the
  scenario applier all call it, and they had already drifted: the importer
  skipped a zero reserve, the other two wrote one, so a scenario pinned an
  anchored state no import could produce.
- `category_opening` — the carryover seed for one category, derived from the
  loaded anchor rather than re-queried per category.
- `get_for_budget` — the ONE assembler of the walk-seed shape
  (`domain.cards.AnchorOpenings`): the card walk, the snapshot rebuild, the
  timeline and the probe all consume what it returns, so no two of them can
  disagree about what was anchored.

See `db.models.ImportAnchor` for what the rows mean and why they are
write-once.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, ImportAnchor
from igab.domain.cards import AnchorOpenings
from igab.domain.dates import add_months

ZERO = Decimal("0")


@dataclass(frozen=True)
class BudgetAnchor:
    """One budget's anchor: the boundary and the walk seeds.

    `month` is B — the first month the walks re-derive; the openings inside
    `openings` are stated at B−1 (`openings.opening_month`).
    """

    month: date
    openings: AnchorOpenings[uuid.UUID, uuid.UUID]


def anchor_rows(
    budget_id: uuid.UUID,
    opening_month: date,
    *,
    available: Mapping[uuid.UUID, Decimal],
    reserve: Mapping[uuid.UUID, Decimal],
    uncovered: Mapping[uuid.UUID, Decimal],
) -> list[ImportAnchor]:
    """The rows an anchor is made of, shaped once for every writer.

    `available` is written in full, **zeros included** — the rows are how a
    walk knows the budget is anchored at all, and an envelope YNAB showed at
    zero is a position, not an absence. A plan's B−1 month lists every
    category, so the importer always has some; a generated budget must list
    its scenario's categories for the same reason.

    `reserve` and `uncovered` are written only where non-zero: a card with
    neither has nothing to seed, and the truncation that matters keys off the
    budget-level anchor month, never off a row's presence.
    """
    rows = [
        ImportAnchor(
            budget_id=budget_id,
            month=opening_month,
            kind="available",
            category_id=category_id,
            amount=amount,
        )
        for category_id, amount in available.items()
    ]
    for kind, amounts in (("reserve", reserve), ("uncovered", uncovered)):
        rows.extend(
            ImportAnchor(
                budget_id=budget_id,
                month=opening_month,
                kind=kind,
                account_id=account_id,
                amount=amount,
            )
            for account_id, amount in amounts.items()
            if amount != ZERO
        )
    return rows


def category_opening(
    anchor: BudgetAnchor | None, category_id: uuid.UUID
) -> tuple[date, Decimal] | None:
    """A category's carryover seed `(B−1, its opening Available)`, or None.

    Zero where the anchor names no row for it — a category YNAB showed at
    zero and a category the anchor skipped are the same position, and both
    must still truncate. None only for an unanchored budget, which is the
    byte-identical path.
    """
    if anchor is None:
        return None
    return anchor.openings.opening_for(category_id)


class ImportAnchorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._by_budget: dict[uuid.UUID, BudgetAnchor | None] = {}
        self._by_category: dict[uuid.UUID, BudgetAnchor | None] = {}

    async def bulk_create(self, rows: list[ImportAnchor]) -> None:
        """The one write. Build `rows` with `anchor_rows`."""
        self.session.add_all(rows)
        await self.session.flush()

    async def get_for_budget(self, budget_id: uuid.UUID) -> BudgetAnchor | None:
        """The budget's anchor as walk seeds, or None for an unanchored budget.

        None is the byte-identical path: every walk treats it as "run from
        zero at the first month", exactly today's behavior.

        Memoized for the request: `get_budget_summary` alone asks through the
        card walk, the snapshot rebuild and the timeline, and the answer
        cannot change under a session that only ever writes anchors at import.
        """
        if budget_id in self._by_budget:
            return self._by_budget[budget_id]
        result = await self.session.execute(
            select(ImportAnchor).where(ImportAnchor.budget_id == budget_id)
        )
        anchor = _assemble(list(result.scalars()))
        self._by_budget[budget_id] = anchor
        return anchor

    async def get_for_category(self, category_id: uuid.UUID) -> tuple[date, Decimal] | None:
        """One category's carryover seed, for callers holding no budget id.

        Loads the category's whole budget anchor in a single query and
        memoizes it, so a loop over categories costs one round-trip each at
        worst and none once the budget is known. Callers that *do* hold the
        budget id — the summary's per-category loop above all — should load
        the anchor once and pass `category_opening(anchor, id)` instead.
        """
        if category_id not in self._by_category:
            result = await self.session.execute(
                select(ImportAnchor)
                .join(Category, Category.budget_id == ImportAnchor.budget_id)
                .where(Category.id == category_id)
            )
            rows = list(result.scalars())
            anchor = _assemble(rows)
            self._by_category[category_id] = anchor
            if anchor is not None:
                # Every category of that budget shares this anchor; the ones
                # asked for next are free.
                self._by_budget.setdefault(rows[0].budget_id, anchor)
        return category_opening(self._by_category[category_id], category_id)


def _assemble(anchors: list[ImportAnchor]) -> BudgetAnchor | None:
    """Rows to walk seeds. The rows of one budget are written in a single
    statement at import and are never edited, so they all carry the same
    month; a set with two is corrupt data, and picking one at random would
    move every envelope figure silently."""
    if not anchors:
        return None
    months = {row.month for row in anchors}
    if len(months) > 1:
        raise ValueError(
            f"budget {anchors[0].budget_id} has import anchors dated {sorted(months)}; "
            f"an anchor is written once, at one month, and the walks seed from it"
        )
    opening_month = months.pop()
    available: dict[uuid.UUID, Decimal] = {}
    reserve: dict[uuid.UUID, Decimal] = {}
    uncovered: dict[uuid.UUID, Decimal] = {}
    for row in anchors:
        if row.kind == "available" and row.category_id is not None:
            available[row.category_id] = row.amount
        elif row.kind == "reserve" and row.account_id is not None:
            reserve[row.account_id] = row.amount
        elif row.kind == "uncovered" and row.account_id is not None:
            uncovered[row.account_id] = row.amount
    boundary = add_months(opening_month, 1)
    return BudgetAnchor(
        month=boundary,
        openings=AnchorOpenings(
            month=boundary,
            available_by_category=available,
            reserve_by_card=reserve,
            uncovered_by_card=uncovered,
        ),
    )
