"""accounts say whether they count as savings

Every off-budget asset used to count as savings. A transfer into one classed
SAVINGS, and a transfer out of one un-saved it — which is right for a
brokerage and wrong for a car. Buying a $9,000 car said the household saved
$9,000 that month; selling it three years later for $4,500 lowered the
savings rate by $4,500 and never reached Ready to Assign, where a sale's
proceeds belong.

So the account says. `accounts.counts_as_savings` is read by the activity
classifier for off-budget assets only; `account_types.default_counts_as_savings`
is what a new account of the type starts with, and the built-in descriptions
for `investment` and `other_asset` are rewritten to say so. `other_asset` defaults to
false — it is the type people pick for a house or a vehicle — and every other
type to true.

Existing accounts are backfilled so nothing changes for them unless the name
says it is property or a vehicle: an `other_asset` whose name matches the
words of `igab.domain.import_mapping._TRACKED_HINTS` (with that module's stem
suffixes and token boundaries) becomes false, and everything else keeps
counting as savings exactly as it did. The regex below is a frozen copy of
`suggest_counts_as_savings` as of this revision, inlined so this replays
identically forever.

The import mapping step's memory gains a nullable `counts_as_savings` too, so
a choice made there comes back on the next import. Null is every mapping
remembered before this revision, and means "never asked": the preview guesses
from the name rather than reading it as false.

The server defaults are load-bearing beyond the backfill: a budget snapshot
taken before these columns existed restores through INSERTs that do not name
them (`services/budget_snapshot.py`).

Revision ID: e3f1a8c5d920
Revises: b7d2e4a91c05
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f1a8c5d920"
down_revision: Union[str, Sequence[str], None] = "b7d2e4a91c05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Frozen copy of `_TRACKED_HINTS` matched the way `_matches` matches: whole
#: tokens, optionally followed by one of `_STEM_SUFFIXES`, where anything
#: outside [a-z0-9] separates tokens.
_PROPERTY_OR_VEHICLE = (
    "(^|[^a-z0-9])"
    "(property|house|home|real[^a-z0-9]+estate|land|condo|apartment"
    "|vehicle|car|truck|boat|motorcycle|auto|rv)"
    "(s|es|ing|ment|ments)?"
    "([^a-z0-9]|$)"
)

#: The two built-in descriptions that said every transfer here counts as
#: saving, rewritten to say the flag decides. Inlined, like the regex.
_DESCRIPTIONS: list[tuple[str, str]] = [
    (
        "investment",
        "Brokerage, retirement (401k, IRA), HSA, or similar. Off budget: it grows "
        "your net worth but isn't spendable envelope money. Money you move here "
        "counts as saving rather than spending, unless you turn off Counts as "
        "savings on the account. Growth inside the account — dividends, market "
        "movement — is not counted as saving, because you didn't put it there.",
    ),
    (
        "other_asset",
        "Anything else you own that counts toward net worth — a house, a car, "
        "crypto, a manually tracked balance. Off budget. It does not count as "
        "savings unless you turn Counts as savings on: buying the thing is "
        "spending and selling it is income. Turn it on for something you save "
        "into, like crypto.",
    ),
]


def upgrade() -> None:
    op.add_column(
        "account_types",
        sa.Column(
            "default_counts_as_savings", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "accounts",
        sa.Column("counts_as_savings", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.add_column(
        "import_account_mappings",
        sa.Column("counts_as_savings", sa.Boolean(), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE account_types SET default_counts_as_savings = false "
            "WHERE key = 'other_asset' AND is_system = true"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE accounts SET counts_as_savings = false "
            "WHERE account_type = 'other_asset' AND lower(name) ~ :pattern"
        ),
        {"pattern": _PROPERTY_OR_VEHICLE},
    )
    for key, description in _DESCRIPTIONS:
        conn.execute(
            sa.text(
                "UPDATE account_types SET description = :description "
                "WHERE key = :key AND is_system = true"
            ),
            {"key": key, "description": description},
        )


def downgrade() -> None:
    op.drop_column("import_account_mappings", "counts_as_savings")
    op.drop_column("accounts", "counts_as_savings")
    op.drop_column("account_types", "default_counts_as_savings")
