"""guide bindings and state

Two per-budget tables behind the Guide's personalisation: what the user says
counts as each roadmap concept, and the rest of their Guide state (step
progress, preferences).

Revision ID: f7b2a4c98e13
Revises: d2e6a9c53b71
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7b2a4c98e13"
down_revision: Union[str, Sequence[str], None] = "d2e6a9c53b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guide_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_key", sa.String(40), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=True),
        # Not a foreign key: entity_type decides which table it points at.
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answer", sa.Boolean(), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "budget_id", "concept_key", "entity_type", "entity_id",
            name="uq_guide_binding_concept_entity",
        ),
    )
    op.create_index("ix_guide_bindings_budget_id", "guide_bindings", ["budget_id"])
    # Every read is "all rows for this budget and concept", so index the pair.
    op.create_index(
        "ix_guide_bindings_budget_concept", "guide_bindings", ["budget_id", "concept_key"]
    )

    op.create_table(
        "guide_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("budget_id", "key", name="uq_guide_state_budget_key"),
    )
    op.create_index("ix_guide_state_budget_id", "guide_state", ["budget_id"])


def downgrade() -> None:
    # Both tables hold only Guide preference — losing them resets the roadmap
    # to fully automatic, which is the documented default, not data loss.
    op.drop_index("ix_guide_state_budget_id", table_name="guide_state")
    op.drop_table("guide_state")
    op.drop_index("ix_guide_bindings_budget_concept", table_name="guide_bindings")
    op.drop_index("ix_guide_bindings_budget_id", table_name="guide_bindings")
    op.drop_table("guide_bindings")
