import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

# ─── Existing ─────────────────────────────────────────────────────────────────


class SpendingCategory(BaseModel):
    id: uuid.UUID
    name: str
    group_name: str
    total: Decimal
    pct: float


class SpendingReportResponse(BaseModel):
    categories: list[SpendingCategory]
    total: Decimal


class IncomeExpenseMonth(BaseModel):
    month: date
    income: Decimal
    #: Money spent. Saving and debt principal are reported separately — both
    #: leave the budget, but neither is spending.
    expenses: Decimal
    savings: Decimal
    debt_principal: Decimal
    #: income - expenses - savings - debt_principal, so the parts reconcile.
    net: Decimal


class IncomeExpenseResponse(BaseModel):
    months: list[IncomeExpenseMonth]


# ─── Dashboard ────────────────────────────────────────────────────────────────


class TopCategory(BaseModel):
    id: uuid.UUID
    name: str
    group_name: str
    total: Decimal


class DashboardMetrics(BaseModel):
    to_be_assigned: Decimal = Decimal("0")
    net_worth: Decimal
    net_worth_prev: Decimal
    burn_rate_30: Decimal
    burn_rate_90: Decimal
    savings_rate: float
    days_until_zero: float | None
    income_this_month: Decimal
    expenses_this_month: Decimal
    expenses_prev_month: Decimal
    top_categories: list[TopCategory]


# ─── Net Worth ────────────────────────────────────────────────────────────────


class AccountSnapshot(BaseModel):
    account_id: uuid.UUID
    account_name: str
    account_type: str
    # 'asset' | 'liability' — drives which side of net worth the balance joins
    classification: str | None = None
    balance: Decimal


class NetWorthPoint(BaseModel):
    date: date
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    # Liabilities with no Account (unmanaged liabilities) — included in
    # total_liabilities, broken out so the bucket stays visible
    unmanaged_liability_total: Decimal = Decimal("0")
    accounts: list[AccountSnapshot]


class NetWorthResponse(BaseModel):
    points: list[NetWorthPoint]
    unmanaged_liability_total: Decimal = Decimal("0")


# ─── Account Composition ──────────────────────────────────────────────────────


class AccountCompositionPoint(BaseModel):
    date: date
    # Balance per account-type key present in the budget (custom types
    # included) — the type set is per-budget, so it can't be a fixed schema
    balances: dict[str, Decimal]


class AccountCompositionResponse(BaseModel):
    points: list[AccountCompositionPoint]


# ─── Burn Rate ────────────────────────────────────────────────────────────────


class BurnRatePoint(BaseModel):
    date: date
    rolling_30: Decimal
    rolling_90: Decimal


class BurnRateResponse(BaseModel):
    points: list[BurnRatePoint]


# ─── Cash Flow (Sankey) ───────────────────────────────────────────────────────


class SankeyNode(BaseModel):
    id: str
    name: str
    type: str
    #: The entity this node stands for, when it stands for one. `id` is a
    #: display key that may compose several ids (a category node is keyed by
    #: group AND category, so one category can sit under both its own group
    #: and the savings trunk) — recovering an id by string-surgery on it sent
    #: "{group_uuid}_{category_uuid}" to the transactions API as a category id.
    entity_id: str | None = None


class SankeyLink(BaseModel):
    source: str
    target: str
    value: Decimal


class CategoryPayee(BaseModel):
    name: str
    total: Decimal


class CashFlowResponse(BaseModel):
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    total_income: Decimal
    #: Everything that left the budget. The links off the budget node sum to
    #: this — flow conservation, whatever the branches are.
    total_expense: Decimal
    #: How that outflow splits. Spent mode only; budgeted mode draws from
    #: assignments, where activity class has no meaning.
    total_spending: Decimal = Decimal("0")
    total_savings: Decimal = Decimal("0")
    total_debt_principal: Decimal = Decimal("0")
    category_payees: dict[str, list[CategoryPayee]]
    group_categories: dict[str, list[CategoryPayee]]


# ─── Budget vs Actual ─────────────────────────────────────────────────────────


class BudgetActualItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    category_group_name: str
    assigned: Decimal
    spent: Decimal
    variance: Decimal
    variance_pct: float


class BudgetActualResponse(BaseModel):
    categories: list[BudgetActualItem]
    total_assigned: Decimal
    total_spent: Decimal


# ─── Plan vs Reality ──────────────────────────────────────────────────────────


class PlanRealityCell(BaseModel):
    month: date
    assigned: Decimal
    spent: Decimal
    variance: Decimal


class PlanRealityCategory(BaseModel):
    category_id: uuid.UUID
    category_name: str
    category_group_name: str
    monthly: list[PlanRealityCell]
    months_over: int
    months_active: int
    total_assigned: Decimal
    total_spent: Decimal
    avg_overspend: Decimal
    chronic: bool


