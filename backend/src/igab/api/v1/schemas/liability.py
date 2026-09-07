import datetime
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel, ClientDated
from igab.domain.money import Money
from igab.domain.payment_composition import MAX_LABEL
from igab.services.liability_service import BalanceSource

LiabilityType = Literal[
    "mortgage", "auto", "student", "personal", "credit_card", "medical", "other"
]


class PaymentComponentIn(ApiModel):
    """One line of the monthly bill that is not principal and interest.

    Optional and additive — a car loan has none. `kind` is what the app
    reasons about (`pmi` is the one with a rule attached); `label` is the
    user's own wording for it. See domain/payment_composition.py.
    """

    kind: Literal["tax", "insurance", "pmi", "hoa", "other"] = "other"
    label: str = Field(default="", max_length=MAX_LABEL)
    amount: Money = Field(ge=0)


class PaymentComponentOut(ApiModel):
    kind: Literal["tax", "insurance", "pmi", "hoa", "other"]
    label: str
    amount: Decimal


class LiabilityCreate(ClientDated):
    name: str
    #: Ignored when linked_account_id is set — a managed liability's kind is
    #: its account's type. Required for an unmanaged one, which has no account
    #: to ask.
    liability_type: LiabilityType | None = None
    #: Annual percent, e.g. 6.25. Optional, like every other term: the column
    #: has been nullable since a3f7c1d84e26, `terms_complete` exists precisely
    #: to describe a liability whose contract is not filled in yet, and
    #: `ensure_for_account` creates companions with none. Requiring it here
    #: was the one path that disagreed — you could not record a debt you knew
    #: the balance of but not the rate.
    interest_rate: Decimal | None = None
    #: The whole payment for kind='fixed'; left blank for a percentage rule.
    minimum_payment: Money | None = None
    minimum_payment_kind: Literal["fixed", "percent_of_balance"] = "fixed"
    minimum_payment_percent: Decimal | None = None
    minimum_payment_floor: Money | None = None
    minimum_payment_plus_interest: bool = False
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
    #: The card bill's due day of the month. Metadata for the card header;
    #: no projection reads it.
    payment_due_day: int | None = Field(default=None, ge=1, le=31)
    #: Cards: the issuer's limit, for utilization. Null when unknown.
    credit_limit: Money | None = None
    #: What the bill carries BESIDE principal and interest. `minimum_payment`
    #: stays the P&I figure every projection runs on; these never touch one.
    payment_components: list[PaymentComponentIn] | None = None


class LiabilityUpdate(ApiModel):
    name: str | None = None
    liability_type: LiabilityType | None = None
    interest_rate: Decimal | None = None
    #: Explicit null clears the plan (exclude_unset keeps sent nulls).
    planned_extra_payment: Money | None = None
    minimum_payment: Money | None = None
    minimum_payment_kind: Literal["fixed", "percent_of_balance"] | None = None
    minimum_payment_percent: Decimal | None = None
    minimum_payment_floor: Money | None = None
    minimum_payment_plus_interest: bool | None = None
    linked_account_id: uuid.UUID | None = None
    manual_balance: Money | None = None
    origination_date: datetime.date | None = None
    original_principal: Money | None = None
    promo_end_date: datetime.date | None = None
    promo_deferred_interest: bool | None = None
    term_months: int | None = None
    #: Explicit null clears it, like planned_extra_payment above.
    payment_due_day: int | None = Field(default=None, ge=1, le=31)
    #: Cards: the issuer's limit, for utilization. Null when unknown.
    credit_limit: Money | None = None
    #: An empty list clears the composition; null leaves it as it was.
    payment_components: list[PaymentComponentIn] | None = None


