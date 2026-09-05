"""One anchor month per budget, held by the database

A budget's import anchor is written once, in one statement, at one month.
`ImportAnchorRepository._assemble` refuses to guess when it reads a mixed set —
picking one of two months would move every envelope figure in the budget
silently — but until now nothing stopped a mixed set from existing. The model
said so itself: "pinned by test, not by constraint".

The constraint is an exclusion, not a unique index, because the invariant is
not "one row per (budget, month)" — a budget writes one row per category and
per card, all at the same month. It is "no two rows of one budget disagree
about the month", which is exactly what `EXCLUDE USING gist (budget_id WITH =,
month WITH <>)` says.

`<>` under gist comes from btree_gist, a standard contrib extension present in
the postgres image this app ships. `CREATE EXTENSION` needs a role that may
create extensions; the shipped compose runs as the database owner, which may.
An installation pointed at a managed Postgres where that is not true should
create the extension once by hand before migrating.

Revision ID: c41d8b6ae973
Revises: f3a7c9e21d84
Create Date: 2026-09-04

"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "c41d8b6ae973"
down_revision: Union[str, Sequence[str], None] = "f3a7c9e21d84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # Any budget already carrying two months is corrupt in the way `_assemble`
    # raises on, and the constraint would fail to validate against it. There is
    # no correct automatic repair — which month is right is a question about
    # what the user imported — so this fails loudly with the budget named
    # rather than deleting rows to make the migration pass.
    op.execute(
        """
        DO $$
        DECLARE bad uuid;
        BEGIN
            SELECT budget_id INTO bad
            FROM import_anchors
            GROUP BY budget_id
            HAVING COUNT(DISTINCT month) > 1
            LIMIT 1;
            IF bad IS NOT NULL THEN
                RAISE EXCEPTION
                    'budget % carries import anchors at more than one month; '
                    'an anchor is written once, at one month. Resolve by hand '
                    'before migrating.', bad;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE import_anchors
        ADD CONSTRAINT ex_import_anchor_one_month_per_budget
        EXCLUDE USING gist (budget_id WITH =, month WITH <>)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE import_anchors DROP CONSTRAINT ex_import_anchor_one_month_per_budget"
    )
    # btree_gist is left in place: dropping an extension another table may have
    # started using is not this migration's call.
