"""Putting a bank feed into IGAB's frame, once, before anything reads it.

The rule itself is pure and lives in `domain/bank_frame.py`. This is the
wiring: it needs the accounts (for their classification and their remembered
frame) and the repository (to remember a frame the first time it is decided),
which is exactly why it is not in the domain module.

**Why it sits at this boundary and nowhere else.** The feed is read by the
matcher, the anchor, the drift check and the run record. Normalising in any
of them means normalising in all four, and the one that gets missed is the
next bug — that is precisely how the original defect composed: five places
each doing something defensible with a sign nobody owned.

The SimpleFIN client stays verbatim on purpose. It has no account, so it
cannot know a classification; making it guess would put the rule in the one
layer that lacks the input to apply it.
"""

import logging
from dataclasses import replace
from decimal import Decimal

from igab.db.models import Account
from igab.domain.bank_frame import LENDER, Frame, detect_frame, normalise, resolve_frame
from igab.integrations.simplefin.client import SimpleFINFeed
from igab.repositories.account_repo import AccountRepository

logger = logging.getLogger(__name__)


async def normalise_feed(
    account_repo: AccountRepository,
    targets: list[Account],
    feed: SimpleFINFeed,
) -> tuple[SimpleFINFeed, dict[str, Frame]]:
    """`feed` with every lender-frame account's figures flipped into IGAB's.

    Returns the rewritten feed and the frame decided for each SimpleFIN
    account id, so the caller can log what it did.

    A frame newly decided here is persisted immediately: the account's own
    row is the memory that stops an overpaid card being re-read as a change
    of convention next month.
    """
    frames: dict[str, Frame] = {}
    for account in targets:
        sf_id = account.simplefin_account_id
        if not sf_id:
            continue
        detected = detect_frame(account.classification, feed.balances.get(sf_id))
        frame = resolve_frame(_stored_frame(account), detected)
        frames[sf_id] = frame
        if account.simplefin_sign_frame is None and detected is not None:
            await account_repo.update(account.id, simplefin_sign_frame=detected)
            # Keep the in-memory object in step: `targets` is read again
            # further down the same sync.
            account.simplefin_sign_frame = detected
            if detected == LENDER:
                logger.info(
                    "simplefin: %s reports debts as positive — flipping signs on the way in",
                    account.name,
                )

    if not any(frame == LENDER for frame in frames.values()):
        return feed, frames

    balances = {
        sf_id: normalise(frames.get(sf_id, "ledger"), value)
        for sf_id, value in feed.balances.items()
    }
    transactions = [_normalised_row(row, frames) for row in feed.transactions]
    return replace(feed, transactions=transactions, balances=balances), frames


def _stored_frame(account: Account) -> Frame | None:
    """The remembered frame, ignoring a value the column should never hold.

    A string column cannot promise its own vocabulary; an unrecognised value
    is treated as "never decided" rather than crashing a sync.
    """
    stored = account.simplefin_sign_frame
    return stored if stored in ("ledger", "lender") else None  # type: ignore[return-value]


def _normalised_row(row: dict, frames: dict[str, Frame]) -> dict:
    """One feed row with its amount in IGAB's frame.

    A copy, never an edit in place: the raw feed is also what the run record
    and the rate-limit accounting were handed, and a mutating pass would
    change figures those had already read.
    """
    frame = frames.get(row.get("account_id") or "")
    if frame != LENDER:
        return row
    raw = row.get("amount")
    if raw is None:
        return row
    try:
        flipped = normalise(frame, Decimal(str(raw)))
    except (ArithmeticError, ValueError, TypeError):
        # A malformed amount is the import path's problem to report, not
        # this one's; hand it on untouched.
        return row
    return {**row, "amount": str(flipped)}