class LiabilityOut(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    #: Resolved, not stored: an account type key for a managed liability, the
    #: stored kind for an unmanaged one. Display labels come from the account-
    #: type registry, so a custom type reads as whatever the user named it.
    liability_type: str
    mode: Literal["managed", "unmanaged"]
    linked_account_id: uuid.UUID | None
    #: The asset this debt is secured against, when the user has said so.
    #: Served because the client computes equity from it (one pure module,
    #: utils/equity.ts) — "the client already has the fields" was untrue
    #: until this line, which is the boundary-rule trap by name.
    linked_asset_id: uuid.UUID | None
    linked_category_id: uuid.UUID | None
    current_balance: Decimal  # owed, positive
    #: Where current_balance came from. The one definition is
    #: liability_service.BalanceSource; this imports it rather than restating
    #: the members, which is how 'empty' reached the service and 422'd here.
    balance_source: BalanceSource
    # Null until someone fills the terms in. terms_complete is the one flag to
    # branch on: false means every projection below is absent, not zero.
    interest_rate: Decimal | None
    minimum_payment: Decimal | None
    # The rule behind that number. A card's minimum is usually "2% of the
    # balance, or $35" rather than a figure, and a stored figure makes every
    # projection optimistic. `minimum_payment` stays authoritative for
    # kind='fixed'. Home: backend/.../domain/minimum_payment.py.
    minimum_payment_kind: str
    minimum_payment_percent: Decimal | None
    minimum_payment_floor: Decimal | None
    minimum_payment_plus_interest: bool
    # What the issuer asks for at TODAY'S balance — computed here because the
    # server owns the balance and the interest, and the client owns neither.
    # Required rather than optional: a path that forgets must raise, not
    # quietly render a rule as a blank. Null only when there is no usable
    # rule, which `terms_complete` already reports.
    minimum_payment_due_now: Decimal | None
    #: The standing curtailment plan — monthly, above the minimum, all
    #: principal by construction. The paydown what-if prefills from it.
    planned_extra_payment: Decimal | None
    terms_complete: bool
    origination_date: datetime.date | None
    original_principal: Decimal | None
    # This month's interest at the current balance — the concrete number the
    # payoff copy compares payments against. Null without a rate.
    monthly_interest_now: Decimal | None
    # Average of recent positive payments (None until 2+ months of history).
    # Observed, not projected, so it survives missing terms. A payment is a
    # transfer INTO the liability's account — see LOAN_PAYMENT_ROW.
    typical_recent_payment: Decimal | None
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
    #: The card bill's due day of the month — metadata, no projection reads it.
    payment_due_day: int | None
    credit_limit: Decimal | None
    #: balance ÷ credit_limit as a percent (domain/credit.py), to one decimal;
    #: None without a usable limit. Computed here because the server owns
    #: the balance.
    utilization: Decimal | None
    #: What the bill carries beside P&I, and what that comes to. Empty for
    #: every debt with no composition on file, which is most of them.
    payment_components: list[PaymentComponentOut]
    payment_components_total: Decimal
    #: P&I plus the components — the figure to check against a statement.
    #: Null without a fixed P&I payment to add them to.
    full_monthly_payment: Decimal | None
    #: Whether the transfers actually seen agree with the declared bill.
    #: 'matches_pi' is the healthy shape: only P&I reaches the loan, so the
    #: balance means what the schedule assumes. 'matches_full' says the whole
    #: bill lands on the loan, escrow included, so the balance falls faster
    #: than the debt does. 'undeclared_gap' is the same drift, unexplained.
    composition_check: Literal["matches_full", "matches_pi", "undeclared_gap", "unknown"]
    #: What the transfers exceed P&I by, when there is such a gap.
    composition_gap: Decimal | None
    promo_projection: "PromoProjectionOut | None"
    baseline_payoff_date: datetime.date | None
    baseline_never_pays_off: bool
    live_payoff_date: datetime.date | None
    live_never_pays_off: bool
    has_live_projection: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


class PromoProjectionOut(ApiModel):
    """Where the balance stands when the promo window closes."""

    months_until_promo_end: int
    balance_at_promo_end_minimum: Decimal
    balance_at_promo_end_live: Decimal | None
    clears_before_promo: bool
    # Estimate of retroactive interest if the deadline is missed (deferred-
    # interest promos only) — retailer accrual rules vary
    deferred_interest_estimate: Decimal | None


class LiabilityBalanceSnapshotCreate(ClientDated):
    balance: Money
    #: Defaults to the caller's today (`client_today`), and only then to the
    #: server's — see `clock.recorded_on`.
    date: datetime.date | None = None


class LiabilityBalanceSnapshotOut(ApiModel):
    id: uuid.UUID
    liability_id: uuid.UUID
    date: datetime.date
    balance: Decimal
    source: str

    model_config = {"from_attributes": True}


class LinkLiabilityRequest(ApiModel):
    liability_id: uuid.UUID | None  # null unlinks


class AmortizationMonthOut(ApiModel):
    month_index: int
    date: datetime.date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    balance: Decimal


class BalancePointOut(ApiModel):
    date: datetime.date
    balance: Decimal


class AmortizationResponse(ApiModel):
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
    #: One-off amount applied straight to the balance today — the classic
    #: curtailment question. Composes with extra_payment.
    curtailment: Decimal | None = None
    extra_schedule: list[AmortizationMonthOut] | None = None
    extra_payoff_date: datetime.date | None = None
    extra_never_pays_off: bool = False
    extra_total_interest: Decimal | None = None
    live_payoff_date: datetime.date | None = None
    live_never_pays_off: bool = False
    live_typical_payment: Decimal | None = None
    #: What the observed pace costs and how long it takes — the same two
    #: figures the page reports for the contractual minimum, so it can lead
    #: with what is actually happening instead of an assumption. None when
    #: there is too little history, or when that pace never clears the debt.
    live_total_interest: Decimal | None = None
    live_months: int | None = None
    # Actual balance points before today; populated when from=origination
    history: list[BalancePointOut] = []
