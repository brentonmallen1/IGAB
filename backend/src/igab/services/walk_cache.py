"""An in-process cache keyed on the snapshot cache's own validity signal.

**Why.** Every Budget page read runs the card walk (`BudgetService.card_walk`):
five history-wide sums, every assignment the budget ever made, and a
month-by-month simulation in Python. It was never cached, so the burst of
refetches after one edit — the month, the month before it, the Assign menu's
totals, Cover Overspending's preview, the hygiene panel — ran it five or six
times over identical inputs, and it was about seventy percent of a warm
month read.

**Validity is not a second mechanism.** The walk reads what the category
snapshots read — transactions, assignments, categories, the import anchor and
its history mode, accounts — and `igab.db.invalidation` already deletes the
budget's `BudgetSnapshotMeta` row on a write to any of them (`_WATCHED`). The
next rebuild writes a fresh `generation`. An entry is served only under the
generation it was computed with, so:

- no meta row (a write since the last rebuild, including this transaction's
  own uncommitted one) means no lookup and no store;
- a rebuild after a write is a new generation, which no entry carries.

There is no invalidation to call and nothing to clear. An entry that can no
longer match is simply never read again, and falls off the end.

**Read-only by contract.** A hit hands the same objects to every reader, so a
caller that mutated a walk's dicts would change the next request's figures.
None does — they read series and build new ones — and
`test_card_walk_cache.py` holds a served summary from a hit equal to one from
a cold walk, on the full sample budget.

Bounded by entry count, oldest out first. One budget's month read, the month
before, a report's range: a few dozen entries covers every page at once.
"""

import threading
import uuid
from collections import OrderedDict
from datetime import date


class GenerationCache[V]:
    """Values keyed by (budget, month), each valid for one snapshot generation."""

    def __init__(self, capacity: int = 48) -> None:
        self._capacity = capacity
        self._entries: OrderedDict[tuple[uuid.UUID, date], tuple[uuid.UUID, V]] = OrderedDict()
        # The scheduler's jobs are the only other caller; a lock is cheaper
        # than proving none of them runs on a thread.
        self._lock = threading.Lock()

    def get(self, budget_id: uuid.UUID, month: date, generation: uuid.UUID | None) -> V | None:
        if generation is None:
            return None
        key = (budget_id, month)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[0] != generation:
                return None
            self._entries.move_to_end(key)
            return entry[1]

    def put(
        self, budget_id: uuid.UUID, month: date, generation: uuid.UUID | None, value: V
    ) -> None:
        if generation is None:
            return
        key = (budget_id, month)
        with self._lock:
            self._entries[key] = (generation, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
