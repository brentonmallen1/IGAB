"""add multi-user support: is_admin, budget_members, change actor

Three pieces of one feature:

- users.is_admin gates user management and global-surface writes (settings,
  backups). Backfill marks EVERY existing user admin — a pre-multi-user
  database has exactly one real user (the env-bootstrapped admin), and
  sync_admin re-asserts the ADMIN_EMAIL user's flag at every boot anyway.

- budget_members becomes the authorization source of truth: every *Access
  guard resolves membership here instead of Budget.user_id (which remains as
  creator-of-record for the uq_budget_user_name constraint). Backfill gives
  each existing budget an 'owner' row for its creator, so upgraded installs
  keep exactly their current access.

- change_log.user_id records who made a change (NULL for system/AI actors),
  needed the moment two people share a budget. SET NULL on user deletion so
  history outlives accounts.

Revision ID: e9b3f6a25c17
Revises: c3b8e1a47d92
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e9b3f6a25c17"
down_revision: str | Sequence[str] | None = "c3b8e1a47d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE users SET is_admin = true")

    op.create_table(
        "budget_members",
        sa.Column("budget_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False, server_default="member"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("budget_id", "user_id"),
    )
    op.create_index("ix_budget_members_user", "budget_members", ["user_id"])
    op.execute(
        "INSERT INTO budget_members (budget_id, user_id, role)"
        " SELECT id, user_id, 'owner' FROM budgets"
    )

    op.add_column("change_log", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_change_log_user_id",
        "change_log",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_change_log_user_id", "change_log", type_="foreignkey")
    op.drop_column("change_log", "user_id")
    op.drop_index("ix_budget_members_user", table_name="budget_members")
    op.drop_table("budget_members")
    op.drop_column("users", "is_admin")
