"""Which card-bill reminders the household has dismissed.

The reminder itself is decided in the client (`frontend/src/utils/paymentDue.ts`
`cardDueReminder`), which is the side that knows what day it is. What the
server keeps is the one thing the client cannot keep for itself: that
somebody said "I know" — shared across the household's devices, so a bill
dismissed on the phone does not reappear on the laptop.

**One key per dismissed reminder, never per card.** A dismissal is of one
due date in one state: `due:<account_id>:<YYYY-MM-DD>` for "due", with
`:past` appended for "past due". So dismissing "due" does not hide a later
"past due" for the same date, and dismissing one due date never silences the
next. At most 56 characters, inside `guide_state.key`'s 60.

Stored in ``guide_state`` like the report favourites (`report_favorites.py`):
it is already the per-budget key-value store for household preference, with
an undo-recorded writer and a cascade to the budget. Dismissing is a person's
decision, so it records and ⌘Z brings the reminder back.

Old keys are pruned on write: a due date more than `KEEP_DAYS` before today
can no longer be the one a reminder is about. The prunes are recorded in the
same batch as the dismissal that triggered them, the dismissal last, so one
⌘Z takes back both — rather than leaving an older dismissal whose undo would
refuse because its key had quietly vanished.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.guide.repo import GuideRepository, set_state_recorded
from igab.services.change_log import ChangeRecorder

DueState = Literal["due", "past_due"]

PREFIX = "due:"
PAST_SUFFIX = ":past"

#: How long a dismissal is kept. A reminder is only ever about the next due
#: date or the most recent one, so anything two billing cycles old is dead
#: weight in a table the Guide reads whole.
KEEP_DAYS = 60


@dataclass(frozen=True)
class Dismissal:
    account_id: uuid.UUID
    due_date: date
    state: DueState


def dismissal_key(account_id: uuid.UUID, due_date: date, state: DueState) -> str:
    key = f"{PREFIX}{account_id}:{due_date.isoformat()}"
    return key + PAST_SUFFIX if state == "past_due" else key


def parse_dismissal_key(key: str) -> Dismissal | None:
    """The dismissal a key spells, or None for any other key (or a mangled
    one — a hand-edited row reads as "not a dismissal", never as an error)."""
    if not key.startswith(PREFIX):
        return None
    body = key[len(PREFIX) :]
    state: DueState = "due"
    if body.endswith(PAST_SUFFIX):
        body = body[: -len(PAST_SUFFIX)]
        state = "past_due"
    account, _, day = body.partition(":")
    try:
        return Dismissal(uuid.UUID(account), date.fromisoformat(day), state)
    except ValueError:
        return None


def expired_keys(keys: list[str], today: date) -> list[str]:
    """Dismissal keys whose due date is more than `KEEP_DAYS` before today."""
    cutoff = today - timedelta(days=KEEP_DAYS)
    out = []
    for key in keys:
        parsed = parse_dismissal_key(key)
        if parsed is not None and parsed.due_date < cutoff:
            out.append(key)
    return out


async def list_dismissals(session: AsyncSession, budget_id: uuid.UUID) -> list[Dismissal]:
    state = await GuideRepository(session).state(budget_id)
    parsed = (parse_dismissal_key(key) for key in state)
    return sorted(
        (d for d in parsed if d is not None),
        key=lambda d: (d.due_date, str(d.account_id), d.state),
    )


async def dismiss(
    session: AsyncSession,
    changes: ChangeRecorder,
    budget_id: uuid.UUID,
    dismissal: Dismissal,
    today: date,
) -> list[Dismissal]:
    """Record one dismissal, prune the expired ones, and return what is left."""
    repo = GuideRepository(session)
    stale = expired_keys(list((await repo.state(budget_id)).keys()), today)
    key = dismissal_key(dismissal.account_id, dismissal.due_date, dismissal.state)
    with changes.batch():
        for old in stale:
            if old != key:
                await set_state_recorded(repo, changes, budget_id, old, None)
        await set_state_recorded(repo, changes, budget_id, key, {"dismissed_on": today.isoformat()})
    return await list_dismissals(session, budget_id)
