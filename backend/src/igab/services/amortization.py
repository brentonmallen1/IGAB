"""Pure amortization math — no I/O, Decimal end-to-end, cent-quantized.

Every step quantizes to cents, and the final-payment clamp guarantees that
whenever a schedule pays off, the principal column sums to the starting
balance EXACTLY — zero cent drift. The test suite pins this invariant.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")

# 50 years of monthly payments — far beyond any real consumer debt; a
# schedule still open after this is reported as never paying off.
DEFAULT_CAP_MONTHS = 600


def quantize_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)


def add_months(d: date, months: int) -> date:
    """Shift by whole months, clamping the day to the target month length."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class AmortizationMonth:
    month_index: int  # 1-based payment number
    date: date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    balance: Decimal  # remaining after this payment


@dataclass(frozen=True)
class AmortizationResult:
    schedule: list[AmortizationMonth]
    never_pays_off: bool
    payoff_date: date | None
    total_interest: Decimal


def amortization_schedule(
    balance: Decimal,
    annual_rate: Decimal,
    payment: Decimal,
    start_date: date,
    cap_months: int = DEFAULT_CAP_MONTHS,
) -> AmortizationResult:
    """Project a fixed-payment monthly amortization schedule.

    `balance` is the amount owed (positive). Payments land monthly starting
    one month after `start_date`. `annual_rate` is a percentage (6.25 means
    6.25%/year), compounded monthly. A payment that doesn't exceed the
    month's interest can never retire the debt — reported honestly as
    `never_pays_off` rather than looping forever (same if `cap_months` is
    exceeded).
    """
    if annual_rate < ZERO:
        raise ValueError("annual_rate must be non-negative")
    if payment < ZERO:
        raise ValueError("payment must be non-negative")

    balance = quantize_cents(balance)
    if balance <= ZERO:
        # Nothing owed: already paid off as of the start date.
        return AmortizationResult(
            schedule=[], never_pays_off=False, payoff_date=start_date, total_interest=ZERO
        )

    monthly_rate = annual_rate / Decimal("100") / Decimal("12")
    schedule: list[AmortizationMonth] = []
    total_interest = ZERO

    for month in range(1, cap_months + 1):
        interest = quantize_cents(balance * monthly_rate)
        if payment <= interest:
            return AmortizationResult(
                schedule=schedule,
                never_pays_off=True,
                payoff_date=None,
                total_interest=total_interest,
            )
        principal = min(payment - interest, balance)  # final-payment clamp
        balance -= principal
        total_interest += interest
        schedule.append(
            AmortizationMonth(
                month_index=month,
                date=add_months(start_date, month),
                payment=principal + interest,
                principal_paid=principal,
                interest_paid=interest,
                balance=balance,
            )
        )
        if balance <= ZERO:
            return AmortizationResult(
                schedule=schedule,
                never_pays_off=False,
                payoff_date=schedule[-1].date,
                total_interest=total_interest,
            )

    return AmortizationResult(
        schedule=schedule, never_pays_off=True, payoff_date=None, total_interest=total_interest
    )


@dataclass(frozen=True)
class LiveProjection:
    """Payoff projection from actual payment velocity, not the contract."""

    payoff_date: date | None
    never_pays_off: bool
    average_payment: Decimal


def project_payoff(
    balance: Decimal,
    annual_rate: Decimal,
    recent_payments: list[Decimal],
    as_of: date,
) -> LiveProjection | None:
    """Live payoff estimate from trailing actual payments.

    Returns None with fewer than two positive data points — the caller
    falls back to the contractual schedule rather than fabricating a date
    from insufficient history.
    """
    positive = [p for p in recent_payments if p > ZERO]
    if len(positive) < 2:
        return None
    average = quantize_cents(sum(positive, ZERO) / len(positive))
    result = amortization_schedule(balance, annual_rate, average, as_of)
    return LiveProjection(
        payoff_date=result.payoff_date,
        never_pays_off=result.never_pays_off,
        average_payment=average,
    )
