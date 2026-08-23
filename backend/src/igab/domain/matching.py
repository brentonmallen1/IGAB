"""Scoring two transactions as "the same transaction".

Two services ask this — SimpleFIN dedup against already-synced rows, and
matching a synced row against a manual entry — and each carried its own
`_payee_similarity` and date-decay function.

The date functions were the same function written twice: one short-circuits
`delta == 0` to 1.0, which is what `1.0 - 0/(window+1)` already gives. Both
used a five-day window, so they agreed only because two constants happened to
match.

The payee functions gave **opposite** answers for an unknown payee — 0.5 in
one, 0.0 in the other — and neither said why. That difference is real and both
callers still make it, but they now make it out loud, at the call site, from
one implementation. It is safe in both today only because of arithmetic
nobody had checked: under either weighting a payee-less pair cannot reach its
auto-accept threshold on date evidence alone. `test_matching_scores.py` pins
that, so a future weight change cannot quietly make an unknown payee enough
to merge two transactions.
"""

from datetime import date

from rapidfuzz import fuzz

#: How far apart two postings may be and still look like one transaction.
#: Banks post two to five days after the date a user records.
DATE_WINDOW_DAYS = 5


def payee_similarity(a: str | None, b: str | None, *, unknown: float) -> float:
    """0..1 similarity, or `unknown` when either side has no payee.

    `unknown` is required and has no default on purpose: "how much does a
    missing payee count for" is a scoring decision each caller has to own,
    and defaulting it is how the two implementations came to disagree
    silently.

    WRatio combines ratio, partial_ratio, token_sort and token_set and takes
    the best — it is what makes a raw bank description match a cleaned payee.
    """
    if not a or not b:
        return unknown
    return fuzz.WRatio(a.lower(), b.lower()) / 100.0


def date_proximity(one: date, other: date, *, window_days: int = DATE_WINDOW_DAYS) -> float:
    """1.0 on the same day, decaying linearly to 0.0 just past `window_days`."""
    delta = abs((one - other).days)
    if delta > window_days:
        return 0.0
    return 1.0 - (delta / (window_days + 1))
