"""subscription is a category tag

The Subscription system tag applied to payees, and the Subscriptions report
read payee tags. Every other counting tag lives on categories, and a
household files its subscriptions into categories (Streaming, Software) far
more reliably than it tags each payee. So the tag moves: the report reads
categories tagged Subscription and groups the charges by payee within them,
and the payee tag routes refuse it.

Existing payee tags are removed rather than migrated: a payee's dominant
category is a guess ("Amazon" under Shopping would tag all of Shopping a
subscription). The count removed is recorded per budget as a Guide-state
notice the Tags panel shows once, so the removal is not silent.

Revision ID: b8e5d1c73a49
Revises: a7d3b9e15c62
Create Date: 2026-09-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8e5d1c73a49"
down_revision: str | Sequence[str] | None = "a7d3b9e15c62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTICE_KEY = "notice:subscription_tag_moved"


def upgrade() -> None:
    # One notice per budget that loses rows, written before the rows go.
    op.execute(
        f"""
        INSERT INTO guide_state (id, budget_id, key, value, updated_at)
        SELECT gen_random_uuid(), t.budget_id, '{NOTICE_KEY}',
               jsonb_build_object('payee_tags_removed', count(pt.payee_id)), now()
        FROM payee_tags pt
        JOIN tags t ON t.id = pt.tag_id
        WHERE t.system_key = 'subscription'
        GROUP BY t.budget_id
        ON CONFLICT (budget_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )
    op.execute(
        """
        DELETE FROM payee_tags pt
        USING tags t
        WHERE t.id = pt.tag_id AND t.system_key = 'subscription'
        """
    )


def downgrade() -> None:
    # The removed memberships are not recoverable; only the notice goes.
    op.execute(f"DELETE FROM guide_state WHERE key = '{NOTICE_KEY}'")
