"""Payee mapping_samples as a list, not a comma-delimited string.

A bank name can contain a comma ("NORTHWIND PAYSERV PAYROLL … DOE, JANE"),
and the delimited string split every one of them into two samples on save.
Existing text is split on commas one last time, trimmed, and de-duplicated
ignoring case; a sample already mangled by an earlier save stays as it is —
nothing can tell "JANE" apart from a real sample.

Revision ID: e3c7a9d51f28
Revises: b4e7c2d91a56
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3c7a9d51f28"
down_revision: str | Sequence[str] | None = "b4e7c2d91a56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payees",
        sa.Column("mapping_samples_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE payees p SET mapping_samples_list = COALESCE((
            SELECT jsonb_agg(s.t ORDER BY s.ord)
            FROM (
                SELECT DISTINCT ON (lower(trim(u.x))) trim(u.x) AS t, u.ord
                FROM unnest(string_to_array(p.mapping_samples, ',')) WITH ORDINALITY AS u(x, ord)
                WHERE trim(u.x) <> ''
                ORDER BY lower(trim(u.x)), u.ord
            ) s
        ), '[]'::jsonb)
        """
    )
    op.drop_column("payees", "mapping_samples")
    op.alter_column(
        "payees",
        "mapping_samples_list",
        new_column_name="mapping_samples",
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )


def downgrade() -> None:
    op.add_column("payees", sa.Column("mapping_samples_text", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE payees p SET mapping_samples_text = NULLIF((
            SELECT string_agg(v, ', ') FROM jsonb_array_elements_text(p.mapping_samples) AS v
        ), '')
        """
    )
    op.drop_column("payees", "mapping_samples")
    op.alter_column("payees", "mapping_samples_text", new_column_name="mapping_samples")
