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

#: The auto-generated bookkeeping payees. The two constants are the single
#: spelling for IGAB's own writers — `reconciliation_service` writes the
#: first; `simplefin_service` and the sample budget write the second — so a
#: row they create is recognized everywhere by construction, not by strings
#: staying in step. A YNAB export uses the same two names plus "Manual
#: Balance Adjustment", which IGAB never writes and only ever imports.
#:
#: A row under one of these names is a ledger correction, not spending
#: anybody did — checks that read filing quality must not treat it as a
#: purchase (`txn_filters.BALANCE_ADJUSTMENT_ROW` is the SQL reading of this
#: set). IGAB's own writers always leave these rows uncategorized; ones that
#: arrive *with* a category come from a YNAB import, which preserves the
#: export's "Inflow: Ready to Assign" filing because that is YNAB's own
#: convention for an adjustment on any account.
RECONCILIATION_ADJUSTMENT_PAYEE = "Reconciliation Balance Adjustment"
STARTING_BALANCE_PAYEE = "Starting Balance"
BALANCE_ADJUSTMENT_PAYEES = frozenset(
    {
        RECONCILIATION_ADJUSTMENT_PAYEE,
        STARTING_BALANCE_PAYEE,
        "Manual Balance Adjustment",
    }
)

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


#: A derived stem shorter than this is not a merchant name, it is a letter.
#: `^C` would match half the register.
MIN_DERIVED_STEM = 4


def _common_prefix(names: Sequence[str]) -> str:
    r"""The longest prefix every name shares, cut back to a word boundary.

    Cut back because half a word is a worse pattern than the word before it:
    the shared prefix of `SQ *BLUE BOTTLE` and `SQ *BLUEBIRD` is `SQ *BLUE`,
    and `^SQ \*BLUE` matches a third merchant nobody asked about. Ending at
    the last boundary keeps `^SQ \*`, which is honest about what is actually
    shared.
    """
    if not names:
        return ""
    shortest = min(names, key=len)
    end = 0
    for i, ch in enumerate(shortest):
        if any(name[i] != ch for name in names):
            break
        end = i + 1
    prefix = shortest[:end]
    if end < len(shortest) and prefix and prefix[-1].isalnum():
        cut = max(
            (i for i, ch in enumerate(prefix) if not ch.isalnum()),
            default=-1,
        )
        prefix = prefix[: cut + 1]
    return prefix


def derived_match_patterns(names: Sequence[str]) -> list[str]:
    """Patterns computed from the names themselves, no model involved.

    The suggester's answer used to be whatever the model said and nothing at
    all when it said something unusable — which is most of what "the AI regex
    is flaky" means in practice. These are the floor under it: the last one
    is an alternation of the names, so *something* that matches every name is
    always on offer, however the model behaved.

    Most specific last, matching the caller's contract, because that is also
    least useful: the alternation is a restatement of the list, correct and
    dull. The shared stem above it is the pattern a person would have written.
    """
    cleaned = [n.strip() for n in names if n.strip()]
    if not cleaned:
        return []
    out: list[str] = []
    prefix = _common_prefix(cleaned)
    if len(prefix.strip()) >= MIN_DERIVED_STEM:
        out.append("^" + re.escape(prefix))
    # Guaranteed full coverage. Escaped, so a name containing regex
    # metacharacters (`AMZN Mktp US*1A2B3`) cannot make the pattern invalid.
    out.append("^(?:" + "|".join(re.escape(n) for n in dict.fromkeys(cleaned)) + ")")
    return out


def rank_match_patterns(
    candidates: Iterable[object],
    names: Sequence[str],
    limit: int,
    avoid: Sequence[str] = (),
) -> list[str]:
    """The usable candidates among what a model proposed, best first.

    A candidate survives if it is a non-blank string that compiles and matches
    at least one name. Ordering, in order of importance:

    1. **Coverage** — how many of `names` it matches. The whole request is
       "one pattern for these", so one that leaves a name behind is worse
       than one that does not.
    2. **False hits** — how many of `avoid` it also matches. `avoid` is the
       budget's OTHER payees, which is what "too general" can be checked
       against instead of guessed at: `.*` and `^A` cover every name asked
       for and would swallow the register with them. Ranked rather than
       refused, because a pattern that catches one unrelated payee may still
       be the best on offer, and the caller shows the alternatives.
    3. **Proposal order** — so a model asked for most-specific-first keeps
       that order among equals, and the derived fallbacks the caller appends
       stay below anything the model got right.

    A candidate that misses a name is ranked, not withheld: one stray sample
    (a bank name split on its own comma) must not blank the whole answer.

    Newlines are trimmed but not spaces — a trailing space is significant
    ("^ACH DEPOSIT PAYROLL " must keep it).
    """
    scored: list[tuple[int, int, int, str]] = []
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
            misfires = sum(pattern_matches(pattern, other) for other in avoid)
        except re.error:
            continue
        if hits == 0:
            continue
        scored.append((hits, misfires, order, pattern))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    return [pattern for _, _, _, pattern in scored[:limit]]
