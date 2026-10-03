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

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from rapidfuzz import fuzz

#: How far apart two postings may be and still look like one transaction.
#: Banks post two to five days after the date a user records.
DATE_WINDOW_DAYS = 5


def name_similarity(a: str | None, b: str | None, *, unknown: float) -> float:
    """0..1 similarity of two names, or `unknown` when either side is missing.

    The generic primitive. `unknown` is required and has no default on
    purpose: "how much does a missing name count for" is a scoring decision
    each caller has to own, and defaulting it is how two payee
    implementations came to disagree silently.

    WRatio combines ratio, partial_ratio, token_sort and token_set and takes
    the best — it is what makes a raw bank description match a cleaned payee,
    and an account's bank string match the one stored when it was linked.
    """
    if not a or not b:
        return unknown
    return fuzz.WRatio(a.lower(), b.lower()) / 100.0


def payee_similarity(a: str | None, b: str | None, *, unknown: float) -> float:
    """`name_similarity` under the name transaction matching asks for it by."""
    return name_similarity(a, b, unknown=unknown)


def best_payee_similarity(
    names: Iterable[str | None], other: str | None, *, unknown: float
) -> float:
    """The best `payee_similarity` between `other` and any of `names`.

    A row keeps several strings for the same merchant: the payee the user
    chose ("Starbucks"), the bank's own string from a pending record
    ("STARBUCKS #1234") and its description. When the bank re-identifies a
    record at posting, the posted string is usually near-identical to the
    bank's pending string even when it shares nothing with the user's payee
    — so the row is scored on whichever of its strings matches best, never
    on the user's payee alone. Non-strings and empty strings are skipped;
    with nothing to compare, the caller's `unknown` applies.
    """
    usable = [n for n in names if isinstance(n, str) and n]
    if not usable:
        return unknown
    return max(payee_similarity(n, other, unknown=unknown) for n in usable)


def date_proximity(one: date, other: date, *, window_days: int = DATE_WINDOW_DAYS) -> float:
    """1.0 on the same day, decaying linearly to 0.0 just past `window_days`."""
    delta = abs((one - other).days)
    if delta > window_days:
        return 0.0
    return 1.0 - (delta / (window_days + 1))


# ─── The dedup ladder ────────────────────────────────────────────────────────
#
# "Is this incoming bank record a row we already have?" Two callers ask it:
# the SimpleFIN sync, for every feed record, and the CSV import, for every
# file row. It lived inside the sync until the CSV import needed it. The
# import's own answer — an import-id hash over the payee string — could never
# see a cleaned payee ("Trader Joe's") and a raw bank descriptor
# ("TRADER JOE'S #552 SEATTLE WA") as one purchase, so a bank file over a
# history imported from another app came in almost entirely as new rows.

#: A combined score at or above this, within DEDUP_AUTO_DATE_MAX_DAYS, merges
#: without asking.
DEDUP_AUTO_MATCH_THRESHOLD = 0.80
#: How far to search for exact-amount candidates. Wide enough to cover
#: settlement lag: a payment the user dates when initiated can post a week+
#: later (a card payment dated the 15th, posted the 22nd).
DEDUP_DATE_WINDOW_DAYS = 10
#: Auto-matching is confined to this radius (the date-proximity score curve is
#: anchored here too). Beyond it, exact amount + similar payee is as likely a
#: recurring charge as a settlement-lagged duplicate — those candidates only
#: ever reach the review queue.
DEDUP_AUTO_DATE_MAX_DAYS = 5
#: Exact amount + a date this tight is near-certain identity regardless of
#: payee (bank descriptors rarely resemble user-renamed payees).
DEDUP_TIGHT_DATE_DAYS = 1
#: Payee-similarity margin that resolves a same-day tie between candidates.
DEDUP_TIEBREAK_MARGIN = 0.10
#: Below this, a candidate that carries the bank's OWN descriptor contradicts
#: the incoming one rather than merely differing from it, and the structural
#: shortcut (same amount, a day apart, nothing else nearby) may not take it
#: unasked: "BIGGBY COFFEE" and "HOME DEPOT" are two purchases, and merging
#: them loses one. A row a person typed is judged as before — their "Rent"
#: never resembles the bank's "CHECK 1234", and that pair is one payment.
#: The floor applies only where both sides are the bank's words. Two
#: unrelated descriptors score around 0.3 on shared punctuation and store
#: numbers alone; the same merchant under two spellings scores above 0.9.
DEDUP_STRUCTURAL_MIN_PAYEE = 0.5
#: What a missing payee counts for here. Neutral rather than zero: a bank
#: record often arrives before its payee is resolved, and scoring it zero
#: would stop it deduplicating against a row it genuinely matches. Safe
#: because 0.2 (max date) + 0.8 x 0.5 = 0.6, below the 0.80 auto threshold —
#: a payee-less pair can never auto-merge on date evidence alone. Pinned in
#: test_matching_scores.py. Transaction matching asks a different question
#: and answers it with 0.0, deliberately — see transaction_matching_service.
DEDUP_UNKNOWN_PAYEE_SCORE = 0.5


def dedup_payee_score(names: Iterable[str | None], incoming: str | None) -> float:
    """The ladder's payee evidence: the best of a row's strings against the
    incoming record's, a missing payee counting as neutral."""
    return best_payee_similarity(names, incoming, unknown=DEDUP_UNKNOWN_PAYEE_SCORE)


