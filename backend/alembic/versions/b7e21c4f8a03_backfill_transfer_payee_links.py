"""backfill transfer payee links

Revision ID: b7e21c4f8a03
Revises: cdea6bae6ab3
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e21c4f8a03"
down_revision: Union[str, Sequence[str], None] = "cdea6bae6ab3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Point existing "Transfer : <account>" payees at the account they name.

    `payees.transfer_account_id` has existed since the initial schema, but only
    the sample-budget generator ever set it: the app's own transfer flow and the
    YNAB importer both created a payee that was merely *named* "Transfer : X".

    That field is what identifies a row as transfer-shaped once its partner link
    is missing, so until it is populated, orphaned transfer legs read as real
    income and expense. It is also what keeps transfer payees out of payee
    pickers and AI suggestions.

    Matched on the exact prefix the app writes, case-insensitively against the
    account name, and only within the same budget. Rows already carrying a link
    are left alone, and a name matching no account (the account was never
    imported, or was renamed since) is simply skipped — it stays an ordinary
    payee rather than being pointed somewhere wrong.
    """
    op.execute(
        sa.text(
            """
            UPDATE payees AS p
            SET transfer_account_id = a.id
            FROM accounts AS a
            WHERE p.transfer_account_id IS NULL
              AND p.is_deleted = false
              AND a.is_deleted = false
              AND a.budget_id = p.budget_id
              AND lower(p.name) = lower('Transfer : ' || a.name)
            """
        )
    )


def downgrade() -> None:
    """Clear links on payees whose name marks them as a transfer payee.

    Deliberately narrower than "everything this migration set": a payee linked
    by the sample-budget generator carries the same name shape, so this cannot
    distinguish them. Clearing is the safe direction — the link is derivable
    from the name again, and re-running upgrade() restores it.

    Matched case-insensitively to mirror upgrade(): `LIKE` is case-sensitive in
    Postgres, so a payee named "transfer : checking" would otherwise be linked
    on the way up and left linked on the way down.
    """
    op.execute(
        sa.text(
            """
            UPDATE payees
            SET transfer_account_id = NULL
            WHERE transfer_account_id IS NOT NULL
              AND lower(name) LIKE 'transfer : %'
            """
        )
    )
