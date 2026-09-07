"""tags apply to categories, not payees

Tags on payees are retired. The app had already reached this conclusion once,
for Subscription (b8e5d1c73a49): "a household files its subscriptions into
categories far more reliably than it tags each payee". Everything since has
agreed — `ESSENTIAL_TAGGED` was the last rule that read a payee tag for
meaning, and it now reads categories alone, so a tag on a payee changed no
number anywhere.

Rows are removed rather than migrated to the payee's categories, for
b8e5d1c73a49's reason: a payee's dominant category is a guess, and tagging
Shopping as a subscription because Amazon sells one is worse than tagging
nothing. The count removed is recorded per budget as a Guide-state notice the
Tags panel shows once, so the removal is not silent.

The `payee_tags` TABLE stays. Undo records and budget snapshots reference it,
and dropping it would break restoring anything taken before today; a later
release can drop it once those have aged out.

Revision ID: c4f18d70b3a2
Revises: e7c3a91d4b28
Create Date: 2026-09-07

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4f18d70b3a2"
down_revision: str | Sequence[str] | None = "e7c3a91d4b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTICE_KEY = "notice:payee_tags_retired"


def upgrade() -> None:
    # One notice per budget that loses rows, written before the rows go.
    op.execute(
        f"""
        INSERT INTO guide_state (id, budget_id, key, value, updated_at)
        SELECT gen_random_uuid(), t.budget_id, '{NOTICE_KEY}',
               jsonb_build_object('payee_tags_removed', count(pt.payee_id)), now()
        FROM payee_tags pt
        JOIN tags t ON t.id = pt.tag_id
        GROUP BY t.budget_id
        ON CONFLICT (budget_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )
    op.execute("DELETE FROM payee_tags")


def downgrade() -> None:
    # The removed memberships are not recoverable; only the notice goes.
    op.execute(f"DELETE FROM guide_state WHERE key = '{NOTICE_KEY}'")