class PlanRealityResponse(BaseModel):
    months: list[date]
    categories: list[PlanRealityCategory]
    total_assigned: Decimal
    total_spent: Decimal
    chronic_count: int


# ─── Variance ─────────────────────────────────────────────────────────────────


class VariancePoint(BaseModel):
    month: date
    budget_assigned: Decimal
    actual_spent: Decimal
    monthly_variance: Decimal
    cumulative_variance: Decimal


class VarianceResponse(BaseModel):
    points: list[VariancePoint]


# ─── Volatility ───────────────────────────────────────────────────────────────


class VolatilityItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    category_group_name: str
    mean: Decimal
    std_dev: Decimal
    min_val: Decimal
    max_val: Decimal
    p25: Decimal
    p75: Decimal
    months_included: int


class VolatilityResponse(BaseModel):
    categories: list[VolatilityItem]


# ─── Spending Grouped (Pareto + Treemap) ──────────────────────────────────────


class SpendingGroupItem(BaseModel):
    id: uuid.UUID
    name: str
    #: Opaque rollup key, not a foreign key: a category-group id normally, a
    #: view-group id under a view, and the "__unassigned__" sentinel for
    #: categories a view has not placed. Typing it as a UUID made that last
    #: case a 500 the moment a view left anything unplaced.
    parent_id: str | None
    parent_name: str | None
    total: Decimal
    count: int
    pct: float


class SpendingClassExcluded(BaseModel):
    """Activity in the user's current scope that a spending report will not
    count — savings or debt payments in categories they selected or a view
    shows. Absence without this reads as a bug: "I picked Car Payment and it
    isn't here."""

    activity_class: str
    label: str
    categories: int
    total: Decimal


class SpendingGroupedResponse(BaseModel):
    groups: list[SpendingGroupItem]
    total: Decimal
    #: What the active view kept out of this report: categories hidden by the
    #: view (or unplaced, when it hides those too) that had spending in the
    #: window. Zero without a view. The chart states this out loud — a view
    #: that hides most spending otherwise reads as data loss.
    view_hidden_categories: int = 0
    view_hidden_total: Decimal = Decimal("0")
    #: Present only when the user selected categories or a view is active.
    class_excluded: list[SpendingClassExcluded] = []
    #: The requested view no longer exists (deleted, or another budget's), so
    #: these groups are the budget's own. Said out loud because the client
    #: persists viewId outside any budget scope and would otherwise show one
    #: arrangement while its selector claims another.
    view_unavailable: bool = False


# ─── Seasonality ─────────────────────────────────────────────────────────────


class SeasonalityCell(BaseModel):
    category_id: uuid.UUID
    category_name: str
    month: date
    total: Decimal


class SeasonalityResponse(BaseModel):
    cells: list[SeasonalityCell]
    months: list[date]
    categories: list[dict]


# ─── Payee Analysis ───────────────────────────────────────────────────────────


class PayeeTrend(BaseModel):
    month: date
    total: Decimal


class PayeeTopCategory(BaseModel):
    category_name: str
    total: Decimal


class PayeeSpending(BaseModel):
    payee_id: uuid.UUID
    payee_name: str
    total: Decimal
    count: int
    pct: float
    monthly_trend: list[PayeeTrend]
    top_categories: list[PayeeTopCategory]
    is_recurring: bool


class PayeeAnalysisResponse(BaseModel):
    payees: list[PayeeSpending]
    total: Decimal


# ─── Day Patterns ─────────────────────────────────────────────────────────────


class DayPatternItem(BaseModel):
    day_of_week: int
    day_name: str
    total: Decimal
    count: int
    avg_transaction: Decimal


class DayPatternsResponse(BaseModel):
    days: list[DayPatternItem]


# ─── Large Transactions (Timeline) ────────────────────────────────────────────


class TimelineTransaction(BaseModel):
    id: uuid.UUID
    date: date
    amount: Decimal
    payee_name: str | None
    category_name: str | None
    memo: str | None
    #: What this row counts as. A large transfer into savings belongs on a
    #: timeline of large transactions, but calling it an expense because the
    #: amount is negative is the mislabelling this taxonomy exists to fix.
    activity_class: str = "spending"
    #: Its display label, served rather than mirrored. A local copy in the
    #: chart had already drifted ("Interest" vs the canonical "Interest &
    #: fees"), and a class added later would fall back to sign-based colouring
    #: there — the exact mislabelling this taxonomy exists to fix.
    activity_label: str = "Spending"


class TimelineResponse(BaseModel):
    transactions: list[TimelineTransaction]


# ─── Liabilities Report ──────────────────────────────────────────────────────


