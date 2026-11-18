"""Which envelope a new row for a known payee most likely belongs in.

Auto-fill used to hand every new row the category of the payee's most recent
categorised row. Measured on eight years of a real budget, that was right
67.6% of the time; "the most recent row with the same amount, else the most
recent row" reached 72.8%; letting each payee keep whichever of three rules
has served it best reached 74.5%. Declining to guess for payees no rule
serves well cut the wrong fills from 27% to 11% — and a blank row asks to be
filed, where a wrong one hides.

The bug that made this urgent: a warehouse club's recent rows were all split
parents (uncategorised, so not history), the rule fell back to a date where
the annual membership and a grocery run share a date, and the membership was
entered second. `date DESC, created_at DESC` picked it, and every new grocery
run after that was filed under Membership. Under the rules here, "last" loses
that payee's scoreboard to "nearest", and a grocery-sized row lands in
Groceries while a membership-sized one still lands in Membership.

A real warehouse club is messier than that: its runs are filed under eight
envelopes, so no rule's record is trusted. Leaving every row blank there
was measured too and judged worse than two narrower answers — the same
amount seen before (the renewal), else the envelope holding half the
history (Groceries). Only a payee with neither is left blank.

Pure: the repository supplies `history`; `TransactionService.guess_category_for`
decides precedence around the result, for both the create path and the
editors' guess endpoint.
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Literal, NamedTuple

Rule = Literal["exact", "nearest", "last"]

#: How many of the payee's categorised rows the rule scores. The repository
#: fetches exactly this many and `guess_category` reads no further.
HISTORY_LIMIT = 24

#: How many of the most recent rows "nearest" looks among. Older amounts
#: describe what the payee used to charge; a gym that raised its price two
#: years ago should not be matched on the old price.
NEAREST_WINDOW = 12

#: A scoreboard needs this many replayed rows before its leader is trusted —
#: or distrusted. Below it, the guess is "exact, else last".
MIN_SCORED = 4

#: The leader must have been right on at least this share of its scored rows,
#: or it is not trusted and the fallbacks answer instead. Exact rational
#: arithmetic, so 3 of 5 is exactly 60% and passes.
MIN_HIT_RATE = Fraction(3, 5)

#: When the leader is not trusted, a category holding at least this share of
#: the history still answers. Exactly half fills.
DOMINANT_SHARE = Fraction(1, 2)

#: Scoreboard ties go to the more specific rule.
_TIE_ORDER: tuple[Rule, ...] = ("exact", "nearest", "last")


class HistoryRow(NamedTuple):
    """One categorised row for the payee. `history` is newest first, in the
    repository's order: `date DESC, created_at DESC`."""

    date: date
    amount: Decimal
    category_id: uuid.UUID


def _exact(prior: Sequence[HistoryRow], amount: Decimal) -> uuid.UUID | None:
    """The most recent row with the identical signed amount."""
    for row in prior:
        if row.amount == amount:
            return row.category_id
    return None


def _nearest(prior: Sequence[HistoryRow], amount: Decimal) -> uuid.UUID | None:
    """The closest signed amount among the last `NEAREST_WINDOW` rows; equal
    distances go to the more recent row."""
    best: HistoryRow | None = None
    for row in prior[:NEAREST_WINDOW]:
        if best is None or abs(row.amount - amount) < abs(best.amount - amount):
            best = row
    return best.category_id if best is not None else None


def _last(prior: Sequence[HistoryRow], amount: Decimal) -> uuid.UUID | None:
    """The most recent row — today's rule, ties broken the same way."""
    del amount
    return prior[0].category_id if prior else None


_RULES: dict[Rule, Callable[[Sequence[HistoryRow], Decimal], uuid.UUID | None]] = {
    "exact": _exact,
    "nearest": _nearest,
    "last": _last,
}


def _dominant(history: Sequence[HistoryRow]) -> uuid.UUID | None:
    """A category holding at least `DOMINANT_SHARE` of `history`, or None.
    Two at exactly half each: the one on the more recent row."""
    counts: dict[uuid.UUID, int] = {}
    for row in history:
        counts[row.category_id] = counts.get(row.category_id, 0) + 1
    for row in history:  # newest first, so a tie goes to the more recent
        if Fraction(counts[row.category_id], len(history)) >= DOMINANT_SHARE:
            return row.category_id
    return None


def scoreboard(history: Sequence[HistoryRow]) -> tuple[dict[Rule, int], int]:
    """Replay each row against only the rows older than it.

    Returns each rule's hits and the number of rows scored. A row is scored
    when it has at least one older row to be guessed from; a rule that makes
    no guess (exact, with no matching amount) counts as a miss, since a blank
    is not a correct fill.
    """
    hits: dict[Rule, int] = dict.fromkeys(_TIE_ORDER, 0)
    scored = 0
    for i, row in enumerate(history):
        prior = history[i + 1 :]
        if not prior:
            continue
        scored += 1
        for rule in _TIE_ORDER:
            if _RULES[rule](prior, row.amount) == row.category_id:
                hits[rule] += 1
    return hits, scored


def leader_is_trusted(hits: dict[Rule, int], scored: int) -> bool:
    """Whether the scoreboard's best rule has earned the answer: right on at
    least `MIN_HIT_RATE` of `scored` (> 0) replayed rows."""
    return Fraction(max(hits.values()), scored) >= MIN_HIT_RATE


def guess_category(history: Sequence[HistoryRow], amount: Decimal) -> uuid.UUID | None:
    """The payee's best rule applied to `amount`, or None when unsure.

    - No history: None (the service may fall back to the payee's default).
    - Fewer than `MIN_SCORED` scored rows: exact, else last.
    - Otherwise the scoreboard's leader (ties: exact, then nearest, then
      last). If the leader is exact and no row has this amount, the next rule
      in tie order answers — exact's record says amounts repeat for this
      payee, and nearest is exact's own answer whenever one does.
    - If the leader was right on under `MIN_HIT_RATE` of its scored rows it
      is not trusted, and in its place:
        1. a row with the identical signed amount — an annual renewal at a
           store otherwise filed many ways;
        2. else a category holding at least `DOMINANT_SHARE` of the history —
           a warehouse club that is mostly groceries, whatever the amount;
        3. else None.
    """
    history = list(history)[:HISTORY_LIMIT]
    if not history:
        return None

    hits, scored = scoreboard(history)

    if scored < MIN_SCORED:
        return _exact(history, amount) or _last(history, amount)

    if not leader_is_trusted(hits, scored):
        return _exact(history, amount) or _dominant(history)

    leader = max(_TIE_ORDER, key=lambda r: (hits[r], -_TIE_ORDER.index(r)))
    for rule in _TIE_ORDER[_TIE_ORDER.index(leader) :]:
        found = _RULES[rule](history, amount)
        if found is not None:
            return found
    return None
