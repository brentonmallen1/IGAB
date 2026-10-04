"""Late arrivals count in the import month: mark YNAB rows and imported accounts.

An anchored import's walks start at the import month B, seeded from YNAB's
figures at B−1. A row dated in B−1 that reached IGAB after the import — a
straggler that cleared late, one typed in by hand — was in neither, so it
moved cash and nothing else. It now counts in B (`txn_filters.LATE_ARRIVAL`),
which needs two facts the schema did not hold:

- which rows the YNAB import wrote. They were stamped `created_via='import'`,
  the CSV importer's word; they are now `'ynab'`. The backfill marks every
  'import' row with no `import_batch_id` (the CSV importer always sets one) on
  a budget that has an anchor. A CSV split child or transfer leg made later
  inherits 'import' without the batch id and is marked too — so it counts as
  history, never as a late arrival. That is the safe direction: the only
  error it can make is the behaviour every budget had before this.
- which accounts came with the import. `accounts.from_import`; the backfill
  sets it on an anchored budget's accounts created no later than its anchor
  (the importer writes both in one transaction, so they share `now()`). An
  account linked afterwards stays false: its bank history is opening
  position, netted by its Starting Balance.

Unanchored budgets are untouched by both backfills, and the rule needs an
anchor, so their figures cannot move.

The category snapshot cache is cleared: it was built under the old buckets,
and the first rebuild after deploy would otherwise wait for the next write.

Revision ID: 1255a89c2bec
Revises: f4a7c2d91b3e
"""

import sqlalchemy as sa
from alembic import op

revision = "1255a89c2bec"
down_revision = "f4a7c2d91b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("from_import", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(
        """
        UPDATE transactions AS t
           SET created_via = 'ynab'
         WHERE t.created_via = 'import'
           AND t.import_batch_id IS NULL
           AND EXISTS (SELECT 1 FROM import_anchors a WHERE a.budget_id = t.budget_id)
        """
    )
    op.execute(
        """
        UPDATE accounts AS ac
           SET from_import = true
          FROM (SELECT budget_id, min(created_at) AS anchored_at
                  FROM import_anchors GROUP BY budget_id) AS a
         WHERE ac.budget_id = a.budget_id
           AND ac.created_at <= a.anchored_at
        """
    )
    op.execute("DELETE FROM budget_snapshot_meta")


def downgrade() -> None:
    op.execute("UPDATE transactions SET created_via = 'import' WHERE created_via = 'ynab'")
    op.drop_column("accounts", "from_import")
    op.execute("DELETE FROM budget_snapshot_meta")
