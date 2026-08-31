import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from igab.api.v1.schemas.base import ApiModel


class ConceptInfo(ApiModel):
    """A concept the roadmap can ask about, and how it may be corrected."""

    key: str
    label: str
    kind: str
    binds_to: list[str]
    prompt: str
    caveat: str
    auto: bool
    allows_external: bool
    us_only: bool
    aliases: list[str]


class SignalResponse(ApiModel):
    key: str
    #: False when the user asked us to leave this concept alone.
    tracked: bool
    #: 'auto' | 'manual' | 'external' | 'manual+external' | 'dismissed'
    #: | 'answer' | 'off'
    source: str
    #: True/False when known, None when detection could not tell. Never guessed.
    met: bool | None = None
    #: Detected plus self-reported, in the concept's own units.
    value: Decimal | None = None
    detected_value: Decimal | None = None
    #: Self-reported and never blended into any report — Guide only.
    external_value: Decimal | None = None
    external_declared: bool = False
    external_as_of: date | None = None
    target: Decimal | None = None
    #: The emergency fund only: the starter cushion (the flat figure or one
    #: month of essentials, whichever is larger) and whether the fund clears
    #: it. The roadmap's starter step reads these; the full step reads
    #: `target` / `met`. None on every other concept.
    starter_target: Decimal | None = None
    starter_met: bool | None = None
    reason: str = ""
    entities: dict[str, list[str]] = Field(default_factory=dict)
    #: Things worth mentioning that did not count — a debt with no rate on
    #: record. A gap in the data is a nudge, not a silence.
    gaps: list[str] = Field(default_factory=list)
    note: str | None = None


class SignalsResponse(ApiModel):
    personalization: bool
    concepts: list[SignalResponse]


class CandidateOption(ApiModel):
    id: str
    name: str
    detail: str | None = None


class CandidatesResponse(ApiModel):
    concept_key: str
    options: dict[str, list[CandidateOption]]


class BindingUpdate(ApiModel):
    """One concept's whole answer — the endpoint replaces rather than merges."""

    #: 'auto' resets to the app's own guess and deletes every stored row.
    mode: str = Field(pattern="^(auto|manual|dismissed|answer|external)$")
    entity_ids: dict[str, list[uuid.UUID]] | None = None
    answer: bool | None = None
    #: Declare money held outside IGAB alongside anything bound above.
    external: bool = False
    #: Optional on purpose: "I have this covered" is a complete answer, and
    #: requiring a figure invites an invented one.
    external_amount: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_shape(self) -> "BindingUpdate":
        if self.mode == "answer" and self.answer is None:
            raise ValueError("answer is required when mode is 'answer'")
        if self.mode == "external" and not self.external:
            # Saying mode='external' without setting the flag would store
            # nothing and silently read as a reset.
            self.external = True
        return self


class PreferencesUpdate(ApiModel):
    personalization: bool | None = None
    checkup: bool | None = None
    wishlist: bool | None = None
    #: Consent to the money move turning the Wishlist off implies. Without it
    #: the server refuses while a wish envelope still holds a balance and says
    #: how much, so the dialog can state the figure and no request that merely
    #: says "wishlist: false" moves money on its own.
    release_wishlist_money: bool = False


class WishlistRetirePreview(ApiModel):
    """What turning the Wishlist off would return to Ready to Assign.

    Served rather than summed on the client from the month's balances: the
    switch and the endpoint must agree on the figure, and the client cannot see
    an archived group's envelopes to add them up in the first place.
    """

    #: Envelopes carrying a balance, named so the dialog can list them.
    envelopes: list[str]
    #: Their total, in the current month.
    available: Decimal
    #: Nothing to move — the switch may flip with no dialog at all.
    is_empty: bool


class PreferencesResponse(ApiModel):
    personalization: bool
    checkup: bool
    wishlist: bool


class StepUpdate(ApiModel):
    #: null clears the mark and returns the step to undecided.
    state: str | None = Field(default=None, pattern="^(done|skipped)$")


class GuideOverview(ApiModel):
    """Everything the Guide needs to render, in one round trip."""

    concepts: list[ConceptInfo]
    thresholds: dict[str, int]
    preferences: PreferencesResponse
    progress: dict[str, str]


