"""add_account_types_registry

Per-budget account-type registry: built-in types become rows (seeded for every
existing budget), users can add custom rows, and accounts gain a NOT NULL FK
to their type row. The legacy 'tracking' type is retired — existing tracking
accounts become 'investment' (or 'other_liability' when they were classified
as liabilities). Finally accounts.classification is backfilled from the type
row for EVERY account: the YNAB importer historically created off-budget
accounts with classification NULL, which made them invisible in the sidebar.

The seed rows are inlined (not imported from igab.domain.account_types) so
this migration replays identically forever; later changes to the built-ins
belong to later migrations.

Revision ID: a4d7e2c96b18
Revises: f2a8c5d17b39
Create Date: 2026-08-19 12:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d7e2c96b18"
down_revision: Union[str, Sequence[str], None] = "f2a8c5d17b39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (key, label, classification, default_on_budget, description, sort_order)
_BUILTINS: list[tuple[str, str, str, bool, str, int]] = [
    (
        "checking",
        "Checking",
        "asset",
        True,
        "Everyday spending account. On budget: its balance funds your "
        "envelopes, and spending from it needs a category.",
        0,
    ),
    (
        "savings",
        "Savings",
        "asset",
        True,
        "Money set aside but still yours to plan with. On budget so it can "
        "back envelopes like an emergency fund.",
        1,
    ),
    (
        "cash",
        "Cash",
        "asset",
        True,
        "Physical cash. Works exactly like checking, just tracked by hand.",
        2,
    ),
    (
        "credit_card",
        "Credit Card",
        "liability",
        True,
        "Card debt tracked transaction by transaction. On budget: card "
        "spending uses envelope money, and payments are transfers.",
        3,
    ),
    (
        "loan",
        "Loan",
        "liability",
        False,
        "A mortgage, auto, student, or other loan. Usually off budget — "
        "link a Liability record to it for payoff projections.",
        4,
    ),
    (
        "investment",
        "Investment",
        "asset",
        False,
        "Brokerage, retirement (401k, IRA), HSA, or similar. Off budget: it "
        "grows your net worth but isn't spendable envelope money.",
        5,
    ),
    (
        "other_asset",
        "Other Asset",
        "asset",
        False,
        "Anything else you own that counts toward net worth — property "
        "value, crypto, a manually tracked balance.",
        6,
    ),
    (
        "other_liability",
        "Other Liability",
        "liability",
        False,
        "Anything else you owe that counts against net worth but isn't "
        "budgeted transaction by transaction.",
        7,
    ),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "account_types",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(30), nullable=False),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("default_on_budget", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("budget_id", "key", name="uq_account_type_budget_key"),
    )
    op.create_index("ix_account_types_budget_id", "account_types", ["budget_id"])

    conn = op.get_bind()

    # Seed the built-ins for every existing budget
    for key, label, classification, default_on_budget, description, sort_order in _BUILTINS:
        conn.execute(
            sa.text(
                """
                INSERT INTO account_types
                    (id, budget_id, key, label, classification, default_on_budget,
                     description, is_system, sort_order)
                SELECT gen_random_uuid(), b.id, :key, :label, :classification,
                       :default_on_budget, :description, true, :sort_order
                FROM budgets b
                """
            ),
            {
                "key": key,
                "label": label,
                "classification": classification,
                "default_on_budget": default_on_budget,
                "description": description,
                "sort_order": sort_order,
            },
        )

    # Retire the 'tracking' type: liability-classified tracking accounts become
    # other_liability, the rest investment (the YNAB import heuristic used
    # tracking for brokerage/401k/IRA/HSA accounts).
    op.alter_column("accounts", "account_type", type_=sa.String(30))
    conn.execute(
        sa.text(
            """
            UPDATE accounts
            SET account_type = CASE
                WHEN classification = 'liability' THEN 'other_liability'
                ELSE 'investment'
            END
            WHERE account_type = 'tracking'
            """
        )
    )

    # Link every account to its type row, then lock the column down
    op.add_column(
        "accounts", sa.Column("account_type_id", sa.UUID(as_uuid=True), nullable=True)
    )
    conn.execute(
        sa.text(
            """
            UPDATE accounts a
            SET account_type_id = at.id
            FROM account_types at
            WHERE at.budget_id = a.budget_id AND at.key = a.account_type
            """
        )
    )
    op.alter_column("accounts", "account_type_id", nullable=False)
    op.create_foreign_key(
        "fk_accounts_account_type_id", "accounts", "account_types", ["account_type_id"], ["id"]
    )
    op.create_index("ix_accounts_account_type_id", "accounts", ["account_type_id"])

    # Repair the classification hole: derive it from the type row for EVERY
    # account (the importer left it NULL; on-budget accounts never had one).
    conn.execute(
        sa.text(
            """
            UPDATE accounts a
            SET classification = at.classification
            FROM account_types at
            WHERE at.id = a.account_type_id
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema. Custom account types are lost; accounts referencing
    them fall back to legacy keys by classification."""
    conn = op.get_bind()

    op.drop_index("ix_accounts_account_type_id", table_name="accounts")
    op.drop_constraint("fk_accounts_account_type_id", "accounts", type_="foreignkey")
    op.drop_column("accounts", "account_type_id")

    # Map post-registry keys (built-in and custom) back onto the legacy enum
    conn.execute(
        sa.text(
            """
            UPDATE accounts
            SET account_type = CASE
                WHEN account_type IN ('checking', 'savings', 'credit_card', 'loan')
                    THEN account_type
                WHEN account_type = 'cash' THEN 'checking'
                WHEN on_budget AND classification = 'liability' THEN 'credit_card'
                WHEN on_budget THEN 'checking'
                WHEN classification = 'liability' THEN 'loan'
                ELSE 'tracking'
            END
            """
        )
    )
    op.alter_column("accounts", "account_type", type_=sa.String(20))
    # Restore legacy semantics: classification only meant something off-budget
    conn.execute(sa.text("UPDATE accounts SET classification = NULL WHERE on_budget"))

    op.drop_index("ix_account_types_budget_id", table_name="account_types")
    op.drop_table("account_types")
