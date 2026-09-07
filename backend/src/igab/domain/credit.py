"""Card utilization: the one rule for "how much of the limit is in use".

Utilization is balance ÷ credit limit as a percent. Credit scoring models
weigh it heavily and the folk thresholds are 30% (noticeable) and 50%
(damaging); both live here so the liability page, the Guide checkup and any
future banner read the same numbers.
"""

from decimal import Decimal

#: Above this share of the limit, scoring models start to mark the card down.
UTILIZATION_HIGH = Decimal("30")
#: Above this, the effect is large enough to name as a finding of its own.
UTILIZATION_VERY_HIGH = Decimal("50")


def utilization_percent(balance: Decimal, credit_limit: Decimal | None) -> Decimal | None:
    """Balance as a percent of the limit, to one decimal. None without a
    usable limit; a negative balance (the issuer owes you) reads as 0."""
    if credit_limit is None or credit_limit <= 0:
        return None
    if balance <= 0:
        return Decimal("0.0")
    return (balance / credit_limit * 100).quantize(Decimal("0.1"))
