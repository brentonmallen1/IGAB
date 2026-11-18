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

Pure: the repository supplies `history`, the service decides precedence
around the result.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, NamedTuple

Rule = Literal["exact", "nearest", "last"]

#: How many of the payee's categorised rows the repository hands over.
HISTORY_LIMIT = 24

#: How many of the most recent rows "nearest" looks among. Older amounts
#: describe what the payee used to charge; a gym that raised its price two
#: years ago should not be matched on the old price.
NEAREST_WINDOW = 12

#: A scoreboard needs this many replayed rows before its leader is trusted —
#: or distrusted. Below it, the guess is "exact, else last".
MIN_SCORED = 4

#: The leader must have been right on at least this share of its scored rows,
#: or the guess is left blank. Hits are compared as integers against
#: `hits * DEN >= scored * NUM` so 3 of 5 (exactly 60%) passes.
MIN_HIT_RATE_NUM = 3
MIN_HIT_RATE_DEN = 5

#: Scoreboard ties go to the more specific rule.
_TIE_ORDER: tuple[Rule, ...] = ("exact", "nearest", "last")


class HistoryRow(NamedTuple):
    """One categorised row for the payee. `history` is newest first, in the
    repository's order: `date DESC, created_at DESC`."""

    date: date
    amount: Decimal
    category_id: uuid.UUID


@dataclass(frozen=True)
class GuessResult:
    """The guess, the rule that made it, and that rule's record for the payee.

    `category_id` is None for a new payee, and for an abstain — the leading
    rule was right on under 60% of at least four replayed rows. `rule` is
    None only when there is no history. `record` is `(hits, scored)` for the
    rule that was asked; `(0, 0)` when nothing was scored.
    """

    category_id: uuid.UUID | None
    rule: Rule | None
    record: tuple[int, int]


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


def guess_category(history: Sequence[HistoryRow], amount: Decimal) -> GuessResult:
    """The payee's best rule applied to `amount`, or None when unsure.

    - No history: None (the service may fall back to the payee's default).
    - Fewer than `MIN_SCORED` scored rows: exact, else last.
    - Otherwise the scoreboard's leader (ties: exact, then nearest, then
      last). If it was right on under 60% of its scored rows, abstain. If the
      leader is exact and no row has this amount, the next rule in tie order
      answers — exact's record says amounts repeat for this payee, and
      nearest is exact's own answer whenever one does.
    """
    history = list(history)[:HISTORY_LIMIT]
    if not history:
        return GuessResult(None, None, (0, 0))

    hits, scored = scoreboard(history)

    if scored < MIN_SCORED:
        found = _exact(history, amount)
        if found is not None:
            return GuessResult(found, "exact", (hits["exact"], scored))
        return GuessResult(_last(history, amount), "last", (hits["last"], scored))

    leader = max(_TIE_ORDER, key=lambda r: (hits[r], -_TIE_ORDER.index(r)))
    record = (hits[leader], scored)
    if hits[leader] * MIN_HIT_RATE_DEN < scored * MIN_HIT_RATE_NUM:
        return GuessResult(None, leader, record)

    for rule in _TIE_ORDER[_TIE_ORDER.index(leader) :]:
        found = _RULES[rule](history, amount)
        if found is not None:
            return GuessResult(found, leader, record)
    return GuessResult(None, leader, record)
