"""The scenario calculators, as the Tools tab presents them.

Presentation over `services/amortization.py`, which owns the arithmetic:
these functions decide what to compare and what to call the answer, never how
a month of interest is computed. Every figure here is one the app can show
its working for. There is no market-return projection and no tax modelling
anywhere in this module, on purpose — a savings rate is something the user
types in, labelled as a rate they can get today.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Literal

from igab.domain.dates import add_months
from igab.domain.money import quantize_cents
from igab.services.amortization import (
    DEFAULT_CAP_MONTHS,
    CascadeDebt,
    CascadeResult,
    amortization_schedule,
    future_value_monthly,
    interest_over,
    level_payment,
    payoff_cascade,
)

ZERO = Decimal("0")
CENT = Decimal("0.01")


# ── payoff plan ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PayoffPlan:
    as_of: date
    extra: Decimal
    avalanche: CascadeResult
    snowball: CascadeResult
    #: Minimums only, nothing rolled — what happens if nothing changes.
    minimums_only: CascadeResult


def payoff_plan(
    debts: list[CascadeDebt],
    extra: Decimal,
    as_of: date,
    cap_months: int = DEFAULT_CAP_MONTHS,
) -> PayoffPlan:
    return PayoffPlan(
        as_of=as_of,
        extra=quantize_cents(extra),
        avalanche=payoff_cascade(debts, extra, "avalanche", as_of, cap_months),
        snowball=payoff_cascade(debts, extra, "snowball", as_of, cap_months),
        minimums_only=payoff_cascade(debts, ZERO, "avalanche", as_of, cap_months, roll_freed=False),
    )


# ── pay it down, or save instead ─────────────────────────────────────────────


Favours = Literal["pay", "save", "even"]


@dataclass(frozen=True)
class PayVsSave:
    #: Months the minimum-only plan takes — the window both arms are measured over.
    horizon_months: int
    baseline_total_interest: Decimal
    baseline_never_pays_off: bool
    pay_months: int
    pay_payoff_date: date | None
    pay_total_interest: Decimal
    pay_never_pays_off: bool
    debt_interest_saved: Decimal
    months_sooner: int
    savings_contributed: Decimal
    savings_balance: Decimal
    savings_interest_earned: Decimal
    #: The savings rate at which the two arms tie. None when there is no
    #: horizon to measure over.
    breakeven_apy: Decimal | None
    favours: Favours


def _breakeven_apy(extra: Decimal, months: int, target_interest: Decimal) -> Decimal:
    """Bisect for the rate at which `months` of `extra` earn `target_interest`.

    Future value is monotonic in the rate, so this converges; to the basis
    point is plenty for a figure whose purpose is "roughly what would a
    savings account have to pay".
    """
    if target_interest <= ZERO or extra <= ZERO or months <= 0:
        return ZERO
    lo, hi = ZERO, Decimal("100")
    contributed = extra * months
    for _ in range(40):
        mid = (lo + hi) / 2
        earned = future_value_monthly(extra, mid, months) - contributed
        if earned < target_interest:
            lo = mid
        else:
            hi = mid
    # Up, not nearest: at the rate we name, saving at least ties.
    return hi.quantize(CENT, rounding=ROUND_CEILING)


def pay_vs_save(
    balance: Decimal,
    annual_rate: Decimal,
    minimum_payment: Decimal,
    extra: Decimal,
    savings_apy: Decimal,
    as_of: date,
    cap_months: int = DEFAULT_CAP_MONTHS,
) -> PayVsSave:
    """Put `extra` a month against the debt, or into savings at `savings_apy`?

    Both arms run over the months the minimum-only plan takes — or, when
    the minimum never clears the debt, the months paying extra takes. Paying
    saves the interest the baseline would have charged in that window; saving
    earns interest on the same money over it. The comparison is that simple,
    and says so.
    """
    if extra < ZERO or savings_apy < ZERO:
        raise ValueError("extra and savings_apy must be non-negative")
    extra = quantize_cents(extra)
    baseline = amortization_schedule(balance, annual_rate, minimum_payment, as_of, cap_months)
    pay = amortization_schedule(balance, annual_rate, minimum_payment + extra, as_of, cap_months)

    if not baseline.never_pays_off:
        horizon = len(baseline.schedule)
    elif not pay.never_pays_off:
        horizon = len(pay.schedule)
    else:
        horizon = cap_months

    # Both measured over the same window, and a stalled baseline keeps
    # charging rather than stopping where its schedule gave up.
    baseline_interest = interest_over(balance, annual_rate, minimum_payment, horizon)
    pay_interest = interest_over(balance, annual_rate, minimum_payment + extra, horizon)
    saved = baseline_interest - pay_interest
    sooner = len(baseline.schedule) - len(pay.schedule) if not baseline.never_pays_off else 0
    contributed = extra * horizon
    fv = future_value_monthly(extra, savings_apy, horizon)
    earned = fv - contributed
    breakeven = _breakeven_apy(extra, horizon, saved) if horizon > 0 else None

    if abs(saved - earned) < Decimal("0.01"):
        favours: Favours = "even"
    elif saved > earned:
        favours = "pay"
    else:
        favours = "save"

    return PayVsSave(
        horizon_months=horizon,
        baseline_total_interest=baseline_interest,
        baseline_never_pays_off=baseline.never_pays_off,
        pay_months=len(pay.schedule),
        pay_payoff_date=pay.payoff_date,
        pay_total_interest=pay_interest,
        pay_never_pays_off=pay.never_pays_off,
        debt_interest_saved=saved,
        months_sooner=max(0, sooner),
        savings_contributed=contributed,
        savings_balance=fv,
        savings_interest_earned=earned,
        breakeven_apy=breakeven,
        favours=favours,
    )


# ── which loan is better ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoanCandidate:
    name: str
    principal: Decimal
    annual_rate: Decimal
    #: Either a term (the payment is derived) or a payment (the term is).
    term_months: int | None = None
    payment: Decimal | None = None
    fees: Decimal = ZERO


@dataclass(frozen=True)
class LoanOutcome:
    name: str
    payment: Decimal
    months: int
    payoff_date: date | None
    never_pays_off: bool
    total_interest: Decimal
    #: Principal + interest + fees: everything that leaves your pocket.
    total_cost: Decimal


@dataclass(frozen=True)
class LoanComparison:
    loans: list[LoanOutcome]
    #: The lowest total cost among loans that actually pay off; ties go to
    #: the lower payment, then the name. None when nothing pays off.
    cheapest: str | None


def loan_compare(
    loans: list[LoanCandidate], as_of: date, cap_months: int = DEFAULT_CAP_MONTHS
) -> LoanComparison:
    outcomes: list[LoanOutcome] = []
    for loan in loans:
        if loan.principal < ZERO or loan.fees < ZERO:
            raise ValueError(f"{loan.name}: principal and fees must be non-negative")
        if loan.payment is not None:
            payment = quantize_cents(loan.payment)
        elif loan.term_months is not None:
            payment = level_payment(loan.principal, loan.annual_rate, loan.term_months)
        else:
            raise ValueError(f"{loan.name}: a term or a payment is required")
        result = amortization_schedule(loan.principal, loan.annual_rate, payment, as_of, cap_months)
        outcomes.append(
            LoanOutcome(
                name=loan.name,
                payment=payment,
                months=len(result.schedule),
                payoff_date=result.payoff_date,
                never_pays_off=result.never_pays_off,
                total_interest=result.total_interest,
                total_cost=quantize_cents(loan.principal + result.total_interest + loan.fees),
            )
        )
    paying = [o for o in outcomes if not o.never_pays_off]
    cheapest = min(paying, key=lambda o: (o.total_cost, o.payment, o.name)).name if paying else None
    return LoanComparison(loans=outcomes, cheapest=cheapest)


# ── how big an emergency fund ────────────────────────────────────────────────


@dataclass(frozen=True)
class EmergencyFundPlan:
    months: int
    monthly_contribution: Decimal
    essentials_monthly: Decimal | None
    current: Decimal | None
    target: Decimal | None
    gap: Decimal | None
    months_to_fund: int | None
    funded_by: date | None


def emergency_fund(
    current: Decimal | None,
    essentials_monthly: Decimal | None,
    months: int,
    monthly_contribution: Decimal,
    today: date,
) -> EmergencyFundPlan:
    """`months` of essential spending, and how long the gap takes to fill.

    Reads the roadmap's own figures — the essentials signal and the
    emergency-fund signal — rather than re-deriving either. Unknown inputs
    stay unknown: no essentials figure means no target, not a target of zero.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    if monthly_contribution < ZERO:
        raise ValueError("monthly_contribution must be non-negative")
    contribution = quantize_cents(monthly_contribution)
    if essentials_monthly is None or essentials_monthly <= ZERO:
        return EmergencyFundPlan(months, contribution, None, current, None, None, None, None)

    target = quantize_cents(essentials_monthly * months)
    plan = EmergencyFundPlan(
        months=months,
        monthly_contribution=contribution,
        essentials_monthly=essentials_monthly,
        current=current,
        target=target,
        gap=None,
        months_to_fund=None,
        funded_by=None,
    )
    if current is None:
        return plan

    gap = max(ZERO, target - quantize_cents(current))
    if gap == ZERO:
        return replace(plan, gap=ZERO, months_to_fund=0, funded_by=today)
    if contribution <= ZERO:
        return replace(plan, gap=gap)

    quotient = gap / contribution
    months_to_fund = int(quotient)
    if quotient > months_to_fund:
        months_to_fund += 1
    return replace(
        plan, gap=gap, months_to_fund=months_to_fund, funded_by=add_months(today, months_to_fund)
    )
