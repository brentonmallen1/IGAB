"""An Interest & fees envelope, under the credit cards.

Card interest and fees had nowhere to be filed: a transfer is wrong (no money
moved) and the card's own envelope refuses filing on purpose, because card
arithmetic overwrites it. They sat in "needs a category" forever.

`Category.system_key` lets the app find its own envelope by key rather than by
a name the user may change; `card_interest` is the only key.
`services/card_payment.ensure_interest_envelope` makes it for every budget that
gets a card from now on; this backfills the budgets that already have one, in
the same order the service works in:

1. the "Credit Card Payments" group, where a budget has cards but no such group
   (the showcase spec and some imports keep card envelopes elsewhere);
2. adopt a live, unkeyed "Interest & fees" / "Interest and fees" already in
   that group, so a user who made their own keeps its money and history;
3. otherwise insert one at the end of the group.

Every step is guarded by NOT EXISTS, so re-running creates nothing new.

`downgrade` drops the index and the column and nothing else: the envelopes may
hold money by then, and dropping money as a side effect of a downgrade is never
right. They stay as ordinary envelopes in the card group.

Revision ID: 2cb769068102
Revises: b3f70c5e12d9
"""

import sqlalchemy as sa
from alembic import op

revision = "2cb769068102"
down_revision = "b3f70c5e12d9"
branch_labels = None
depends_on = None

GROUP_NAME = "Credit Card Payments"
KEY = "card_interest"
NAME = "Interest & fees"
ADOPTABLE = ("interest & fees", "interest and fees")

#: A budget with a live card — `card_payment.is_card_account`, in SQL.
_HAS_CARD = (
    "EXISTS (SELECT 1 FROM accounts a WHERE a.budget_id = {budget}"
    " AND a.on_budget = true AND a.classification = 'liability'"
    " AND a.is_deleted = false)"
)
#: A budget whose keyed envelope already stands.
_HAS_KEYED = (
    "EXISTS (SELECT 1 FROM categories k WHERE k.budget_id = {budget}"
    " AND k.system_key = :key AND k.is_deleted = false)"
)


def upgrade() -> None:
    op.add_column("categories", sa.Column("system_key", sa.String(length=40), nullable=True))
    op.create_index(
        "uq_category_budget_system_key_live",
        "categories",
        ["budget_id", "system_key"],
        unique=True,
        postgresql_where=sa.text("system_key IS NOT NULL AND NOT is_deleted"),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO category_groups"
            " (id, budget_id, name, is_archived, is_system, sort_order, is_deleted)"
            " SELECT gen_random_uuid(), b.id, :group, false, false,"
            "   COALESCE((SELECT MAX(g2.sort_order) + 1 FROM category_groups g2"
            "     WHERE g2.budget_id = b.id AND g2.is_deleted = false), 0), false"
            " FROM budgets b"
            " WHERE " + _HAS_CARD.format(budget="b.id") + " AND NOT EXISTS (SELECT 1 FROM category_groups g"
            "   WHERE g.budget_id = b.id AND g.name = :group AND g.is_deleted = false)"
        ),
        {"group": GROUP_NAME},
    )
    conn.execute(
        sa.text(
            "UPDATE categories c SET system_key = :key"
            " FROM (SELECT DISTINCT ON (c2.budget_id) c2.id FROM categories c2"
            "   JOIN category_groups g ON g.id = c2.category_group_id"
            "   WHERE g.name = :group AND g.is_deleted = false"
            "   AND c2.is_deleted = false AND c2.system_key IS NULL"
            "   AND c2.linked_account_id IS NULL AND c2.linked_liability_id IS NULL"
            "   AND lower(c2.name) IN :adoptable"
            "   AND " + _HAS_CARD.format(budget="c2.budget_id") + "   AND NOT "
            + _HAS_KEYED.format(budget="c2.budget_id")
            + "   ORDER BY c2.budget_id, c2.sort_order, c2.created_at) pick"
            " WHERE c.id = pick.id"
        ).bindparams(sa.bindparam("adoptable", expanding=True)),
        {"key": KEY, "group": GROUP_NAME, "adoptable": list(ADOPTABLE)},
    )
    conn.execute(
        sa.text(
            "INSERT INTO categories"
            " (id, budget_id, category_group_id, name, system_key,"
            "  sort_order, is_archived, is_deleted)"
            " SELECT gen_random_uuid(), g.budget_id, g.id, :name, :key,"
            "   COALESCE((SELECT MAX(c3.sort_order) + 1 FROM categories c3"
            "     WHERE c3.category_group_id = g.id AND c3.is_deleted = false), 0),"
            "   false, false"
            " FROM category_groups g"
            " WHERE g.name = :group AND g.is_deleted = false"
            " AND " + _HAS_CARD.format(budget="g.budget_id") + " AND NOT "
            + _HAS_KEYED.format(budget="g.budget_id")
            # A live row of that exact name the adopt step could not take (a
            # card named "Interest & fees") would collide on the group's name
            # index; the budget is skipped rather than the upgrade failed.
            + " AND NOT EXISTS (SELECT 1 FROM categories n"
            "   WHERE n.category_group_id = g.id AND n.name = :name"
            "   AND n.is_deleted = false)"
        ),
        {"name": NAME, "key": KEY, "group": GROUP_NAME},
    )


def downgrade() -> None:
    op.drop_index("uq_category_budget_system_key_live", table_name="categories")
    op.drop_column("categories", "system_key")
