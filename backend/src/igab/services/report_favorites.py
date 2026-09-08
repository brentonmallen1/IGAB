"""Which reports the user starred.

Twenty-nine reports live behind a group dropdown and a tab row, which is a
fine way to find one you have never opened and a poor way to return to the
three you read every week.

**The server stores the list; it does not know what is in it.** Which reports
exist is a client fact — the tab ids are a TypeScript union, the labels are in
the client's registry, and no backend path reads either. So this validates
shape and size and nothing else, and the client drops ids it does not
recognise when it draws the row. Storing an allow-list here would put a second
copy of the report registry on the server, which would then have to be kept in
step with the real one by hand.

It lives in ``guide_state`` because that table is already the per-budget
key-value store for user preference, with an undo-recorded writer
(``set_state_recorded``) and a cascade to the budget. The name is narrower
than the table has turned out to be; a new table for one list of strings would
buy nothing but a migration.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from igab.guide.repo import GuideRepository, set_state_recorded
from igab.services.change_log import ChangeRecorder

#: Namespaced so `guide_state` stays legible as it takes on more than the
#: Guide's own keys.
FAVORITES_KEY = "reports:favorites"

#: A cap, not a design: favourites are for the handful someone returns to, and
#: an unbounded list in a JSONB column is a row that can grow without anyone
#: deciding it should.
MAX_FAVORITES = 12


def clean_favorites(tabs: Sequence[str]) -> list[str]:
    """Trimmed, de-duplicated, order preserved, capped.

    Order is the user's — the client sends the row as it should read — so this
    must not sort. De-duplication keeps the first occurrence for the same
    reason.
    """
    seen: set[str] = set()
    out: list[str] = []
    for tab in tabs:
        key = tab.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) == MAX_FAVORITES:
            break
    return out


class ReportFavoritesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = GuideRepository(session)
        self.changes = ChangeRecorder(session)

    async def favorites(self, budget_id: uuid.UUID) -> list[str]:
        value = (await self.repo.state(budget_id)).get(FAVORITES_KEY) or {}
        tabs = value.get("tabs")
        # A hand-edited row, or one written by an older shape. Reading it as
        # "no favourites" beats raising on a preference.
        if not isinstance(tabs, list):
            return []
        return clean_favorites([t for t in tabs if isinstance(t, str)])

    async def set_favorites(self, budget_id: uuid.UUID, tabs: Sequence[str]) -> list[str]:
        cleaned = clean_favorites(tabs)
        # None deletes the row: an empty list is the absence of a preference,
        # and a budget with no favourites should carry no favourites row.
        await set_state_recorded(
            self.repo,
            self.changes,
            budget_id,
            FAVORITES_KEY,
            {"tabs": cleaned} if cleaned else None,
        )
        return cleaned
