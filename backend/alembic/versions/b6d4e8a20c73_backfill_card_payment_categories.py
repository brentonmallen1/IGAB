"""backfill_card_payment_categories

Credit cards left Ready to Assign (domain/cards.py): a card's balance no
longer nets against cash, and the money set aside to pay it lives in a
linked category — one per on-budget liability account, in a hidden
"Credit Card Payments" group. `services/card_payment.ensure_payment_category`
guarantees the category for every account created or retyped from now on;
this backfills the accounts that already exist, so a budget imported last
month serves its card section on the first read after upgrading.

No schema change. Idempotent: accounts that already have a linked category
(the demo budget's showcase card) are left alone, and re-running creates
nothing new.

Revision ID: b6d4e8a20c73
Revises: a7c3e91d5f42
Create Date: 2026-08-28 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d4e8a20c73"
down_revision: str | Sequence[str] | None = "a7c3e91d5f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GROUP_NAME = "Credit Card Payments"


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    # One hidden group per budget that has at least one card account and no
    # live group of this name yet. sort_order goes last (max+1): hidden
    # groups do not render, but the arrangement should still be sane if one
    # is ever unhidden.
    conn.execute(
        sa.text(
            "INSERT INTO category_groups"
            " (id, budget_id, name, is_hidden, is_system, sort_order, is_deleted)"
            " SELECT gen_random_uuid(), b.id, :name, true, false,"
            "   COALESCE((SELECT MAX(g2.sort_order) + 1 FROM category_groups g2"
            "     WHERE g2.budget_id = b.id AND g2.is_deleted = false), 0), false"
            " FROM budgets b"
            " WHERE EXISTS (SELECT 1 FROM accounts a WHERE a.budget_id = b.id"
            "   AND a.on_budget = true AND a.classification = 'liability'"
            "   AND a.is_deleted = false)"
            " AND NOT EXISTS (SELECT 1 FROM category_groups g WHERE g.budget_id = b.id"
            "   AND g.name = :name AND g.is_deleted = false)"
        ),
        {"name": GROUP_NAME},
    )
    # One linked category per card that lacks one — the same predicate
    # `ensure_payment_category` applies. A soft-deleted linked category is
    # revived rather than duplicated, mirroring the service.
    conn.execute(
        sa.text(
            "UPDATE categories c SET is_deleted = false"
            " FROM accounts a"
            " WHERE c.linked_account_id = a.id AND c.is_deleted = true"
            " AND a.on_budget = true AND a.classification = 'liability'"
            " AND a.is_deleted = false"
        )
    )
    # A budget imported before the importer skipped YNAB's Credit Card
    # Payments group may hold a real category already named after the card,
    # in a group of this same name. That category IS the card's reserve —
    # adopt it (link it) rather than colliding with uq_category_group_name.
    conn.execute(
        sa.text(
            "UPDATE categories c SET linked_account_id = a.id"
            " FROM category_groups g, accounts a"
            " WHERE c.category_group_id = g.id AND g.budget_id = c.budget_id"
            " AND g.name = :name AND g.is_deleted = false"
            " AND c.is_deleted = false AND c.linked_account_id IS NULL"
            " AND a.budget_id = c.budget_id AND a.name = c.name"
            " AND a.on_budget = true AND a.classification = 'liability'"
            " AND a.is_deleted = false"
            " AND NOT EXISTS (SELECT 1 FROM categories c2"
            "   WHERE c2.linked_account_id = a.id)"
        ),
        {"name": GROUP_NAME},
    )
    conn.execute(
        sa.text(
            "INSERT INTO categories"
            " (id, budget_id, category_group_id, name, linked_account_id,"
            "  is_hidden, sort_order, is_deleted)"
            " SELECT gen_random_uuid(), a.budget_id, g.id, a.name, a.id, false,"
            "   ROW_NUMBER() OVER (PARTITION BY a.budget_id ORDER BY a.name, a.id) - 1,"
            "   false"
            " FROM accounts a"
            " JOIN category_groups g ON g.budget_id = a.budget_id"
            "   AND g.name = :name AND g.is_deleted = false"
            " WHERE a.on_budget = true AND a.classification = 'liability'"
            "   AND a.is_deleted = false"
            "   AND NOT EXISTS (SELECT 1 FROM categories c"
            "     WHERE c.linked_account_id = a.id)"
        ),
        {"name": GROUP_NAME},
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Deliberately a no-op: the categories may have accrued real assignments,
    # and dropping money as a side effect of a downgrade is never right. An
    # earlier revision simply ignores linked categories in a hidden group.
    pass
