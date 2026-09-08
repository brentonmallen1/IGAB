"""record whether an answer's figures are grounded

Every money figure in an answer is matched against the numbers the tools
returned. The verdict is stored with the message rather than recomputed,
because the tool results it was checked against are pruned by retention and a
verdict that quietly changes on reload is worse than one that is simply old.

Revision ID: 1edb396867cb
Revises: 749d88a7777e
Create Date: 2026-09-08 16:34:06.789693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1edb396867cb'
down_revision: Union[str, Sequence[str], None] = '749d88a7777e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_messages",
        sa.Column("grounding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_messages", "grounding")
