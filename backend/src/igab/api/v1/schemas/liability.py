import datetime
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from igab.domain.money import Money

LiabilityType = Literal[
    "mortgage", "auto", "student", "personal", "credit_card", "medical", "other"
]


class LiabilityCreate(BaseModel):
    name: str
    #: Ignored when linked_account_id is set — a managed liability's kind is
    #: its account's type. Required for an unmanaged one, which has no account
    #: to ask.
    liability_type: LiabilityType | None = None
    interest_rate: Decimal  # annual percent, e.g. 6.25
    minimum_payment: Money
    # Managed (linked account) XOR unmanaged (manual balance) — not both.
    # Compounding is not accepted: all amortization math is monthly by design
    # (see services/amortization.py).
    linked_account_id: uuid.UUID | None = None
    manual_balance: Money | None = None
    origination_date: datetime.date | None = None
    original_principal: Money | None = None
    # Promotional financing: 0% until promo_end_date, interest_rate after.
    # promo_deferred_interest = retailer deals that charge interest
    # RETROACTIVELY when the balance isn't cleared by the deadline.
    promo_end_date: datetime.date | None = None
    promo_deferred_interest: bool = False
    term_months: int | None = None


class LiabilityUpdate(BaseModel):
    name: str | None = None
    liability_type: LiabilityType | None = None
    interest_rate: Decimal | None = None
    minimum_payment: Money | None = None
    linked_account_id: uuid.UUID | None = None
    manual_balance: Money | None = None
    origination_date: datetime.date | None = None
    original_principal: Money | None = None
    promo_end_date: datetime.date | None = None
    promo_deferred_interest: bool | None = None
    term_months: int | None = None


class LiabilityOut(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    #: Resolved, not stored: an account type key for a managed liability, the
    #: stored kind for an unmanaged one. Display labels come from the account-
    #: type registry, so a custom type reads as whatever the user named it.
    liability_type: str
    mode: Literal["managed", "unmanaged"]
    linked_account_id: uuid.UUID | None
    linked_category_id: uuid.UUID | None
    current_balance: Decimal  # owed, positive
    # 'ledger' | 'manual' | 'manual_fallback' — manual_fallback means the
    # linked account's register is empty and the pre-link manual balance is
    # standing in; the UI prompts for an opening balance in that state
    balance_source: Literal["ledger", "manual", "manual_fallback"]
    # Null until someone fills the terms in. terms_complete is the one flag to
    # branch on: false means every projection below is absent, not zero.
    interest_rate: Decimal | None
    minimum_payment: Decimal | None
    terms_complete: bool
    origination_date: datetime.date | None
    original_principal: Decimal | None
    # This month's interest at the current balance — the concrete number the
    # payoff copy compares payments against. Null without a rate.
    monthly_interest_now: Decimal | None
    # Average of recent positive payments (None until 2+ months of history).
    # Observed, not projected, so it survives missing terms. A payment is a
    # transfer INTO the liability's account — see LOAN_PAYMENT_ROW.
    average_recent_payment: Decimal | None
    # What the ledger says interest and fees came to per month over the same
    # window (None until 2+ months carry any). The actual figure where one
    # exists; `monthly_interest_now` is the modelled one.
    recent_interest_average: Decimal | None
    # Positive rows on the ledger with no partner account in the window. Not
    # payments — a balance adjustment, or a payment typed without a transfer
    # — and said out loud rather than silently left out.
    uncounted_deposits: Decimal
    # Contractual term implied by origination + principal + minimum payment.
    # implied_never_pays_off=True flags the P&I-vs-escrow data-entry trap:
    # the entered minimum wouldn't have amortized the original loan at all.
    implied_term_months: int | None
    implied_never_pays_off: bool | None
    promo_end_date: datetime.date | None
    promo_deferred_interest: bool
    term_months: int | None
    promo_projection: "PromoProjectionOut | None"
    baseline_payoff_date: datetime.date | None
    baseline_never_pays_off: bool
    live_payoff_date: datetime.date | None
    live_never_pays_off: bool
    has_live_projection: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


class PromoProjectionOut(BaseModel):
    """Where the balance stands when the promo window closes."""

    months_until_promo_end: int
    balance_at_promo_end_minimum: Decimal
    balance_at_promo_end_live: Decimal | None
    clears_before_promo: bool
    # Estimate of retroactive interest if the deadline is missed (deferred-
    # interest promos only) — retailer accrual rules vary
    deferred_interest_estimate: Decimal | None


class LiabilityBalanceSnapshotCreate(BaseModel):
    balance: Money
    date: datetime.date | None = None  # default: today


class LiabilityBalanceSnapshotOut(BaseModel):
    id: uuid.UUID
    liability_id: uuid.UUID
    date: datetime.date
    balance: Decimal
    source: str

    model_config = {"from_attributes": True}


class LinkLiabilityRequest(BaseModel):
    liability_id: uuid.UUID | None  # null unlinks


class AmortizationMonthOut(BaseModel):
    month_index: int
    date: datetime.date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    balance: Decimal


class BalancePointOut(BaseModel):
    date: datetime.date
    balance: Decimal


class AmortizationResponse(BaseModel):
    current_balance: Decimal
    # terms_complete=false returns an empty schedule and null totals rather
    # than an error: the page renders a "terms not set" state, and a 4xx would
    # make an ordinary, expected state look like a failure.
    terms_complete: bool
    baseline_schedule: list[AmortizationMonthOut]
    baseline_payoff_date: datetime.date | None
    baseline_never_pays_off: bool
    baseline_total_interest: Decimal | None
    extra_payment: Decimal | None = None
    extra_schedule: list[AmortizationMonthOut] | None = None
    extra_payoff_date: datetime.date | None = None
    extra_never_pays_off: bool = False
    extra_total_interest: Decimal | None = None
    live_payoff_date: datetime.date | None = None
    live_never_pays_off: bool = False
    live_average_payment: Decimal | None = None
    # Actual balance points before today; populated when from=origination
    history: list[BalancePointOut] = []
