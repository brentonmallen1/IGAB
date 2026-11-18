"""Whether a receipt's read is plausible enough to trust — pure.

A model reads a receipt with confidence 1.0 and still gets the two fields
that matter wrong: a warehouse-club till prints its date and its TOTAL bar
in reverse video, and a vision model read the date 2½ years back and the
total with its cents dropped, three runs out of three (reported 2026-11-17).
Nothing here tries to read the receipt better. These rules say when the read
contradicts itself or the calendar, so the review can point at the field
instead of showing a confident number.

Each check names the draft field a person should look at — ``"date"`` or
``"amount"`` — and any check caps the model's confidence: a read that failed
one is not 100% sure of anything.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

#: How far back a receipt's date may fall before the read is treated as a
#: misread. A scan is almost always days old, not months; a date beyond
#: this is replaced by today and flagged.
RECEIPT_DATE_WINDOW_DAYS = 60
#: How far ahead a read date may fall: one day of slack for the time zone
#: between the till (or the person describing) and the server.
DATE_FUTURE_SLACK_DAYS = 1
#: How much more the total may be than its line items add up to, as a
#: fraction of that sum: sales tax a receipt prints as a total line rather
#: than an item. Generous on purpose — no US combined rate reaches it — so
#: a flag means the items and the total disagree, not that tax was high.
#: There is no slack the other way: items adding up to MORE than the total
#: is a discount read as a charge, or a reward left out.
LINE_ITEM_TAX_TOLERANCE = Decimal("0.12")
#: How far a model's own arithmetic may be off, either way, in currency —
#: slack for the MODEL, never for the ledger (see domain/splits.py).
MODEL_ROUNDING_SLACK = Decimal("0.01")
#: The highest confidence a read that failed any check may carry.
CHECKED_CONFIDENCE_CAP = 0.5

DATE = "date"
AMOUNT = "amount"


@dataclass(frozen=True)
class CheckedDate:
    #: The date the draft uses.
    date: date
    #: The date the receipt was read as, when it fell outside the window and
    #: `date` is today instead — what the review names. None when it stood.
    read_as: date | None


def checked_receipt_date(read: date | None, today: date) -> CheckedDate:
    """A receipt date inside the plausible window stands; one outside it
    (too old, or past tomorrow) becomes today, remembering what was read.
    No date read at all is today with nothing to flag — receipts that print
    none exist, and today is the right guess for a fresh scan."""
    if read is None:
        return CheckedDate(date=today, read_as=None)
    earliest = today - timedelta(days=RECEIPT_DATE_WINDOW_DAYS)
    latest = today + timedelta(days=DATE_FUTURE_SLACK_DAYS)
    if earliest <= read <= latest:
        return CheckedDate(date=read, read_as=None)
    return CheckedDate(date=today, read_as=read)


def tender_disagrees(total: Decimal, tender: Decimal | None) -> bool:
    """The payment line charged something other than the total. Both are
    the amount paid, so they agree to the cent or one of them is misread.
    No payment line (cash, or none printed) checks nothing."""
    if tender is None:
        return False
    return tender.copy_abs() != total.copy_abs()


def line_items_disagree(total: Decimal, line_amounts: Sequence[Decimal]) -> bool:
    """The items, discounts negative, do not add up to the total within
    the tax tolerance. No items read checks nothing."""
    if not line_amounts:
        return False
    items = sum(line_amounts, Decimal("0")).copy_abs()
    paid = total.copy_abs()
    if items > paid + MODEL_ROUNDING_SLACK:
        return True
    return paid > items * (1 + LINE_ITEM_TAX_TOLERANCE) + MODEL_ROUNDING_SLACK


def capped_confidence(confidence: float, checks: Sequence[str]) -> float:
    """The model's confidence, held at `CHECKED_CONFIDENCE_CAP` when any
    field failed a check."""
    return min(confidence, CHECKED_CONFIDENCE_CAP) if checks else confidence
