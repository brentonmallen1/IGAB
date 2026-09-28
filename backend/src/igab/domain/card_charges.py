"""Is this card row interest or a fee the issuer charged?

Pure, so it is one table test away from being wrong in either direction. Read
by `TransactionService.create` as the last auto-filing fallback: a new outflow
on a card, with nothing from payee history or the payee's default, whose name
says it is interest or a fee goes to the budget's Interest & fees envelope
(`services/card_payment.CARD_INTEREST_KEY`). After the first one, payee
history takes over like any other payee.

A deliberate phrase set, not a word list. `payee_names.GENERIC_BANK_WORDS`
drops "interest", "fee" and "charge" for the opposite reason — they say
nothing about WHICH merchant a row is — so it cannot tell "Late fee" from
"Fee Fi Fo Fum Bakery", and neither can a bare "fee" match. Every phrase here
is something an issuer writes and a merchant does not: "interest charge",
"late fee", "annual fee". A payment ("Online payment, thank you"), a refund or
a merchant with "Fee" in its name matches none of them.
"""

import re

#: Phrases an issuer uses for interest and its own fees. Matched as whole
#: words, case-insensitively, anywhere in the name — banks prefix and suffix
#: them freely ("INTEREST CHARGE ON PURCHASES", "LATE FEE - MAR").
_PHRASES: tuple[str, ...] = (
    # Interest
    r"interest charges?",
    r"interest charged",
    r"purchase interest",
    r"interest on purchases",
    r"cash advance interest",
    r"finance charges?",
    # The issuer's own fees
    r"late (?:payment )?fee",
    r"annual (?:membership )?fee",
    r"membership fee",
    r"foreign (?:transaction |exchange |currency )?fee",
    r"cash advance fee",
    r"returned (?:payment |check )?fee",
    r"over[- ]?(?:the[- ])?limit fee",
)

_PATTERN = re.compile(r"\b(?:" + "|".join(_PHRASES) + r")\b", re.IGNORECASE)


def is_interest_or_fee(name: str | None) -> bool:
    """Does this payee (or bank description) name card interest or a card fee?"""
    if not name:
        return False
    # Collapse the separators banks use between words, so "LATE_FEE" and
    # "Late  fee" read as the phrase they are.
    normalized = re.sub(r"[\s_]+", " ", name)
    return _PATTERN.search(normalized) is not None
