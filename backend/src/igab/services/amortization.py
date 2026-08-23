"""Pure amortization math — no I/O, Decimal end-to-end, cent-quantized.

Every step quantizes to cents, and the final-payment clamp guarantees that
whenever a schedule pays off, the principal column sums to the starting
balance EXACTLY — zero cent drift. The test suite pins this invariant.

Compounding is MONTHLY by design throughout. The liabilities table carries a
dormant `compounding` column, but no API accepts it and no math reads it —
daily-vs-monthly differences are pennies at consumer rates, not worth the
extra test surface.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from igab.domain.dates import add_months

ZERO = Decimal("0")
CENT = Decimal("0.01")

# 50 years of monthly payments — far beyond any real consumer debt; a
# schedule still open after this is reported as never paying off.
DEFAULT_CAP_MONTHS = 600


def quantize_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)


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


def _month_diff(start: date, end: date) -> int:
    return (end.year * 12 + end.month) - (start.year * 12 + start.month)


def amortization_schedule_with_promo(
    balance: Decimal,
    annual_rate: Decimal,
    payment: Decimal,
    start_date: date,
    promo_end_date: date,
    cap_months: int = DEFAULT_CAP_MONTHS,
) -> AmortizationResult:
    """Fixed-payment schedule for promotional financing: 0% interest through
    `promo_end_date`, `annual_rate` afterwards.

    Composed from two `amortization_schedule` runs so the pinned exactness
    invariant (principal sums to the starting balance, zero cent drift)
    carries over untouched.
    """
    zero_phase = amortization_schedule(balance, ZERO, payment, start_date, cap_months)
    promo_schedule = [m for m in zero_phase.schedule if m.date <= promo_end_date]

    if promo_schedule and promo_schedule[-1].balance <= ZERO:
        return AmortizationResult(
            schedule=promo_schedule,
            never_pays_off=False,
            payoff_date=promo_schedule[-1].date,
            total_interest=ZERO,
        )
    if not promo_schedule and zero_phase.never_pays_off and payment <= ZERO:
        return zero_phase

    remaining = promo_schedule[-1].balance if promo_schedule else balance
    anchor = add_months(start_date, len(promo_schedule))
    post = amortization_schedule(
        remaining, annual_rate, payment, anchor, max(1, cap_months - len(promo_schedule))
    )
    offset = len(promo_schedule)
    combined = promo_schedule + [
        AmortizationMonth(
            month_index=offset + m.month_index,
            date=m.date,
            payment=m.payment,
            principal_paid=m.principal_paid,
            interest_paid=m.interest_paid,
            balance=m.balance,
        )
        for m in post.schedule
    ]
    return AmortizationResult(
        schedule=combined,
        never_pays_off=post.never_pays_off,
        payoff_date=post.payoff_date,
        total_interest=post.total_interest,
    )


@dataclass(frozen=True)
class PromoOutlook:
    """Where a promotional balance stands when the promo window closes."""

    months_until_promo_end: int
    balance_at_promo_end_minimum: Decimal
    balance_at_promo_end_live: Decimal | None  # None without payment history
    # At the best pace we know (live when available, else the minimum)
    clears_before_promo: bool
    # Retroactive interest a deferred-interest deal could charge if the
    # balance survives the deadline. An ESTIMATE — retailer accrual rules
    # vary — accrued monthly on the declining balance at the contract rate,
    # plus the already-elapsed months since origination on the original
    # principal. None when the promo isn't deferred-interest.
    deferred_interest_estimate: Decimal | None


def _balance_at(
    balance: Decimal, payment: Decimal, start_date: date, promo_end_date: date
) -> Decimal:
    """Remaining balance after every 0%-window payment through promo_end_date."""
    remaining = balance
    for m in amortization_schedule(balance, ZERO, payment, start_date).schedule:
        if m.date > promo_end_date:
            break
        remaining = m.balance
    return remaining


def promo_outlook(
    balance: Decimal,
    annual_rate: Decimal,
    minimum_payment: Decimal,
    average_payment: Decimal | None,
    as_of: date,
    promo_end_date: date,
    deferred_interest: bool,
    origination_date: date | None = None,
    original_principal: Decimal | None = None,
) -> PromoOutlook:
    months_left = max(0, _month_diff(as_of, promo_end_date))
    bal_min = _balance_at(balance, minimum_payment, as_of, promo_end_date)
    bal_live = (
        _balance_at(balance, average_payment, as_of, promo_end_date)
        if average_payment is not None and average_payment > ZERO
        else None
    )
    effective_end_balance = bal_live if bal_live is not None else bal_min

    deferred_estimate: Decimal | None = None
    if deferred_interest:
        monthly_rate = annual_rate / Decimal("100") / Decimal("12")
        estimate = ZERO
        if origination_date is not None:
            elapsed = max(0, _month_diff(origination_date, as_of))
            basis = original_principal if original_principal is not None else balance
            estimate += basis * monthly_rate * elapsed
        pace = (
            average_payment
            if average_payment is not None and average_payment > ZERO
            else minimum_payment
        )
        remaining = balance
        for m in amortization_schedule(balance, ZERO, pace, as_of).schedule:
            if m.date > promo_end_date:
                break
            estimate += remaining * monthly_rate
            remaining = m.balance
        deferred_estimate = quantize_cents(estimate)

    return PromoOutlook(
        months_until_promo_end=months_left,
        balance_at_promo_end_minimum=bal_min,
        balance_at_promo_end_live=bal_live,
        clears_before_promo=effective_end_balance <= ZERO,
        deferred_interest_estimate=deferred_estimate,
    )


@dataclass(frozen=True)
class LiveProjection:
    """Payoff projection from actual payment velocity, not the contract."""

    payoff_date: date | None
    never_pays_off: bool
    average_payment: Decimal


def average_recent_payment(recent_payments: list[Decimal]) -> Decimal | None:
    """Mean of the months that saw a payment, or None below two of them.

    One payment is an event, not a pace, so two is the floor everywhere this
    average is used. Split out from `project_payoff` because the average is
    observed history: it stays reportable when the contract terms a projection
    needs are missing.
    """
    positive = [p for p in recent_payments if p > ZERO]
    if len(positive) < 2:
        return None
    return quantize_cents(sum(positive, ZERO) / len(positive))


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
    average = average_recent_payment(recent_payments)
    if average is None:
        return None
    result = amortization_schedule(balance, annual_rate, average, as_of)
    return LiveProjection(
        payoff_date=result.payoff_date,
        never_pays_off=result.never_pays_off,
        average_payment=average,
    )
