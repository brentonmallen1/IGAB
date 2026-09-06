"""One answer to "what kind of account is this, and what should happen to it".

A YNAB register export carries no account ids and no types — only names — so
the import's mapping step asks that question once per account. Three sources
can answer it: an `Accounts.csv` member (only IGAB's own export writes one),
what this person chose the last time they imported an account with the same
name (`db.models.ImportAccountMapping`), and a guess read from the name
itself. `build_ynab_preview` used to pick between the first and the last with
an `if` in the router; adding memory would have made that three sources
resolved inline, which is how the eight copies of "needs a category" started.

So the ladder lives here, once, as `resolve_account_suggestion`, and the guess
it falls back on (`suggest_account_type`) moved here with it. Pure and free of
the database, so every branch is a one-line test.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from igab.domain.account_types import BUILTIN_ACCOUNT_TYPE_KEYS


def account_key(name: str) -> str:
    """One spelling of "the same account, by name".

    Identity, not matching. `_normalize_for_match` below also lowercases, but
    it strips punctuation as well — using it as a key would fold "Vehicle-A"
    into "Vehicle A", which the importer creates as two separate accounts.
    This is the identity the importer already matches on
    (`func.lower(Account.name) == name.lower()`).
    """
    return name.strip().lower()


# YNAB register exports carry no account-type info — only names — so the
# mapping step suggests from name keywords and the user confirms per account.
# Where YNAB's own taxonomy lands in IGAB:
#   Checking → checking · Savings/Money Market → savings · Cash → cash
#   Credit Card / Line of Credit → credit_card
#   Mortgage → mortgage · Car/auto loans → auto_loan · Student → student_loan
#     · anything else owed → loan. All off budget, and all get their payoff
#     tracking automatically — the liability record comes with the account.
#   Asset tracking (brokerage, 401k, IRA, HSA, ESPP) → investment
#   Other tracking assets (crypto, treasury) → other_asset
#   Liability tracking → other_liability
#
# Matching is token-based, never substring: "ira" must not fire on "Admiral",
# "cc" must not fire on "Account", "mm" must not fire on "Summit". Multi-word
# keywords ("money market") match as adjacent tokens.
#
# Getting `on_budget` wrong is not a cosmetic error: to_be_assigned is
# `total_account_balance - total_category_balance - assigned_in_future`, so an
# account wrongly ON budget silently corrupts every budget number. Rules are
# therefore ordered most-specific first, and anything unrecognised is returned
# with needs_review set so the mapping UI can demand a decision.
_TYPE_HINTS: list[tuple[tuple[str, ...], str, bool]] = [
    # Explicit debt first — "Cedar Grove Property Loan" is a loan, not property.
    # Specific kinds before the generic, since "Student Loans" and "Car Loan"
    # both contain "loan": the first match wins, so the generic must be last.
    (("mortgage",), "mortgage", False),
    (("student",), "student_loan", False),
    (("loan", "heloc"), "loan", False),
    (
        ("credit", "card", "visa", "amex", "mastercard", "discover", "cc"),
        "credit_card",
        True,
    ),
    (
        (
            "invest",
            "brokerage",
            "401k",
            "401 k",
            "403b",
            "403 b",
            "457",
            "ira",
            "roth",
            "hsa",
            "retirement",
            "espp",
            "stock",
            "equity",
            "rollover",
            "pension",
            "annuity",
        ),
        "investment",
        False,
    ),
    (("crypto", "treasury"), "other_asset", False),
    (("checking", "chequing", "chk", "debit"), "checking", True),
    (("hysa", "money market", "mm", "saving", "savings", "emergency"), "savings", True),
    (("cash",), "cash", True),
]

# Names describing something owned or owed rather than a bank account. Which
# side it falls on cannot be read from the name — "Birchwood Property Ferry" is
# a mortgage while "Birchwood Property Ferry House" is the house — so the sign
# of the account's own register decides. Either way the account is OFF budget,
# which is the part that protects to_be_assigned; the asset/liability split
# only affects net-worth presentation, so a wrong guess there is cheap.
_TRACKED_HINTS: tuple[str, ...] = (
    "property",
    "house",
    "home",
    "real estate",
    "land",
    "condo",
    "apartment",
    "vehicle",
    "car",
    "truck",
    "boat",
    "motorcycle",
    "auto",
    "rv",
)

#: A vehicle word ALONE names the asset — "Vehicle A" is the car, not the debt
#: against it — so only its co-occurrence with "loan" says auto loan. Handled
#: outside _TYPE_HINTS because the words need not be adjacent ("Vehicle A Loan",
#: "Car (2019) Loan") and a phrase list cannot express that. Boats and the like
#: stay on the generic `loan`; there is no account type for them to be specific
#: about.
_VEHICLE_WORDS: tuple[str, ...] = ("car", "auto", "vehicle", "truck", "motorcycle", "rv")

#: YNAB users commonly mark tracking accounts in the name itself. That is a
#: deliberate statement about budget membership, so it outranks any type
#: keyword that also happens to appear ("Lakeside Trust MM - tracked" is a
#: tracking account, not a money-market savings account).
_OFF_BUDGET_MARKERS: tuple[str, ...] = ("tracked", "tracking", "off budget")


def _normalize_for_match(name: str) -> str:
    """Lowercase, punctuation → single spaces, padded so " kw " matches on
    token boundaries at either end."""
    return " " + re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() + " "


#: Keywords that also match inside a run-together name ("TreasuryDirect",
#: "SavingsPlus"). Listed explicitly rather than by length: a length rule lets
#: "discover" fire on "Discovery Fund". Every entry here must be a word that
#: cannot be the prefix of an unrelated one.
_CONCATENATION_SAFE: frozenset[str] = frozenset(
    {"treasury", "brokerage", "mortgage", "savings", "checking", "retirement"}
)


#: Keywords are stems, not whole words: "invest" has to reach "Investments",
#: "Investment Account" and "Investing". The move from substring to token
#: matching silently dropped every inflected form — "Investments" is a very
#: common YNAB account name, and it began importing as ON-BUDGET checking,
#: folding a brokerage balance straight into Ready to Assign. An explicit
#: suffix list restores that reach without the substring rule's false
#: positives ("invest" as substring also hits "investigation").
_STEM_SUFFIXES: tuple[str, ...] = ("", "s", "es", "ing", "ment", "ments")


def _matches(normalized: str, keywords: tuple[str, ...]) -> bool:
    for kw in keywords:
        for suffix in _STEM_SUFFIXES:
            if f" {kw}{suffix} " in normalized:
                return True
        if kw in _CONCATENATION_SAFE and kw in normalized:
            return True
    return False


def suggest_account_type(
    name: str, implied_balance: Decimal | None = None
) -> tuple[str, bool, bool]:
    """Guess (account_type, on_budget, needs_review) for a YNAB account name.

    `implied_balance` is the sum of the account's register rows. It is used only
    to pick asset vs liability for tracked-thing names, where the name alone is
    genuinely ambiguous.
    """
    normalized = _normalize_for_match(name)

    if _matches(normalized, _OFF_BUDGET_MARKERS):
        is_liability = implied_balance is not None and implied_balance < 0
        return ("other_liability" if is_liability else "other_asset"), False, True

    # Before the hint list, since the generic `loan` rule would otherwise claim
    # it. Mortgage and student still win — a name carrying both words is
    # describing the more specific thing.
    if (
        _matches(normalized, ("loan",))
        and _matches(normalized, _VEHICLE_WORDS)
        and not _matches(normalized, ("mortgage", "student"))
    ):
        return "auto_loan", False, False

    for keywords, account_type, on_budget in _TYPE_HINTS:
        if _matches(normalized, keywords):
            return account_type, on_budget, False

    if _matches(normalized, _TRACKED_HINTS):
        is_liability = implied_balance is not None and implied_balance < 0
        # Off budget either way; the side is a suggestion worth confirming.
        return ("other_liability" if is_liability else "other_asset"), False, True

    # Unrecognised. `checking` stays the convenient default, but the caller is
    # told not to trust it — silently importing an unknown account as on-budget
    # is exactly how a tracked account corrupts to_be_assigned.
    return "checking", True, True


#: How many leading tokens may form a related-account group.
#:
#: One is too coarse and two is the natural size of a thing's name: "Employer
#: A", "Union Ridge", "Cedar Grove", "Vehicle A". At one token the two
#: employers in a real export merge into a nine-account pile; unbounded, a
#: six-account employer shatters into "Employer A ESPP", "Employer A HSA" and
#: a remainder, which is grouping by product line rather than by the thing the
#: user recognises.
_RELATED_GROUP_MAX_TOKENS = 2


def _tokens_preserving_case(name: str) -> list[str]:
    """Same split as `_normalize_for_match`, with the original casing kept.

    Aligns token-for-token with the normalized form, so a group matched on
    "brightpath hsa" can be labelled from the source as "Brightpath HSA"
    rather than title-cased into "Brightpath Hsa"."""
    return [t for t in re.split(r"[^A-Za-z0-9]+", name) if t]


def assign_related_groups(names: Sequence[str]) -> dict[str, str | None]:
    """Group accounts sharing a leading name fragment: name → group label.

    **Related, never duplicate, and never a merge suggestion.** Measured on a
    real export, `rapidfuzz.token_set_ratio` returns 100 for "vehicle a" vs
    "vehicle a loan", "redwood" vs "redwood cc" and "harborstone" vs
    "harborstone savings" — every pair a legitimately distinct account. Acting
    on similarity here would tell someone to destroy real data. A shared
    leading fragment says only "these are probably about the same thing, look
    at them together": an institution's accounts, or an asset and the debt
    secured against it. Comparing those balances is exactly how a house typed
    as a mortgage gets caught.

    Longest shared prefix wins within the cap, so "Vehicle A" pairs with
    "Vehicle A Loan" rather than landing in a bucket with "Vehicle B".
    """
    tokens = {name: _normalize_for_match(name).split() for name in names}
    prefix_members: dict[tuple[str, ...], list[str]] = {}
    for name, toks in tokens.items():
        for k in range(1, min(len(toks), _RELATED_GROUP_MAX_TOKENS) + 1):
            prefix_members.setdefault(tuple(toks[:k]), []).append(name)

    groups: dict[str, str | None] = {}
    for name, toks in tokens.items():
        best: tuple[str, ...] | None = None
        for k in range(min(len(toks), _RELATED_GROUP_MAX_TOKENS), 0, -1):
            prefix = tuple(toks[:k])
            if len(prefix_members[prefix]) > 1:
                best = prefix
                break
        if best is None:
            groups[name] = None
            continue
        # Label from whichever member spells it out, so acronyms survive.
        source = min(prefix_members[best])
        groups[name] = " ".join(_tokens_preserving_case(source)[: len(best)])
    return groups


@dataclass(frozen=True)
class ExportedAccount:
    """What an `Accounts.csv` member says about one account.

    Only IGAB's own export writes that file, and it writes the account's real
    stored type — not a guess. That is why this tier clears `needs_review`
    while the remembered tier does not.
    """

    account_type: str
    on_budget: bool
    is_closed: bool = False


@dataclass(frozen=True)
class RememberedChoice:
    """What this person chose the last time they imported this account name.

    A record of a keystroke, not a fact about the account — and the keystroke
    may have been a pre-filled default nobody looked at. It is trusted to
    pre-fill the form and never to silence a warning about it.
    """

    account_type: str
    on_budget: bool
    skip: bool
    close: bool


@dataclass(frozen=True)
class AccountSuggestion:
    account_type: str
    on_budget: bool
    skip: bool
    close: bool
    needs_review: bool
    #: Where `account_type`/`on_budget` came from — NOT the disposition, which
    #: follows its own precedence (see `resolve_account_suggestion`). The two
    #: genuinely differ: an IGAB export states the type of an account it also
    #: knows nothing about wanting skipped.
    source: Literal["export", "remembered", "heuristic"]


def resolve_account_suggestion(
    name: str,
    implied_balance: Decimal | None = None,
    *,
    from_export: ExportedAccount | None = None,
    remembered: RememberedChoice | None = None,
) -> AccountSuggestion:
    """The one ladder from the three sources to what the mapping step shows.

    **Two ladders, not one.** The export knows what an account *is*; only the
    person knows what they want done with it *this time*:

    ==========================  ==========================================
    ``account_type``,           Accounts.csv → remembered → the name
    ``on_budget``
    ``skip``, ``close``         remembered → Accounts.csv ``Closed`` → keep
    ==========================  ==========================================

    Collapsing them gets one case wrong: an IGAB export carries an
    `Accounts.csv` row for *every* account it contains, so a single ladder
    would let the export outrank a remembered `skip` — and someone who said
    "leave this one out" twice would get it imported on the third try.

    **Memory never clears `needs_review`.** "We could not read this name" stays
    true no matter how many times the form has been submitted with a guess
    left untouched, and getting `on_budget` wrong silently corrupts
    to_be_assigned for the whole budget. The export does clear it: it is
    stating the type, not guessing at it.
    """
    guess_type, guess_on_budget, guess_needs_review = suggest_account_type(name, implied_balance)

    # A remembered type from before an account-type key was renamed or removed
    # would render the picker with no matching option — the browser shows the
    # first one while the form still holds the unknown string, so the person
    # imports `checking` believing they chose otherwise. Drop it and guess.
    usable = (
        remembered if remembered and remembered.account_type in BUILTIN_ACCOUNT_TYPE_KEYS else None
    )

    if from_export is not None:
        account_type, on_budget = from_export.account_type, from_export.on_budget
        source: Literal["export", "remembered", "heuristic"] = "export"
    elif usable is not None:
        account_type, on_budget = usable.account_type, usable.on_budget
        source = "remembered"
    else:
        account_type, on_budget = guess_type, guess_on_budget
        source = "heuristic"

    if usable is not None:
        skip, close = usable.skip, usable.close and not usable.skip
    elif from_export is not None:
        skip, close = False, from_export.is_closed
    else:
        skip, close = False, False

    return AccountSuggestion(
        account_type=account_type,
        on_budget=on_budget,
        skip=skip,
        close=close,
        needs_review=from_export is None and guess_needs_review,
        source=source,
    )