class LiabilitiesReportItem(BaseModel):
    liability_id: uuid.UUID
    name: str
    liability_type: str
    mode: str  # 'managed' | 'unmanaged'
    current_balance: Decimal
    interest_rate: Decimal | None
    baseline_payoff_date: date | None
    live_payoff_date: date | None
    # Null when the terms are unset — no schedule, so no interest to project.
    total_interest_remaining: Decimal | None
    never_pays_off: bool
    terms_complete: bool


class LiabilitiesBalancePoint(BaseModel):
    date: date
    per_liability: dict[str, Decimal]  # keyed by liability id
    total: Decimal


class LiabilitiesReportResponse(BaseModel):
    items: list[LiabilitiesReportItem]
    total_balance: Decimal
    # Sums only the rows whose terms are known; liabilities_missing_terms says
    # how many were left out, so a partial total can be labelled as one.
    total_interest_remaining: Decimal
    liabilities_missing_terms: int
    balance_over_time: list[LiabilitiesBalancePoint]


# ─── Subscriptions Report ────────────────────────────────────────────────────


class SubscriptionPayee(BaseModel):
    payee_id: uuid.UUID
    payee_name: str
    monthly_amounts: list[Decimal]  # amounts per month in the period
    total: Decimal
    avg_monthly: Decimal  # true monthly burden: total / months since first charge
    avg_per_charge: Decimal  # typical charge: total / charge count
    last_charge_date: date | None
    transaction_count: int


class SubscriptionsSummary(BaseModel):
    total_monthly: Decimal  # average monthly total across all subscriptions
    total_annual: Decimal  # projected annual cost
    active_count: int  # number of subscription payees


class SubscriptionsReportResponse(BaseModel):
    subscriptions: list[SubscriptionPayee]
    summary: SubscriptionsSummary
    months: list[date]  # month labels for the period


# ─── Savings Report ──────────────────────────────────────────────────────────


class SavingsCategory(BaseModel):
    category_id: uuid.UUID
    category_name: str
    group_name: str
    monthly_balances: list[Decimal]  # balance at end of each month
    current_balance: Decimal
    target_balance: Decimal | None
    total_inflow: Decimal  # total assigned/deposited in the period


class SavingsSummary(BaseModel):
    total_balance: Decimal  # sum of current balances
    total_inflow: Decimal  # sum of inflows in the period
    avg_monthly_inflow: Decimal
    category_count: int


class SavingsReportResponse(BaseModel):
    categories: list[SavingsCategory]
    summary: SavingsSummary
    months: list[date]


# ─── Savings Rate Report ─────────────────────────────────────────────────────


class SavingsRateMonth(BaseModel):
    month: date
    income: Decimal
    spending: Decimal
    savings: Decimal
    debt_principal: Decimal
    #: None when there was no income that month — distinct from a rate of 0,
    #: which would read as "saved nothing out of real income".
    savings_rate: float | None
    savings_rate_with_debt: float | None


class SavingsRateSummary(BaseModel):
    income: Decimal
    spending: Decimal
    savings: Decimal
    debt_principal: Decimal
    savings_rate: float | None
    savings_rate_with_debt: float | None


class SavingsRateResponse(BaseModel):
    months: list[SavingsRateMonth]
    summary: SavingsRateSummary


# ─── Anomaly Detection Report ────────────────────────────────────────────────


class AnomalyItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    group_name: str
    month: date
    actual: Decimal
    baseline_mean: Decimal
    z_score: float
    direction: str  # 'high' or 'low'
    history: list[Decimal]  # trailing 12 months for sparkline


class AnomalyReportResponse(BaseModel):
    anomalies: list[AnomalyItem]


# ─── Payday Effect Report ────────────────────────────────────────────────────


class PaydayEffectDay(BaseModel):
    offset: int  # 0 = payday, 1 = day after, etc.
    avg_spend: Decimal


class PaydayEffectResponse(BaseModel):
    days: list[PaydayEffectDay]
    baseline_daily: Decimal  # average daily spend outside the window
    event_count: int  # number of income events used


# ─── Cash Projection Report ──────────────────────────────────────────────────


class CashProjectionPoint(BaseModel):
    date: date
    p10: Decimal
    p25: Decimal
    p50: Decimal
    p75: Decimal
    p90: Decimal
    deterministic: Decimal  # projection with only scheduled/subscription events


class CashProjectionEvent(BaseModel):
    date: date
    payee: str
    amount: Decimal
    source: str  # 'scheduled' or 'subscription'


class CashProjectionResponse(BaseModel):
    start_balance: Decimal
    points: list[CashProjectionPoint]
    events: list[CashProjectionEvent]
    goes_negative_date: date | None  # first date P50 goes negative, if any
