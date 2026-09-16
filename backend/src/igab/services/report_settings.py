"""Per-budget settings that change what the reports count.

One so far: whether the essentials figures spread sinking-fund bills over
twelve months (`guide.concepts.essentials_monthly`). It is a budget setting
rather than a per-report toggle because the Overview card, the Essentials and
Emergency Fund reports and the Guide's target all quote one figure — a toggle
on one surface that left the others as they were would be a second answer to
"what does a lean month cost".

Stored like the report favourites (`report_favorites.py`), in ``guide_state``
through the undo-recorded writer, so flipping it is a user decision that lands
in the change log and undoes.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from igab.guide.repo import GuideRepository, set_state_recorded
from igab.services.change_log import ChangeRecorder

SPREAD_SINKING_FUNDS_KEY = "reports:spread_sinking_funds"


async def spread_sinking_funds(session: AsyncSession, budget_id: uuid.UUID) -> bool:
    """On unless the budget turned it off. No row is on: the default is the
    figure a household with a yearly bill should see, and a budget that never
    touched the setting carries no row for it."""
    value = (await GuideRepository(session).state(budget_id)).get(SPREAD_SINKING_FUNDS_KEY)
    # A hand-edited row of another shape reads as the default rather than raising.
    return not (isinstance(value, dict) and value.get("on") is False)


async def set_spread_sinking_funds(session: AsyncSession, budget_id: uuid.UUID, on: bool) -> bool:
    """Off stores `{"on": false}`; on deletes the row, so the default and an
    explicit "on" are one state and undo has one thing to restore."""
    await set_state_recorded(
        GuideRepository(session),
        ChangeRecorder(session),
        budget_id,
        SPREAD_SINKING_FUNDS_KEY,
        None if on else {"on": False},
    )
    return on