class CheckupMetric(ApiModel):
    """One row of the checkup: a figure against the target the roadmap states."""

    key: str
    label: str
    value: Decimal | None = None
    target: Decimal | None = None
    #: 'money' | 'months' | 'percent' | 'count'
    unit: str
    detail: str = ""
    #: Finding kinds this row is the home of, so the client can mark it.
    finding_kinds: list[str] = Field(default_factory=list)
    #: A report tab with the numbers behind this row, when one exists.
    report: str | None = None
    #: What the figure counts, by name — the whole list; the client paces it.
    names: list[str] = Field(default_factory=list)
    #: The same figure in money when `unit` is not money — the emergency fund
    #: in months also says what those months are worth.
    money_value: Decimal | None = None
    money_target: Decimal | None = None


class CheckupFinding(ApiModel):
    kind: str
    rank: int
    concept_key: str | None = None
    title: str
    detail: str = ""
    value: Decimal | None = None
    target: Decimal | None = None
    names: list[str] = Field(default_factory=list)


class CheckupResponse(ApiModel):
    """Metrics, and every finding that fired, most severe first.

    All findings are returned: the roadmap's step markers need every kind, and
    how many the health report shows is the client's call.
    """

    enabled: bool
    as_of: date
    last_run: datetime | None = None
    metrics: list[CheckupMetric]
    findings: list[CheckupFinding]


# ── scenario calculators ─────────────────────────────────────────────────────
#
# Nothing here is persisted. Inputs are what the user typed (or what the
# planner seeded from their liabilities, which they may have edited); the
# server answers with arithmetic it can show its working for.

Money = Decimal


class CascadeDebtIn(ApiModel):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    balance: Money = Field(ge=0)
    annual_rate: Decimal = Field(ge=0, le=100)
    minimum_payment: Money = Field(ge=0)


class PayoffPlanRequest(ApiModel):
    debts: list[CascadeDebtIn] = Field(min_length=1, max_length=50)
    extra: Money = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def unique_keys(self) -> "PayoffPlanRequest":
        keys = [d.key for d in self.debts]
        if len(set(keys)) != len(keys):
            raise ValueError("debt keys must be unique")
        return self


class CascadeDebtOut(ApiModel):
    key: str
    name: str
    order: int
    payoff_date: date | None
    months: int
    never_pays_off: bool
    total_interest: Decimal
    total_principal: Decimal


class CascadeMonthOut(ApiModel):
    month_index: int
    date: date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    balance: Decimal
    balances: dict[str, Decimal]


class CascadeOut(ApiModel):
    order: str
    debts: list[CascadeDebtOut]
    months: list[CascadeMonthOut]
    debt_free_date: date | None
    never_pays_off: bool
    total_interest: Decimal
    total_paid: Decimal


class PayoffPlanResponse(ApiModel):
    as_of: date
    extra: Decimal
    avalanche: CascadeOut
    snowball: CascadeOut
    #: Minimums only, nothing rolled — what happens if nothing changes.
    minimums_only: CascadeOut


class PayVsSaveRequest(ApiModel):
    balance: Money = Field(ge=0)
    annual_rate: Decimal = Field(ge=0, le=100)
    minimum_payment: Money = Field(ge=0)
    extra: Money = Field(ge=0)
    #: A rate the user can get today, typed by them. Never assumed.
    savings_apy: Decimal = Field(ge=0, le=100)


class PayVsSaveResponse(ApiModel):
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
    breakeven_apy: Decimal | None
    favours: Literal["pay", "save", "even"]


class LoanIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    principal: Money = Field(ge=0)
    annual_rate: Decimal = Field(ge=0, le=100)
    term_months: int | None = Field(default=None, ge=1, le=600)
    payment: Money | None = Field(default=None, ge=0)
    fees: Money = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def term_or_payment(self) -> "LoanIn":
        if self.term_months is None and self.payment is None:
            raise ValueError("give a term or a payment")
        return self


class LoanCompareRequest(ApiModel):
    loans: list[LoanIn] = Field(min_length=1, max_length=10)


class LoanOutcomeOut(ApiModel):
    name: str
    payment: Decimal
    months: int
    payoff_date: date | None
    never_pays_off: bool
    total_interest: Decimal
    total_cost: Decimal


class LoanCompareResponse(ApiModel):
    loans: list[LoanOutcomeOut]
    cheapest: str | None


class EmergencyFundRequest(ApiModel):
    months: int = Field(ge=1, le=12)
    monthly_contribution: Money = Field(default=Decimal("0"), ge=0)


class EmergencyFundResponse(ApiModel):
    """Sized from the roadmap's own essentials and emergency-fund figures."""

    months: int
    monthly_contribution: Decimal
    essentials_monthly: Decimal | None
    current: Decimal | None
    target: Decimal | None
    gap: Decimal | None
    months_to_fund: int | None
    funded_by: date | None
