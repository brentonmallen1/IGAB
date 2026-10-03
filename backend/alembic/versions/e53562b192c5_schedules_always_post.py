"""Every schedule posts on its date: roll overdue schedules forward, drop auto_create.

A "remind me only" schedule (`auto_create` off) was skipped by the nightly
run, and every schedule a YNAB import created was one — so imported bills
never posted. The mode is gone: every schedule now posts itself on its date.

Turning that on as-is would post every schedule's backlog on the first night:
months of rent and paychecks, back-dated, for money the person had already
typed in by hand or the bank had already sent. So before the column goes,
every live overdue schedule (next date before today) is rolled forward to its
first occurrence on or after today WITHOUT posting anything. The stepping is
`domain.schedule.rolled_forward`, which steps exactly as Skip does — imported,
not inlined, on purpose: this must land each schedule where Skip would, and a
frozen copy of the arithmetic is the drift the one-implementation rule names.
A schedule whose end date passes on the way (or a `once` whose date has gone)
ends the way Skip ends one: soft-deleted, its dates left as they were.

"Today" is `today_server_local()` — the clock the nightly run asks — so the
first run after this finds nothing overdue to post.

Not change-logged: a migration is not a person's edit, and undoing a
roll-forward would put back exactly the backlog this exists to keep from
posting. The counts go to the migration log for the release note.

`downgrade` re-adds `auto_create` as false everywhere (the old default, and
what every imported schedule was) and leaves the rolled dates where they are:
there is no record of where they were, and moving them back would only make
them overdue again.

Revision ID: e53562b192c5
Revises: d81f4c2a6b09
"""

import logging
from datetime import date

import sqlalchemy as sa
from alembic import op

from igab.domain.schedule import rolled_forward
from igab.utils.clock import today_server_local

revision = "e53562b192c5"
down_revision = "d81f4c2a6b09"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.schedules_always_post")

_OVERDUE = sa.text(
    "SELECT id, frequency, start_date, next_occurrence_date, second_day_of_month, end_date"
    " FROM scheduled_transactions"
    " WHERE is_deleted = false AND next_occurrence_date < :today"
)
_MOVE = sa.text(
    "UPDATE scheduled_transactions SET next_occurrence_date = :lands, updated_at = now()"
    " WHERE id = :id"
)
#: What Skip does when there is no next occurrence: the repository's
#: soft delete, and nothing else.
_END = sa.text(
    "UPDATE scheduled_transactions SET is_deleted = true, updated_at = now() WHERE id = :id"
)


def roll_overdue_forward(conn: sa.Connection, today: date) -> tuple[int, int]:
    """Roll every live overdue schedule to its first occurrence on or after
    `today`, posting nothing. Returns (moved, ended).

    Schedules due today or later, and deleted ones, are not read at all.
    """
    moved = ended = 0
    for row in conn.execute(_OVERDUE, {"today": today}).all():
        lands = rolled_forward(row, today)
        if lands is None:
            conn.execute(_END, {"id": row.id})
            ended += 1
        else:
            conn.execute(_MOVE, {"id": row.id, "lands": lands})
            moved += 1
    return moved, ended


def upgrade() -> None:
    today = today_server_local()
    moved, ended = roll_overdue_forward(op.get_bind(), today)
    logger.info(
        "schedules_always_post: %d overdue schedule(s) rolled forward to on or after %s "
        "without posting; %d ended on the way",
        moved,
        today,
        ended,
    )
    op.drop_column("scheduled_transactions", "auto_create")


def downgrade() -> None:
    op.add_column(
        "scheduled_transactions",
        sa.Column("auto_create", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # The original column had no server default (the model supplied False);
    # the default above only fills the existing rows.
    op.alter_column("scheduled_transactions", "auto_create", server_default=None)
