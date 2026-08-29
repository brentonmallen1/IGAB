"""What a bank's payee string says about the merchant, once the noise is off.

Three rules live here, all pure:

- `similarity_key` — the part of a raw payee name worth comparing. Banks
  append store numbers, reference codes and dates that change on every
  posting (`STARBUCKS #1234`, `AMZN Mktp US*1A2B3`, `PAYROLL 240815`), and a
  fuzzy score over the whole string is dragged down by exactly the part that
  carries no meaning: `ACME CORP PAYROLL #1234567890` against `#9876543210`
  scores 73 raw and 100 on its key. Payee Cleanup and import matching both
  score on this key, so a posting that would once have spawned a second
  payee on import is the same string Cleanup later groups.
- `distinctive_key` — the part of that key that names a *merchant* rather
  than a banking operation. `token_set_ratio` scores 100 whenever one side's
  tokens are a subset of the other's, which is right for `Northwind Payserv`
  against `NORTHWIND` and catastrophic for the literal string SimpleFIN sends on a
  card payment: `Payment` scored 100 against `Att Payment Jane Doe`,
  `Interest Payment`, and every other payee containing the word. The subset
  rule is not the bug; a subset made only of banking vocabulary is.
- `pattern_matches` — how a stored `match_pattern` applies to a raw name.
  The repository's matcher and the AI suggester both call it, so a pattern
  the suggester says "matches every name" is judged the way import judges it.
"""

import re
from collections.abc import Iterable, Sequence

#: Tokens carrying at least this many digits are the bank's, not the
#: merchant's: store numbers, reference codes, dates (`240815`, `08/15/26`).
#: Two digits stay — `76`, `Forever 21`, `24 Hour Fitness` are names.
NOISE_DIGITS = 3

_PUNCTUATION = re.compile(r"[^a-z0-9&]+")
#: A reference marker may sit mid-token (`US*1A2B3`): split before it so the
#: merchant half is judged on its own.
_BEFORE_MARKER = re.compile(r"(?=[#*])")


def _pieces(token: str) -> list[str]:
    return [piece for piece in _BEFORE_MARKER.split(token) if piece]


def _is_noise(piece: str) -> bool:
    digits = sum(c.isdigit() for c in piece)
    if digits >= NOISE_DIGITS:
        return True
    # `#1234`, `*1A2B3` — a marker with any digit behind it. A marker with no
    # digit (`*COFFEE`, as Square prefixes its merchants) is the name.
    return piece[0] in "#*" and digits > 0


def _collapse(name: str) -> str:
    return " ".join(_PUNCTUATION.sub(" ", name.lower()).split())


def similarity_key(name: str) -> str:
    """The comparable part of a raw payee name.

    Lowercased, noise tokens dropped, punctuation folded to spaces (keeping
    `&` — `H&R Block`), whitespace collapsed. If stripping leaves fewer than
    three alphanumeric characters (`1-800-FLOWERS`) the plain collapsed name
    is returned instead, so nothing ever compares as an empty string.
    """
    kept = [piece for token in name.split() for piece in _pieces(token) if not _is_noise(piece)]
    key = _collapse(" ".join(kept))
    if sum(c.isalnum() for c in key) < 3:
        return _collapse(name)
    return key


#: Words a bank writes about a *transaction* rather than about a merchant.
#: A raw name built only from these says nothing about who was paid, so it is
#: no evidence for a fuzzy match — see `distinctive_key`. Kept deliberately
#: narrow: every entry must be a word no merchant would be identified by on
#: its own. `interest` earns its place because "Interest" as a bank payee is
#: an interest charge, never the merchant "Interest".
GENERIC_BANK_WORDS = frozenset(
    {
        "ach",
        "authorized",
        "bank",
        "card",
        "charge",
        "charged",
        "check",
        "credit",
        "debit",
        "deposit",
        "fee",
        "fees",
        "interest",
        "online",
        "payment",
        "payments",
        "pending",
        "pos",
        "purchase",
        "recurring",
        "refund",
        "thank",
        "transfer",
        "withdrawal",
        "you",
    }
)


def distinctive_key(name: str) -> str:
    """`similarity_key` with banking vocabulary removed — what is left that
    could name a merchant.

    Empty means the name is *all* operation and no merchant ("Payment",
    "Interest Charge", "ONLINE PAYMENT, THANK YOU"). A caller matching one
    raw name against a list of payees must not match on an empty key: the
    result is decided by which unrelated payee happens to contain the word.

    Deliberately NOT folded into `similarity_key`, which Payee Cleanup and
    import matching both run against `shared/sample_cases.json`: dropping
    these words from the comparison key would make "Interest Payment" and
    "Att Payment Jane Doe" *more* alike, not less. This is a separate
    question — "is there a merchant in here at all?" — asked before scoring.
    """
    return " ".join(t for t in similarity_key(name).split() if t not in GENERIC_BANK_WORDS)


def dedupe_samples(parts: Iterable[str | None]) -> list[str]:
    """The bank-name samples a payee keeps: trimmed, blanks dropped, unique
    ignoring case with the first spelling kept, order of first appearance.

    Never splits — a bank name may contain a comma, and splitting on it is
    exactly how "DOE, JANE" once became two samples. The frontend's
    `dedupeSamples` is the same rule for its merge preview; both run
    `shared/sample_cases.json`.
    """
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if not isinstance(part, str):
            continue
        sample = part.strip()
        key = sample.lower()
        if not sample or key in seen:
            continue
        seen.add(key)
        out.append(sample)
    return out


def samples_from_legacy(value: object) -> list[str]:
    """A samples value as the list it means — including the comma-delimited
    string the column held before migration e3c7a9d51f28, which an older
    change-log snapshot can still carry into an undo. The string is split
    one last time, exactly as the migration split the column."""
    if isinstance(value, str):
        return dedupe_samples(value.split(","))
    if isinstance(value, list):
        return dedupe_samples(value)
    return []


def pattern_matches(pattern: str, name: str) -> bool:
    """Whether a stored match pattern claims a raw name: a case-insensitive,
    unanchored search. Raises `re.error` for a pattern that does not compile;
    the caller decides whether that is a skip or a refusal."""
    return re.search(pattern, name, re.IGNORECASE) is not None


def rank_match_patterns(
    candidates: Iterable[object], names: Sequence[str], limit: int
) -> list[str]:
    """The usable candidates among what a model proposed, widest coverage first.

    A candidate survives if it is a non-blank string that compiles and matches
    at least one name. Coverage — how many of `names` it matches — orders
    them; the proposal order breaks ties, so a model asked for most-specific-
    first keeps that order among equals. A candidate that misses a name is
    ranked, not withheld: one stray sample (a bank name split on its own
    comma) must not blank the whole answer, and the caller shows the count.

    Newlines are trimmed but not spaces — a trailing space is significant
    ("^ACH DEPOSIT PAYROLL " must keep it).
    """
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for order, candidate in enumerate(candidates):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        pattern = candidate.strip("\r\n")
        if pattern in seen:
            continue
        seen.add(pattern)
        try:
            hits = sum(pattern_matches(pattern, name) for name in names)
        except re.error:
            continue
        if hits == 0:
            continue
        scored.append((hits, order, pattern))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [pattern for _, _, pattern in scored[:limit]]
