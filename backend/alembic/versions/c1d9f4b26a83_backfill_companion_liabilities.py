"""create the companion liability for existing liability-classified accounts

Revision ID: c1d9f4b26a83
Revises: b8c3e5a71f42
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c1d9f4b26a83"
down_revision: Union[str, Sequence[str], None] = "b8c3e5a71f42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make "every liability-classified account has a companion" true of
    accounts that already exist, not only ones created from here on.

    Without this, every consumer carries two empty states forever — no row, and
    a row with no terms — which is the complexity this work exists to delete.
    It would also apply to mortgages already in live budgets: they would keep
    the dead-end behaviour until deleted and recreated.

    Safe to run against live data. It only INSERTs, touching no existing row,
    and a companion contributes no numbers of its own: manual_balance is
    authoritative only when unlinked and these are linked, so the balance comes
    from the account's ledger exactly as before; terms are null, so nothing is
    computed from them (see LiabilityService.get_status).

    Two figures do move, both of them fixes:

    - The Liabilities report total RISES. `liabilities_report` sums whatever
      `get_all` returns, so a credit card or loan account with no companion is
      absent from the rollup entirely today — its debt real, on the ledger, and
      silently missing. It appears now, at its own ledger balance.
    - Net worth does NOT move. `_unmanaged_liabilities` counts only rows with
      linked_account_id IS NULL, precisely because managed ones are already
      counted through their account. These are managed. No double count.

    `liability_type` is coarse on purpose: the account registry cannot tell a
    mortgage from an auto loan, and guessing from the account name would be
    worse than 'other'. Phase 3 derives the type from the linked account and
    supersedes every value written here.

    compounding and the boolean flags are set explicitly — their defaults live
    in Python, not in the schema, so a raw INSERT that omits them fails on the
    NOT NULL constraints.
    """
    op.execute(
        """
        INSERT INTO liabilities (
            id, budget_id, name, liability_type, linked_account_id,
            interest_rate, minimum_payment, compounding,
            promo_deferred_interest, is_deleted
        )
        SELECT
            gen_random_uuid(),
            a.budget_id,
            a.name,
            CASE a.account_type WHEN 'credit_card' THEN 'credit_card' ELSE 'other' END,
            a.id,
            NULL,
            NULL,
            'monthly',
            false,
            false
        FROM accounts a
        WHERE a.classification = 'liability'
          AND a.is_deleted = false
          AND NOT EXISTS (
              SELECT 1 FROM liabilities l WHERE l.linked_account_id = a.id
          )
        """
    )


def downgrade() -> None:
    """Remove only what the backfill could have created.

    Terms, snapshots and a linked payment category are all things a user added
    after the fact; any row carrying one is no longer just a backfilled
    placeholder and is left alone. Deleting hard rather than soft: a
    soft-deleted row still occupies the unique linked_account_id slot, which
    would block re-running the upgrade.
    """
    op.execute(
        """
        DELETE FROM liabilities l
        WHERE l.linked_account_id IS NOT NULL
          AND l.interest_rate IS NULL
          AND l.minimum_payment IS NULL
          AND l.manual_balance IS NULL
          AND l.origination_date IS NULL
          AND l.original_principal IS NULL
          AND l.promo_end_date IS NULL
          AND l.term_months IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM liability_balance_snapshots s WHERE s.liability_id = l.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM categories c WHERE c.linked_liability_id = l.id
          )
        """
    )
