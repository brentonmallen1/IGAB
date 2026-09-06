"""remember import account mapping

A YNAB register export carries no account ids and no types — only names — so
the import's mapping step asks the same question once per account: what kind of
account is this, does it belong on budget, do I want it at all. On a real
export that is 47 answers, and it is the longest step in the import. Importing
the same file again asks all 47 again from scratch, and every re-answer is a
fresh chance to file a tracked account as on-budget.

Per user, and not derived from the accounts a previous import created. Two
things break derivation. A *skipped* account is never created — the importer
consults skip_accounts before _get_or_create_account — so there is no row to
read the choice back from, and skipping is the choice most worth keeping, since
a YNAB export carries archived accounts with no marker. And accounts cascade on
budget delete, so deleting the budget, which is exactly what testing an import
looks like, would take the memory with it. This table outlives every budget
built from it.

`account_key` is the name stripped and lowercased: the identity the importer
already matches on (`func.lower(Account.name) == name.lower()`). A single JSONB
document per user was the near miss — it is read whole, written whole, and
nothing joins against it, which is exactly the argument category_plans makes
for a document. The unique index is what decided against it. With a document,
the only thing stopping two spellings of one account from both persisting is
that every writer remembers to normalize, and a convention is not a mechanism.

Nothing here is authoritative. It pre-fills a form the person still sees and
can still change, it is shown as remembered rather than applied silently, and
it does not clear `needs_review`: a name we could not read last time is still a
name we cannot read.

Revision ID: c4e7b2a91d63
Revises: 86124882b15f
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c4e7b2a91d63"
down_revision: str | Sequence[str] | None = "86124882b15f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_account_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_key", sa.String(255), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(30), nullable=False),
        sa.Column("on_budget", sa.Boolean(), nullable=False),
        sa.Column("skip", sa.Boolean(), nullable=False),
        sa.Column("close", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # No separate index on user_id: this constraint's index leads with it.
        sa.UniqueConstraint("user_id", "account_key", name="uq_import_mapping_user_account"),
    )


def downgrade() -> None:
    op.drop_table("import_account_mappings")
