"""Which way round a bank reports a debt.

A lender reports a loan the way a lender thinks about it: the balance is a
positive amount **owed**, and a payment is negative because it reduces what
you owe. IGAB holds the opposite convention: a liability's ledger is negative,
and a payment is an inflow that moves it toward zero. Both are internally
consistent; they are simply two frames for the same money.

Nothing reconciled the two, and the first sync of a mortgage composed five
defensible steps into a silent inversion: the reported balance was taken
verbatim, every payment already in the register failed to match its
sign-flipped twin and was re-created, the opening anchor closed a gap that
was the whole balance *twice*, and the liability page's `max(0, -ledger)`
clamp turned the resulting positive ledger into a confident "Paid off" on a
seven-figure loan. Net worth counted the mortgage as an asset.

The fix has to live at ONE boundary. Normalising downstream means normalising
in the matcher, the anchor, the drift check and the run record — four places,
and the one that gets missed is the bug.

**Detection happens once per account and is then persisted.** This is the part
that is easy to get wrong: a card CAN legitimately hold a positive ledger
(you overpaid it) and a loan CAN legitimately report a negative balance to its
servicer (an escrow overage). If the frame were re-detected every sync, those
ordinary situations would flip the account's sign halfway through its life.
The bank's convention is a property of the institution, not of this month's
balance, so it is decided from the first decisive observation and kept.

Pure: takes the classification and the figures, reads nothing.
"""

from decimal import Decimal
from typing import Literal

#: How a feed expresses a debt.
#:
#: ``ledger`` — IGAB's own frame: a debt is negative, a payment is an inflow.
#: An asset account is always this frame; so is a lender that reports debts
#: as negative numbers.
#:
#: ``lender`` — the borrower's-statement frame: a debt is positive, a payment
#: is negative. Amounts and the balance are negated on the way in.
Frame = Literal["ledger", "lender"]

LEDGER: Frame = "ledger"
LENDER: Frame = "lender"

ZERO = Decimal("0")

#: Mirrors `services.liability_service.LIABILITY_CLASSIFICATION`. Imported
#: from there would make this module depend on a service; the value is a
#: column's vocabulary, and `test_bank_frame.py` pins the two together.
LIABILITY = "liability"


def detect_frame(classification: str, reported_balance: Decimal | None) -> Frame | None:
    """The frame this feed is speaking, or None when it cannot be told yet.

    An asset is never ambiguous: a checking account holds a positive balance
    in both frames, so there is nothing to flip.

    For a liability, the sign of the reported balance IS the tell — a
    servicer reporting ``+248,900`` means "you owe this much", and no ledger
    frame would express a debt that way.

    None means *undecidable this run*, not "ledger". A balance of zero, or a
    feed that reported none at all, says nothing about the institution's
    convention, and guessing on a zero balance would pin the wrong frame for
    the life of the account on the one sync where the evidence is absent.
    """
    if classification != LIABILITY:
        return LEDGER
    if reported_balance is None or reported_balance == ZERO:
        return None
    return LENDER if reported_balance > ZERO else LEDGER


def resolve_frame(persisted: Frame | None, detected: Frame | None) -> Frame:
    """The frame to sync with: what we already decided, else what we can see.

    **Persisted always wins.** Once an account's institution has told us which
    way round it speaks, an overpaid card or a month of escrow overage must
    not be read as the institution changing its convention.

    Falls back to ``ledger`` when nothing is known, which is the no-op frame:
    an account whose balance we have never seen is synced verbatim, exactly as
    every account was before this module existed.
    """
    if persisted is not None:
        return persisted
    if detected is not None:
        return detected
    return LEDGER


def normalise(frame: Frame, value: Decimal) -> Decimal:
    """`value` expressed in IGAB's frame.

    Applied to the reported balance AND to every row amount for that account,
    from the same frame, so the two can never disagree — which is what made
    the anchor close a doubled gap.
    """
    return -value if frame == LENDER else value


def describe_frame(account_name: str, frame: Frame) -> str:
    """One clause for a sync log line."""
    if frame == LENDER:
        return f"{account_name}: bank reports debts as positive — signs flipped on the way in"
    return f"{account_name}: bank reports in the ledger's own frame"
