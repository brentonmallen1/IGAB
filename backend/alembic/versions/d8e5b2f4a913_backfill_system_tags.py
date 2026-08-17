"""backfill_system_tags

System tags (Subscription, Savings, Long-term expense) are seeded when a
budget is created, but budgets that predate the feature never got them.
Insert any that are missing; budgets that already have a tag with the same
system_key (or a soft-deleted one — the user removed it on purpose) are
left alone.

Revision ID: d8e5b2f4a913
Revises: c7d94a1b3e58
Create Date: 2026-08-16 12:00:00.000000

"""
import uuid

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e5b2f4a913'
down_revision: Union[str, Sequence[str], None] = 'c7d94a1b3e58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors igab.repositories.tag_repo.SYSTEM_TAGS at the time of this migration
SYSTEM_TAGS = [
    ("subscription", "Subscription", "purple"),
    ("savings", "Savings", "green"),
    ("long_term_expense", "Long-term expense", "teal"),
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    budgets = conn.execute(sa.text("SELECT id FROM budgets")).scalars().all()
    for budget_id in budgets:
        existing = set(
            conn.execute(
                sa.text(
                    "SELECT system_key FROM tags"
                    " WHERE budget_id = :budget_id AND system_key IS NOT NULL"
                ),
                {"budget_id": budget_id},
            ).scalars()
        )
        taken_names = {
            name.lower()
            for name in conn.execute(
                sa.text("SELECT name FROM tags WHERE budget_id = :budget_id"),
                {"budget_id": budget_id},
            ).scalars()
        }
        for system_key, name, color_slot in SYSTEM_TAGS:
            if system_key in existing or name.lower() in taken_names:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO tags (id, budget_id, name, system_key, color_slot,"
                    " is_deleted, created_at, updated_at)"
                    " VALUES (:id, :budget_id, :name, :system_key, :color_slot,"
                    " false, now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "budget_id": budget_id,
                    "name": name,
                    "system_key": system_key,
                    "color_slot": color_slot,
                },
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Deliberately a no-op: we cannot tell backfilled tags apart from seeded
    # ones, and removing system tags would strip user assignments.
    pass
