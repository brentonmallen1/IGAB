"""ai chat conversations and model call log

Four tables: the chat panel's conversations and their messages, and the
model-call log every AI feature now writes through `igab.ai.gateway`.

The log is split in two on purpose. `ai_calls` is light and permanent, so
listing the activity page stays cheap and "this call happened" survives
retention. `ai_call_payloads` holds the prompts, responses and tool traces,
keyed 1:1 by a primary key that *is* its foreign key so a second payload for
one call cannot be represented. Retention prunes payloads only.

Revision ID: 749d88a7777e
Revises: c4f18d70b3a2
Create Date: 2026-09-08 00:43:58.048952
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "749d88a7777e"
down_revision: str | None = "c4f18d70b3a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_conversations_budget_updated", "ai_conversations", ["budget_id", "updated_at"]
    )

    op.create_table(
        "ai_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("host", sa.String(length=200), nullable=False),
        sa.Column("endpoint", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_calls_budget_created", "ai_calls", ["budget_id", "created_at"])
    op.create_index("ix_ai_calls_feature_created", "ai_calls", ["feature", "created_at"])

    op.create_table(
        "ai_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("page_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ai_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_call_id"], ["ai_calls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index("ix_ai_messages_conversation_seq", "ai_messages", ["conversation_id", "seq"])

    op.create_table(
        "ai_call_payloads",
        sa.Column("ai_call_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("tool_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["ai_call_id"], ["ai_calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ai_call_id"),
    )


def downgrade() -> None:
    op.drop_table("ai_call_payloads")
    op.drop_index("ix_ai_messages_conversation_seq", table_name="ai_messages")
    op.drop_table("ai_messages")
    op.drop_index("ix_ai_calls_feature_created", table_name="ai_calls")
    op.drop_index("ix_ai_calls_budget_created", table_name="ai_calls")
    op.drop_table("ai_calls")
    op.drop_index("ix_ai_conversations_budget_updated", table_name="ai_conversations")
    op.drop_table("ai_conversations")
