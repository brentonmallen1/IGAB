"""Where counting began: the money that entered a balance chart by being
tracked, not by anything the household did.

Net Worth read +$620k over a year of which all but a few thousand was the
register filling in: accounts linked in June arrived carrying their balances
(Starting Balance rows), a card's pre-budget history arrived with it, and a
house and a car were first given values in September. Like-for-like the year
was slightly down. The Overview card said "+225.5%". For three months the
mortgage counted and the house did not, because a stated value counts nothing
before its first dated point — which is right, and needs saying on the chart
rather than being read as three bad months.

So a balance series carries, per point, what began being counted in the
stretch that point closes, and a change is quoted like-for-like: the
difference between two points, less what entered between them.

What counts as entering (`Entry.kind`):

- **account** — an account's Starting Balance row (class `opening_balance`,
  reason `starting_balance`): the account arriving with what it held. Signed
  as the ledger signs it, which is the sign net worth reads (a card's opening
  debt is negative).
- **pre_start** — the unfiled history from before an account's budget start
  (reason `before_budget_start`): the rest of the position it arrived with,
  spread over the months the bank handed over. Named apart from an arrival,
  because it moves an account already on the chart — a card linked in June
  with history to September is not "added" four times.
- **stated_asset** — the first dated value of an asset with no account (a
  home, a vehicle): positive.
- **manual_debt** — the first dated balance of a debt with no account:
  negative. One with no dated balance at all enters on the day the sheet first
  counts it, today, since that is the only day it is counted.

Pure: entries in, buckets and differences out. `services.tracking_start` reads
the entries from the database.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

ZERO = Decimal("0")

EntryKind = Literal["account", "pre_start", "stated_asset", "manual_debt"]

#: A balance that has not moved in this many days is flagged where it is
#: drawn. A stated value is a claim with a date, and an account nobody has
#: synced in two months reads as flat, not as unknown — which is the same
#: silence the entry markers exist to break.
STALE_AFTER_DAYS = 60


@dataclass(frozen=True)
class Entry:
    """Something that began being counted, and what that did to the total.

    `id` names the account, asset or liability, so one account's opening row
    and its pre-start history in the same stretch read as one arrival."""

    kind: EntryKind
    id: str
    name: str
    day: date
    amount: Decimal


@dataclass(frozen=True)
class StatedValue:
    """A figure the household told us rather than one a ledger adds up: an
    asset's value, or a debt with no account behind it.

    `points` is its dated series, oldest first; `current` the figure it
    stands at today (`manual_value`, `manual_balance`). Net worth reads the
    current figure on today and the step function (`at`) before it, so this
    is the one reading of both — the sheet's totals and the entry markers
    cannot disagree about when a value began to count.
    """

    kind: Literal["stated_asset", "manual_debt"]
    id: str
    name: str
    current: Decimal
    points: tuple[tuple[date, Decimal], ...]

    def at(self, day: date) -> Decimal:
        """The latest point on or before `day`, floored at zero, and nothing
        before the first point — a June appraisal must not rewrite January."""
        latest = ZERO
        for point_day, value in self.points:
            if point_day > day:
                break
            latest = value
        return max(ZERO, latest)

    @property
    def as_of(self) -> date | None:
        """The date of the newest point: when the current figure was last
        true. None for a debt typed in with no dated balance."""
        return self.points[-1][0] if self.points else None

    @property
    def sign(self) -> int:
        return 1 if self.kind == "stated_asset" else -1

    def entry(self, today: date) -> Entry | None:
        """When and with what this began to count. Its first positive point;
        with no point at all, today at its current figure — the only day the
        sheet counts it. None when it never counts."""
        first = next(((d, v) for d, v in self.points if v > ZERO), None)
        if first is None:
            first = (today, self.current) if not self.points and self.current > ZERO else None
        if first is None:
            return None
        day, value = first
        return Entry(kind=self.kind, id=self.id, name=self.name, day=day, amount=self.sign * value)


def stated_total(values: Sequence[StatedValue], kind: str, day: date, today: date) -> Decimal:
    """What the `kind` stated values add up to at the end of `day`: their
    current figures on today, their step functions before it."""
    return sum((s.current if day == today else s.at(day) for s in values if s.kind == kind), ZERO)


def place_entries(
    entries: Sequence[Entry], cutoffs: Sequence[date], since: date
) -> list[list[Entry]]:
    """Each entry in the bucket of the point whose stretch holds its day.

    Point `i` closes the stretch after point `i - 1` through `cutoffs[i]`
    inclusive — the same "rows on or before" every balance at a cutoff reads.
    The first point's stretch starts at `since` (its month's first day on a
    monthly chart): what entered before it is already in that point's balance
    and is not news on this chart. Entries after the last cutoff are dropped.

    Within a bucket one thing is one entry: an account that arrived with a
    Starting Balance row and three months of pre-start history is one account
    added, dated its first row, carrying the sum. Buckets list entries largest
    first, so a label naming one names the one that moved the chart.
    """
    if list(cutoffs) != sorted(cutoffs):
        raise ValueError("cutoffs must ascend")
    buckets: list[dict[tuple[str, str], Entry]] = [{} for _ in cutoffs]
    for entry in entries:
        if entry.day < since:
            continue
        index = next((i for i, cutoff in enumerate(cutoffs) if entry.day <= cutoff), None)
        if index is None:
            continue
        key = (entry.kind, entry.id)
        held = buckets[index].get(key)
        buckets[index][key] = (
            entry
            if held is None
            else Entry(
                kind=entry.kind,
                id=entry.id,
                name=entry.name,
                day=min(held.day, entry.day),
                amount=held.amount + entry.amount,
            )
        )
    return [
        sorted(
            (e for e in bucket.values() if e.amount != ZERO),
            key=lambda e: (-abs(e.amount), e.name),
        )
        for bucket in buckets
    ]


def entered(bucket: Sequence[Entry]) -> Decimal:
    """What a bucket's entries added to the total, signed."""
    return sum((e.amount for e in bucket), ZERO)


def like_for_like(values: Sequence[Decimal], entered_by_point: Sequence[Decimal]) -> Decimal | None:
    """The change from the first point to the last, less what entered between.

    The first point's own entries are not subtracted: they are in the balance
    the change is measured from. None with no points — there is no change to
    state, which is not the same as no change.
    """
    if len(values) != len(entered_by_point):
        raise ValueError("one entered figure per point")
    if not values:
        return None
    return values[-1] - values[0] - sum(entered_by_point[1:], ZERO)


def is_stale(last_changed: date | None, today: date) -> bool:
    """Unchanged for `STALE_AFTER_DAYS` or more. A balance with no date at all
    — a debt typed in with no dated point — is stale: nothing says when it
    was true."""
    return last_changed is None or today - last_changed >= timedelta(days=STALE_AFTER_DAYS)
