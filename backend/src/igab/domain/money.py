"""Money parsing and validation shared by API schemas and importers.

Postgres `Numeric` happily stores NaN — and a single NaN poisons every SUM
the app runs, silently breaking all balances. Every user-supplied amount goes
through `Money` (API) or `parse_csv_amount` (imports) so non-finite values,
absurd magnitudes, and sub-cent noise are rejected at the boundary.
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator

MAX_ABS_AMOUNT = Decimal("9999999999999")  # 10^13 — beyond any household ledger
MAX_DECIMAL_PLACES = 4  # matches the Numeric(19, 4) columns


def validate_money(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("amount must be a finite number")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -MAX_DECIMAL_PLACES:
        raise ValueError(f"amount supports at most {MAX_DECIMAL_PLACES} decimal places")
    if abs(value) > MAX_ABS_AMOUNT:
        raise ValueError("amount is out of range")
    return value


Money = Annotated[Decimal, AfterValidator(validate_money)]

_CURRENCY_CHARS = re.compile(r"[$€£¥\s]")


def parse_csv_amount(raw: str) -> Decimal:
    """Parse a CSV amount string exactly — never through float.

    Handles currency symbols, parentheses negatives, and thousands
    separators. Separator rules:
    - Both "." and "," present → the rightmost one is the decimal point.
    - Only "," present: comma groups of exactly three digits are thousands
      ("1,234" → 1234); a comma followed by 1–2 digits is an ambiguous
      European decimal and is REJECTED rather than silently corrupted.
    - Only "." present → decimal point.
    """
    cleaned = _CURRENCY_CHARS.sub("", raw.strip())
    if not cleaned:
        raise ValueError("empty amount")

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]

    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        # Rightmost separator is the decimal point; strip the other entirely.
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif has_comma:
        parts = cleaned.split(",")
        if all(len(p) == 3 for p in parts[1:]) and parts[0] and len(parts[0]) <= 3:
            cleaned = cleaned.replace(",", "")  # 1,234 / 12,345,678 → thousands
        else:
            raise ValueError(
                f"ambiguous amount '{raw.strip()}': use a dot as the decimal separator"
            )

    try:
        value = Decimal(cleaned)
    except InvalidOperation as e:
        raise ValueError(f"cannot parse amount '{raw.strip()}'") from e

    return validate_money(-value if negative else value)


CENT = Decimal("0.01")


def quantize_cents(amount: Decimal) -> Decimal:
    """Round to whole cents, banker's rounding.

    Twenty-three call sites wrote `quantize(Decimal("0.01"))` with no rounding
    argument, which takes the mode from the *global decimal context*. That is
    the same answer this gives — ROUND_HALF_EVEN is the default — but it is the
    right answer by accident: any code that set `getcontext().rounding` would
    silently change how money rounds across every report in the app, with
    nothing naming the convention to notice it had moved.

    Half-even rather than half-up because it is unbiased over many roundings:
    half-up drags a long column of figures upward, and these are summed.

    The exceptions are deliberate and named where they occur —
    `distribute_cover` rounds DOWN so a proposal can never exceed To Be
    Assigned, and `ai_draft_service` rounds a model's own arithmetic half-up
    before repairing it to sum exactly.
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)
