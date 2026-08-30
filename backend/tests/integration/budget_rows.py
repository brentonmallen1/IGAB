"""Per-table row counts for one budget, derived from the schema.

The alternative — a hand-written list of tables to check — is what
``test_budget_delete.py`` used to do, against 14 of the 23 budget-owned
tables. Nine could have stopped cascading with the test still green.

Counting through ``budget_scope.budget_predicate`` means a new table is
covered by every test that uses this, the day it lands.
"""

from uuid import UUID

from sqlalchemy import MetaData, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.budget_scope import budget_predicate, budget_tables
from igab.db.models import Base


async def row_counts(
    session: AsyncSession, budget_id: UUID, metadata: MetaData = Base.metadata
) -> dict[str, int]:
    """How many rows each table in the budget graph holds for this budget."""
    counts: dict[str, int] = {}
    for table in budget_tables(metadata):
        stmt = (
            select(func.count())
            .select_from(table)
            .where(budget_predicate(table, budget_id, metadata))
        )
        counts[table.name] = (await session.execute(stmt)).scalar_one()
    return counts


def assert_fully_populated(counts: dict[str, int]) -> None:
    """Every table in the graph holds at least one row.

    A test that walks the whole graph proves nothing about a table the
    fixture never filled — it would pass identically if that table were
    dropped from the snapshot, or from the cascade.
    """
    empty = sorted(name for name, count in counts.items() if count == 0)
    assert not empty, (
        f"the fixture does not populate {empty}; this test proves nothing "
        f"about them. Add rows in full_budget.build_full_budget."
    )
