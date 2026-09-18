"""api keys for the read-only MCP endpoint

The app's own credentials do not fit an assistant: an access token lasts 30
minutes, and a refresh token can mint full write access to everything its
owner has. A key is the narrow thing instead — read-only, scoped to named
budgets, revocable on its own.

Only the hash is stored, so a key is shown once and never again.

Revision ID: d5a91c3e04b7
Revises: b7f2a91c3d54
Create Date: 2026-09-18 14:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a91c3e04b7"
down_revision: Union[str, Sequence[str], None] = "b7f2a91c3d54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        # Unique: two keys hashing the same would mean the same secret twice.
        sa.Column("key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("scopes", sa.String(length=40), nullable=False, server_default="read"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "api_key_budgets",
        sa.Column(
            "api_key_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "budget_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("api_key_budgets")
    op.drop_table("api_keys")
