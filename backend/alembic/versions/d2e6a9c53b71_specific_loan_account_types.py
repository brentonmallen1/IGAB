"""seed mortgage / auto_loan / student_loan account types and retype existing loans

Revision ID: d2e6a9c53b71
Revises: c1d9f4b26a83
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e6a9c53b71"
down_revision: Union[str, Sequence[str], None] = "c1d9f4b26a83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Inlined rather than imported from igab.domain.account_types so this replays
# identically forever; later wording changes belong to later migrations.
# (key, label, description, sort_order)
_NEW_TYPES: list[tuple[str, str, str, int]] = [
    (
        "mortgage",
        "Mortgage",
        "A home loan. Off budget, with APR, payment and payoff tracking attached to "
        "the account itself. Money you send here counts as paying down debt, not "
        "spending, so it stays out of your spending reports — including the escrow "
        "portion, which is why the payoff figures use the principal-and-interest amount.",
        4,
    ),
    (
        "auto_loan",
        "Auto Loan",
        "A car, truck, or other vehicle loan. Off budget. Money you send here counts "
        "as paying down debt rather than spending. Track the vehicle's value "
        "separately as an Other Asset if you want it in net worth.",
        5,
    ),
    (
        "student_loan",
        "Student Loan",
        "An education loan. Off budget. Money you send here counts as paying down "
        "debt, not spending. Several loans that are billed together can be one "
        "account, or separate ones if their rates differ enough to matter.",
        6,
    ),
]

# Reordered around the three insertions, so the picker keeps its grouping.
_RESORTED: list[tuple[str, int]] = [
    ("loan", 7),
    ("investment", 8),
    ("other_asset", 9),
    ("other_liability", 10),
]

#: The stored liability_type that justifies retyping a generic `loan` account.
#: Only these three: 'personal' and 'medical' have no account type of their own
#: and stay on `loan`, where the label reads "Loan" rather than something wrong.
_RETYPE: list[tuple[str, str]] = [
    ("mortgage", "mortgage"),
    ("auto", "auto_loan"),
    ("student", "student_loan"),
]


def upgrade() -> None:
    """Make the account-type vocabulary specific enough to carry a debt's name.

    `liability_type` is about to become derived from the linked account for
    managed liabilities, and that is only lossless if the account can say what
    the liability said. It could not: a mortgage, an auto loan and a student
    loan were all `loan`, so deriving would have relabelled "Maple St Mortgage"
    as "Loan". Three types close the gap, and the retype below moves the
    specificity from the liability row onto the account before anything starts
    reading it from there.

    `loan` stays as the generic. 'personal' and 'medical' liabilities keep it —
    an account type named Medical would be noise in a picker most people use
    for a chequing account, and a custom type covers anyone who wants one.
    """
    conn = op.get_bind()

    for key, label, description, sort_order in _NEW_TYPES:
        conn.execute(
            sa.text(
                """
                INSERT INTO account_types
                    (id, budget_id, key, label, classification, default_on_budget,
                     description, is_system, sort_order)
                SELECT gen_random_uuid(), b.id, :key, :label, 'liability',
                       false, :description, true, :sort_order
                FROM budgets b
                WHERE NOT EXISTS (
                    SELECT 1 FROM account_types t WHERE t.budget_id = b.id AND t.key = :key
                )
                """
            ),
            {"key": key, "label": label, "description": description, "sort_order": sort_order},
        )

    for key, sort_order in _RESORTED:
        conn.execute(
            sa.text(
                "UPDATE account_types SET sort_order = :sort_order "
                "WHERE key = :key AND is_system = true"
            ),
            {"key": key, "sort_order": sort_order},
        )

    # Move the specificity onto the account. Only a generic `loan` is retyped:
    # a user who deliberately chose something else keeps it.
    for liability_type, account_type in _RETYPE:
        conn.execute(
            sa.text(
                """
                UPDATE accounts a
                SET account_type = :account_type,
                    account_type_id = t.id
                FROM liabilities l, account_types t
                WHERE l.linked_account_id = a.id
                  AND l.is_deleted = false
                  AND l.liability_type = :liability_type
                  AND a.account_type = 'loan'
                  AND t.budget_id = a.budget_id
                  AND t.key = :account_type
                """
            ),
            {"liability_type": liability_type, "account_type": account_type},
        )

    # Derived for managed liabilities from here on, so it must be omittable.
    op.alter_column("liabilities", "liability_type", existing_type=sa.String(30), nullable=True)


def downgrade() -> None:
    """Collapse the three back into `loan`, keeping every account pointed at a
    type row that exists. The liability rows still carry their stored type, so
    the specificity survives the round trip — which is the reason the upgrade
    does not null the column out."""
    conn = op.get_bind()

    conn.execute(
        sa.text("UPDATE liabilities SET liability_type = 'other' WHERE liability_type IS NULL")
    )
    op.alter_column("liabilities", "liability_type", existing_type=sa.String(30), nullable=False)

    conn.execute(
        sa.text(
            """
            UPDATE accounts a
            SET account_type = 'loan', account_type_id = t.id
            FROM account_types t
            WHERE a.account_type IN ('mortgage', 'auto_loan', 'student_loan')
              AND t.budget_id = a.budget_id
              AND t.key = 'loan'
            """
        )
    )
    conn.execute(
        sa.text("DELETE FROM account_types WHERE key IN ('mortgage', 'auto_loan', 'student_loan')")
    )
    for key, sort_order in (
        ("loan", 4),
        ("investment", 5),
        ("other_asset", 6),
        ("other_liability", 7),
    ):
        conn.execute(
            sa.text(
                "UPDATE account_types SET sort_order = :sort_order "
                "WHERE key = :key AND is_system = true"
            ),
            {"key": key, "sort_order": sort_order},
        )
