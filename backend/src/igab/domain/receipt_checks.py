"""Whether a receipt's read is plausible enough to trust — pure.

A model reads a receipt with confidence 1.0 and still gets the two fields
that matter wrong: a warehouse-club till prints its date and its TOTAL bar
in reverse video, and a vision model read the date 2½ years back and the
total with its cents dropped, three runs out of three (reported 2026-11-17).
Nothing here tries to read the receipt better. These rules say when the read
contradicts itself or the calendar, so the review can point at the field
instead of showing a confident number.

Each check names the draft field a person should look at (a `ReceiptCheck`),
and any check caps the model's confidence: a read that failed one is not
100% sure of anything.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from igab.domain.money import model_cents

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
#: How many identical line items in a row mean the model is looping, not
#: reading. A till prints three of the same yogurt on three lines; a model
#: stuck on one item writes it until something stops it (reported 2026-11-18:
#: one item, hundreds of times, on a ~53-item receipt). Eight is past any
#: honest run and still stops a loop within a few hundred tokens.
LOOPING_RUN = 8


class ReceiptCheck(StrEnum):
    """The draft field a failed check points at — the frontend's
    `AIJobDraftCheck` union spells the same values."""

    DATE = "date"
    AMOUNT = "amount"
    #: The receipt was too long to itemize: the reply was cut short or
    #: looped, so payee, total and date were kept and no split is offered.
    ITEMS = "items"


def past_tomorrow(read: date, today: date) -> bool:
    """A read date later than tomorrow: a misread, since what was read
    already happened — a receipt and a description alike."""
    return read > today + timedelta(days=DATE_FUTURE_SLACK_DAYS)


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
    if read < today - timedelta(days=RECEIPT_DATE_WINDOW_DAYS) or past_tomorrow(read, today):
        return CheckedDate(date=today, read_as=read)
    return CheckedDate(date=read, read_as=None)


def tender_disagrees(total: Decimal, tender: Decimal | None) -> bool:
    """The payment line charged something other than the total. Both are
    the amount paid, so they agree to the cent or one of them is misread.
    No payment line (cash, or none printed) checks nothing."""
    if tender is None:
        return False
    return tender.copy_abs() != total.copy_abs()


def line_items_mismatch(total: Decimal, line_amounts: Sequence[Decimal]) -> Decimal | None:
    """What the items add up to (discounts negative) when that disagrees
    with the total beyond the tax tolerance, for the review to name; None
    when they agree. No items read checks nothing."""
    if not line_amounts:
        return None
    line_sum = sum(line_amounts, Decimal("0"))
    items = line_sum.copy_abs()
    paid = total.copy_abs()
    over = items > paid + MODEL_ROUNDING_SLACK
    under = paid > items * (1 + LINE_ITEM_TAX_TOLERANCE) + MODEL_ROUNDING_SLACK
    return line_sum if over or under else None


def capped_confidence(confidence: float, checks: Sequence[ReceiptCheck]) -> float:
    """The model's confidence, held at `CHECKED_CONFIDENCE_CAP` when any
    field failed a check."""
    return min(confidence, CHECKED_CONFIDENCE_CAP) if checks else confidence


_DIGITS = re.compile(r"\d+")


def _loop_key(item: object) -> tuple[object, object] | None:
    """What makes two line items "the same" to the loop check. Digits are
    collapsed: a model also loops by counting — the same item with its code
    going up by one each time (reported 2026-11-18) — and those never
    compared equal. The amount still has to match, so a till printing one
    price on differently named items is not a loop."""
    if not isinstance(item, dict):
        return None
    description = item.get("description")
    if isinstance(description, str):
        description = _DIGITS.sub("#", description)
    return (description, item.get("amount"))


def looping_items(items: Sequence[object]) -> bool:
    """`LOOPING_RUN` line items in a row that differ at most in their digits:
    the model repeating one item, not a receipt that lists it. Anything that
    is not an item object breaks a run."""
    run = 0
    previous: tuple[object, object] | None = None
    for item in items:
        key = _loop_key(item)
        run = run + 1 if key is not None and key == previous else 1
        previous = key
        if key is not None and run >= LOOPING_RUN:
            return True
    return False


#: Line items adding up to more than this many times the total cannot be the
#: receipt: the list has run away, whatever each line says. Deliberately far
#: above any real discount, because stopping costs the split.
RUNAWAY_ITEMS_FACTOR = 2


def items_overshoot(items: Sequence[object], total: object) -> bool:
    """Whether the line items read so far already add up to far more than
    the total — a runaway list the repeat check has no pattern for."""
    paid = model_cents(total)
    if paid is None or paid <= 0:
        return False
    amounts = [model_cents(i.get("amount")) for i in items if isinstance(i, dict)]
    line_sum = sum((a for a in amounts if a is not None), Decimal("0"))
    return line_sum > paid * RUNAWAY_ITEMS_FACTOR


_WORDS = re.compile(r"[a-z0-9]+")


def _words(text: str | None) -> frozenset[str]:
    return frozenset(_WORDS.findall((text or "").casefold()))


def named_for_payee(category: str, payee: str | None) -> bool:
    """Whether a category carries the store's own name: every word of one is
    in the other ("Northwind Club" for "Northwind Club Wholesale").

    Such a category is usually the store's membership or fee, kept as a
    sinking fund — and a model matches a receipt to it on the name alone,
    whatever was bought (reported 2026-11-18: a full grocery shop filed to
    the yearly-fee envelope while every line item said Groceries). A match
    is a reason to ask for a second opinion, not a verdict."""
    category_words, payee_words = _words(category), _words(payee)
    if not category_words or not payee_words:
        return False
    return category_words <= payee_words or payee_words <= category_words


#: Words a model uses for a line that stands for the whole receipt.
_SUMMARY_WORDS = frozenset(
    "various items item misc miscellaneous assorted groceries grocery merchandise goods"
    " purchase purchases products multiple several general sundry sundries food other"
    " and total".split()
)


def summary_line(items: Sequence[object], total: Decimal) -> bool:
    """One line item, for the whole total, described in general words
    ("various items"): the model declined to itemize. Not a one-item
    receipt — and it made the line-item check pass trivially on a read that
    was wrong everywhere else (a sideways photo, reported 2026-11-18)."""
    if len(items) != 1 or not isinstance(items[0], dict):
        return False
    amount = model_cents(items[0].get("amount"))
    if amount is None or (amount.copy_abs() - total.copy_abs()).copy_abs() > MODEL_ROUNDING_SLACK:
        return False
    words = _words(str(items[0].get("description") or ""))
    return bool(words) and words <= _SUMMARY_WORDS