def dedup_score(payee_score: float, incoming_date: date, existing_date: date) -> float:
    """Combined evidence for an exact-amount pair. Date is weighted low
    because banks post 2-5 days after a person records the purchase; the
    payee carries most of the signal. Weights: date 20%, payee 80%."""
    proximity = date_proximity(incoming_date, existing_date, window_days=DEDUP_AUTO_DATE_MAX_DAYS)
    return round(proximity * 0.2 + payee_score * 0.8, 4)


@dataclass(frozen=True)
class MatchCandidate:
    """The slice of an existing row the ladder reads. Plain, so the ladder is
    testable without an ORM row."""

    id: uuid.UUID
    #: Every string the row keeps for its merchant — the user's payee and the
    #: bank's own strings. See `best_payee_similarity`.
    payee_strings: tuple[str | None, ...]
    #: The date to compare an incoming bank record against: the bank's own
    #: posting date when the row has one, because the incoming record's date
    #: is a bank date too and the two are then the same kind of fact. A row a
    #: person typed has no posting date and is compared on the date they
    #: entered — which is why the two can sit days apart and still be one
    #: transaction. Without this, a row the bank posted on the 25th but the
    #: user dated the 16th scored as nine days from its own re-issued
    #: posting, missed the auto threshold, and was written again.
    comparable_date: date
    #: The row carries the bank's own descriptor (DEDUP_STRUCTURAL_MIN_PAYEE).
    bank_words: bool

    @classmethod
    def from_row(cls, txn: Any, payee_name: str | None) -> "MatchCandidate":
        return cls(
            id=txn.id,
            payee_strings=(payee_name, txn.bank_payee, txn.import_description),
            comparable_date=txn.bank_posted_date or txn.date,
            bank_words=bool(txn.bank_payee or txn.import_description),
        )


@dataclass(frozen=True)
class MatchDecision:
    action: Literal["auto", "review", "create"]
    candidate_id: uuid.UUID | None = None
    score: float = 0.0
    #: Days between the incoming record and the candidate's comparable date.
    days: int = 0


@dataclass(frozen=True)
class _Scored:
    candidate: MatchCandidate
    similarity: float
    days: int
    score: float

    def decide(self, action: Literal["auto", "review"]) -> MatchDecision:
        return MatchDecision(action, self.candidate.id, self.score, self.days)


def decide_match(
    incoming_payee: str | None,
    incoming_date: date,
    is_posted: bool,
    candidates: Sequence[MatchCandidate],
) -> MatchDecision:
    """Decide how an incoming bank record relates to existing rows.

    Candidates already share the exact amount within the date window. The
    ladder: payee-driven auto-match on combined score, then structural
    auto-match (≤1 day, posted records only — pending amounts are
    provisional), then review. A candidate is never silently ignored: an
    unmatched exact-amount neighbor left behind is how duplicate rows are
    born.
    """
    if not candidates:
        return MatchDecision("create")

    scored: list[_Scored] = []
    for candidate in candidates:
        similarity = dedup_payee_score(candidate.payee_strings, incoming_payee)
        against = candidate.comparable_date
        scored.append(
            _Scored(
                candidate,
                similarity,
                abs((incoming_date - against).days),
                dedup_score(similarity, incoming_date, against),
            )
        )

    best = max(scored, key=lambda s: s.score)
    if best.score >= DEDUP_AUTO_MATCH_THRESHOLD:
        if best.days <= DEDUP_AUTO_DATE_MAX_DAYS:
            return best.decide("auto")
        # A candidate this strong but this distant (long settlement? weekly
        # recurring charge?) makes every structural shortcut below unsafe —
        # a human sorts it out.
        return best.decide("review")

    if is_posted:
        near = [s for s in scored if s.days <= DEDUP_TIGHT_DATE_DAYS]
        if len(near) == 1:
            only = near[0]
            # Same amount, a day apart, nothing else in reach — near-certain
            # identity, unless the bank's own descriptor on the row says
            # otherwise (see DEDUP_STRUCTURAL_MIN_PAYEE).
            if only.candidate.bank_words and only.similarity < DEDUP_STRUCTURAL_MIN_PAYEE:
                return only.decide("review")
            return only.decide("auto")
        if len(near) > 1:
            # Same-amount, same-day rows (recurring purchases, split legs):
            # payee similarity is the only disambiguator left. A clear winner
            # takes the match; a near-tie goes to human review over a guess.
            near.sort(key=lambda s: (-s.similarity, s.days))
            if near[0].similarity - near[1].similarity >= DEDUP_TIEBREAK_MARGIN:
                return near[0].decide("auto")
            return near[0].decide("review")

    return best.decide("review")


def settles_in_strict_pass(decision: MatchDecision) -> bool:
    """Whether a decision may be acted on in the first, exact-day pass.

    Both callers post in two passes, because the order records arrive in is
    not evidence. A record whose own twin is a day away must not lose it to a
    record processed earlier that had no twin and reached out for the nearest
    one — and having consumed it, sent the next record reaching further
    still. So every record that can claim a row on its own day claims first;
    only then may the rest look wider.
    """
    return decision.action == "auto" and decision.days == 0
