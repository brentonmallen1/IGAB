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
from decimal import ROUND_CEILING, Decimal
from typing import Literal

from igab.domain.dates import add_months
from igab.domain.minimum_payment import FIXED, MinimumPaymentRule, as_rule
from igab.domain.money import quantize_cents

ZERO = Decimal("0")
CENT = Decimal("0.01")

# 50 years of monthly payments — far beyond any real consumer debt; a
# schedule still open after this is reported as never paying off.
DEFAULT_CAP_MONTHS = 600


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


def _month_step(
    balance: Decimal, monthly_rate: Decimal, payment: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """One month: interest accrues, then the payment lands.

    Returns (interest, principal, new balance). `principal` is clamped to the
    balance — the final-payment clamp that keeps the principal column summing
    to the starting balance exactly — and may be NEGATIVE when the payment
    does not cover the month's interest, which is how a stalled debt grows.
    The single-debt schedule and the multi-debt cascade both step through
    this, so they cannot round a month differently.
    """
    interest = quantize_cents(balance * monthly_rate)
    principal = min(payment - interest, balance)
    return interest, principal, balance - principal


def amortization_schedule(
    balance: Decimal,
    annual_rate: Decimal,
    payment: Decimal | MinimumPaymentRule,
    start_date: date,
    cap_months: int = DEFAULT_CAP_MONTHS,
) -> AmortizationResult:
    """Project a monthly amortization schedule.

    `balance` is the amount owed (positive). Payments land monthly starting
    one month after `start_date`. `annual_rate` is a percentage (6.25 means
    6.25%/year), compounded monthly. A payment that doesn't exceed the
    month's interest can never retire the debt — reported honestly as
    `never_pays_off` rather than looping forever (same if `cap_months` is
    exceeded).

    `payment` may be a scalar or a :class:`MinimumPaymentRule`. A scalar is
    wrapped into a fixed rule, so this is one loop rather than two: a second,
    variable-payment schedule beside this one would be two implementations of
    amortization, and only one of them would be the tested one. The rule is
    asked for its due amount each month *after* interest is computed, because
    a "percent plus this month's interest" rule needs that figure.
    """
    if annual_rate < ZERO:
        raise ValueError("annual_rate must be non-negative")
    rule = as_rule(payment)
    if rule.kind == FIXED and (rule.amount or ZERO) < ZERO:
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
        # This month's interest first: a rule may be a slice of the balance
        # *plus* what the month charged.
        monthly_interest = quantize_cents(balance * monthly_rate)
        interest, principal, balance = _month_step(
            balance, monthly_rate, rule.due(balance, monthly_interest)
        )
        if principal <= ZERO:
            return AmortizationResult(
                schedule=schedule,
                never_pays_off=True,
                payoff_date=None,
                total_interest=total_interest,
            )
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


# ─── Several debts at once ────────────────────────────────────────────────────

CascadeOrder = Literal["avalanche", "snowball"]


@dataclass(frozen=True)
class CascadeDebt:
    key: str
    name: str
    balance: Decimal
    annual_rate: Decimal
    #: A scalar or a rule. A scalar is the rule it always was — see
    #: domain.minimum_payment.as_rule.
    minimum_payment: Decimal | MinimumPaymentRule


@dataclass(frozen=True)
class CascadeDebtResult:
    key: str
    name: str
    #: 1-based position in the attack order.
    order: int
    payoff_date: date | None
    #: Months until it closed; 0 when nothing was owed to begin with.
    months: int
    never_pays_off: bool
    total_interest: Decimal
    total_principal: Decimal


@dataclass(frozen=True)
class CascadeMonth:
    month_index: int
    date: date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    #: Everything still owed across every debt after this month.
    balance: Decimal
    #: Per debt, keyed by `CascadeDebt.key` — what a chart draws.
    balances: dict[str, Decimal]


@dataclass(frozen=True)
class CascadeResult:
    order: CascadeOrder
    debts: list[CascadeDebtResult]
    months: list[CascadeMonth]
    debt_free_date: date | None
    never_pays_off: bool
    total_interest: Decimal
    total_paid: Decimal


def cascade_order(debts: list[CascadeDebt], order: CascadeOrder) -> list[CascadeDebt]:
    """The attack order. Total orders, so ties are broken the same way every
    time: avalanche by rate, then the smaller balance, then name; snowball by
    balance, then the higher rate, then name. The key breaks any last tie."""
    if order == "avalanche":
        return sorted(debts, key=lambda d: (-d.annual_rate, d.balance, d.name, d.key))
    if order == "snowball":
        return sorted(debts, key=lambda d: (d.balance, -d.annual_rate, d.name, d.key))
    raise ValueError(f"unknown order {order!r}")


def payoff_cascade(
    debts: list[CascadeDebt],
    extra: Decimal,
    order: CascadeOrder,
    start_date: date,
    cap_months: int = DEFAULT_CAP_MONTHS,
    *,
    roll_freed: bool = True,
) -> CascadeResult:
    """Pay minimums on everything, throw `extra` at one debt, and when a debt
    clears roll its minimum into the next — the avalanche / snowball plan.

    Each month, in attack order: every open debt takes its minimum through
    `_month_step`; whatever a clamped final minimum did not need joins this
    month's pool alongside `extra` and the minimums freed by earlier closures;
    the pool then walks the attack order, clearing a debt and passing the
    remainder on within the same month. `roll_freed=False` is the honest
    "keep doing what you are doing" baseline: minimums only, nothing rolled.

    Same Decimal discipline as `amortization_schedule` — cents on entry, cents
    every step — so for every debt that closes the principal applied to it
    sums to its starting balance exactly.
    """
    if extra < ZERO:
        raise ValueError("extra must be non-negative")
    for d in debts:
        if d.annual_rate < ZERO:
            raise ValueError(f"{d.name}: annual_rate must be non-negative")
        rule = as_rule(d.minimum_payment)
        if rule.kind == FIXED and (rule.amount or ZERO) < ZERO:
            raise ValueError(f"{d.name}: minimum_payment must be non-negative")

    attack = cascade_order(debts, order)
    extra = quantize_cents(extra)
    balances = {d.key: quantize_cents(d.balance) for d in attack}
    rules = {d.key: as_rule(d.minimum_payment) for d in attack}
    # The payment each debt was consuming when it closed. A declining rule has
    # no single "its minimum", and re-evaluating one against a zero balance
    # would roll nothing forward — so the last amount actually asked for is
    # captured as it is charged.
    last_due = dict.fromkeys(balances, ZERO)
    rates = {d.key: d.annual_rate / Decimal("100") / Decimal("12") for d in attack}
    interest_total = dict.fromkeys(balances, ZERO)
    principal_total = dict.fromkeys(balances, ZERO)
    payoff: dict[str, date | None] = dict.fromkeys(balances)
    months_to = dict.fromkeys(balances, 0)

    open_keys: list[str] = []
    for d in attack:
        if balances[d.key] <= ZERO:
            # Nothing owed: paid as of today, and it frees nothing.
            balances[d.key] = ZERO
            payoff[d.key] = start_date
        else:
            open_keys.append(d.key)

    freed = ZERO
    months: list[CascadeMonth] = []
    stalled = False

    for m in range(1, cap_months + 1):
        if not open_keys:
            break
        pool = extra + freed
        month_interest = month_principal = month_paid = ZERO

        # 1. Minimums, in attack order.
        for d in attack:
            k = d.key
            if k not in open_keys:
                continue
            monthly_interest = quantize_cents(balances[k] * rates[k])
            due = rules[k].due(balances[k], monthly_interest)
            last_due[k] = due
            interest, principal, balances[k] = _month_step(balances[k], rates[k], due)
            paid = interest + principal
            pool += due - paid
            interest_total[k] += interest
            principal_total[k] += principal
            month_interest += interest
            month_principal += principal
            month_paid += paid

        # 2. The pool, in attack order — a cleared debt hands the rest on.
        for d in attack:
            if pool <= ZERO:
                break
            k = d.key
            if k not in open_keys or balances[k] <= ZERO:
                continue
            take = min(pool, balances[k])
            balances[k] -= take
            pool -= take
            principal_total[k] += take
            month_principal += take
            month_paid += take

        # 3. Closures. A minimum freed this month is in next month's pool.
        when = add_months(start_date, m)
        for d in attack:
            k = d.key
            if k in open_keys and balances[k] <= ZERO:
                balances[k] = ZERO
                payoff[k] = when
                months_to[k] = m
                open_keys.remove(k)
                if roll_freed:
                    freed += last_due[k]

        months.append(
            CascadeMonth(
                month_index=m,
                date=when,
                payment=month_paid,
                principal_paid=month_principal,
                interest_paid=month_interest,
                balance=sum(balances.values(), ZERO),
                balances=dict(balances),
            )
        )
        if month_principal <= ZERO:
            # Minimums under the interest and nothing in the pool: the debts
            # only grow from here. Reported, not looped.
            stalled = True
            break

    never = stalled or bool(open_keys)
    results = [
        CascadeDebtResult(
            key=d.key,
            name=d.name,
            order=i + 1,
            payoff_date=None if d.key in open_keys else payoff[d.key],
            months=months_to[d.key],
            never_pays_off=d.key in open_keys,
            total_interest=interest_total[d.key],
            total_principal=principal_total[d.key],
        )
        for i, d in enumerate(attack)
    ]
    return CascadeResult(
        order=order,
        debts=results,
        months=months,
        debt_free_date=None if never else (months[-1].date if months else start_date),
        never_pays_off=never,
        total_interest=sum((mo.interest_paid for mo in months), ZERO),
        total_paid=sum((mo.payment for mo in months), ZERO),
    )


# ─── Two small annuity helpers ───────────────────────────────────────────────


def level_payment(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """The fixed monthly payment that retires `principal` in `term_months`.

    The standard annuity formula, monthly compounding. Rounded UP to the
    cent, as lenders do: rounded to nearest, a 12-month loan leaves a few
    cents for a thirteenth payment, so the term the user asked for would not
    hold. The final payment is a few cents smaller instead. Published tables
    round to nearest and can read one cent lower.
    """
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    if principal < ZERO or annual_rate < ZERO:
        raise ValueError("principal and annual_rate must be non-negative")
    monthly_rate = annual_rate / Decimal("100") / Decimal("12")
    if monthly_rate == ZERO:
        exact = principal / term_months
    else:
        growth = (1 + monthly_rate) ** term_months
        exact = principal * monthly_rate * growth / (growth - 1)
    return exact.quantize(CENT, rounding=ROUND_CEILING)


def interest_over(
    balance: Decimal, annual_rate: Decimal, payment: Decimal | MinimumPaymentRule, months: int
) -> Decimal:
    """Interest charged across `months` of payments, paid off or not.

    `amortization_schedule` stops the moment a payment fails to cover the
    interest, which is right for a schedule and wrong for a comparison: a
    stalled debt keeps charging. This keeps counting, and stops early only
    once the balance is gone.

    Takes a rule for the same reason the schedule does — without it,
    pay-vs-save would compare a declining minimum against a fixed one and
    report a saving that is partly an artefact of the comparison.
    """
    if months < 0:
        raise ValueError("months must be non-negative")
    rule = as_rule(payment)
    monthly_rate = annual_rate / Decimal("100") / Decimal("12")
    balance = quantize_cents(balance)
    total = ZERO
    for _ in range(months):
        if balance <= ZERO:
            break
        monthly_interest = quantize_cents(balance * monthly_rate)
        interest, _principal, balance = _month_step(
            balance, monthly_rate, rule.due(balance, monthly_interest)
        )
        total += interest
    return total


def future_value_monthly(contribution: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    """What `months` end-of-month contributions grow to at `annual_rate`,
    compounding monthly and rounding to cents each month — a savings account,
    not a market projection."""
    if months < 0 or contribution < ZERO or annual_rate < ZERO:
        raise ValueError("months, contribution and annual_rate must be non-negative")
    monthly_rate = annual_rate / Decimal("100") / Decimal("12")
    balance = ZERO
    for _ in range(months):
        balance = quantize_cents(balance * (1 + monthly_rate)) + contribution
    return quantize_cents(balance)
