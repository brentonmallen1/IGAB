"""Add change_log.undo_seq and the (budget_id, seq) index

Revision ID: c4e8b2a71d59
Revises: b3d8e1f52a94
Create Date: 2026-09-01

`undone_at` defaults to func.now(), the transaction timestamp — identical for
every row one request undoes — so the redo candidate was picked by a column
that cannot order two undos from the same request, and the seq tie-break chose
the wrong end. `undo_seq` is stamped from its own sequence at undo time and
cleared on redo; existing undone rows are backfilled in (undone_at, seq) order
so the redo stack survives the upgrade. The index covers every hot selection,
all of which filter on budget_id and sort by seq.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8b2a71d59"
down_revision: Union[str, Sequence[str], None] = "b3d8e1f52a94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("change_log", sa.Column("undo_seq", sa.BigInteger(), nullable=True))
    op.execute("CREATE SEQUENCE IF NOT EXISTS change_log_undo_seq")
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY undone_at, seq) AS rn
            FROM change_log
            WHERE undone_at IS NOT NULL
        )
        UPDATE change_log SET undo_seq = ordered.rn
        FROM ordered
        WHERE change_log.id = ordered.id
        """
    )
    op.execute(
        "SELECT setval('change_log_undo_seq',"
        " (SELECT COALESCE(MAX(undo_seq), 0) + 1 FROM change_log), false)"
    )
    op.create_index("ix_change_log_budget_seq", "change_log", ["budget_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_change_log_budget_seq", table_name="change_log")
    op.execute("DROP SEQUENCE IF EXISTS change_log_undo_seq")
    op.drop_column("change_log", "undo_seq")
