import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel

# ─── Existing ─────────────────────────────────────────────────────────────────


class SpendingCategory(ApiModel):
    id: uuid.UUID
    name: str
    group_name: str
    total: Decimal
    pct: float


class SpendingReportResponse(ApiModel):
    categories: list[SpendingCategory]
    total: Decimal


class IncomeExpenseMonth(ApiModel):
    month: date
    income: Decimal
    #: Money spent. Saving and debt principal are reported separately — both
    #: leave the budget, but neither is spending.
    expenses: Decimal
    savings: Decimal
    debt_principal: Decimal
    #: income - expenses - savings - debt_principal, so the parts reconcile.
    net: Decimal


class IncomeExpenseResponse(ApiModel):
    months: list[IncomeExpenseMonth]


# ─── Dashboard ────────────────────────────────────────────────────────────────


class TopCategory(ApiModel):
    id: uuid.UUID
    name: str
    group_name: str
    total: Decimal


class DashboardMetrics(ApiModel):
    # `to_be_assigned` lived here, defaulted to zero and populated by no code
    # path. The Overview's card reads the budget-month endpoint's own figure,
    # which is the one the budget page uses — so this served a constant 0 that
    # nothing read. A field that always lies is worse than an absent one,
    # because the next reader will use it.
    net_worth: Decimal
    net_worth_prev: Decimal
    burn_rate_30: Decimal
    burn_rate_90: Decimal
    #: Monthly essential spending over the Guide's 90-day window — the same
    #: number the Guide's emergency-fund target is built from. None until
    #: something is tagged Essential (untagged, it would equal burn rate).
    essentials_monthly: Decimal | None
    essentials_tagged: bool
    #: None when no income was recorded in the window — the Savings Rate tab's
    #: convention, and a gap rather than a floor on the chart.
    savings_rate: float | None
    days_until_zero: float | None
    income_this_month: Decimal
    expenses_this_month: Decimal
    expenses_prev_month: Decimal
    top_categories: list[TopCategory]


# ─── Net Worth ────────────────────────────────────────────────────────────────


class AccountSnapshot(ApiModel):
    account_id: uuid.UUID
    account_name: str
    account_type: str
    # 'asset' | 'liability' — drives which side of net worth the balance joins
    classification: str | None = None
    balance: Decimal


class NetWorthPoint(ApiModel):
    date: date
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    # Liabilities with no Account (unmanaged liabilities) — included in
    # total_liabilities, broken out so the bucket stays visible
    unmanaged_liability_total: Decimal = Decimal("0")
    # Stated asset values (Assets, no account) — included in total_assets,
    # broken out for the same footnote: in the net line, not in any series.
    asset_value_total: Decimal = Decimal("0")
    accounts: list[AccountSnapshot]


class NetWorthResponse(ApiModel):
    points: list[NetWorthPoint]
    unmanaged_liability_total: Decimal = Decimal("0")
    asset_value_total: Decimal = Decimal("0")


# ─── Account Composition ──────────────────────────────────────────────────────


class AccountCompositionPoint(ApiModel):
    date: date
    # Balance per account-type key present in the budget (custom types
    # included) — the type set is per-budget, so it can't be a fixed schema
    balances: dict[str, Decimal]
    # Required, not optional: the chart draws this as the net trend line, and
    # a path that forgot it would draw a flat zero over real data.
    net_worth: Decimal
    # The stated-asset share of that net line — the amount by which it floats
    # above the visible account stack; footnoted when non-zero.
    asset_value_total: Decimal


class AccountCompositionResponse(ApiModel):
    points: list[AccountCompositionPoint]


# ─── Burn Rate ────────────────────────────────────────────────────────────────


class BurnRatePoint(ApiModel):
    date: date
    rolling_30: Decimal
    rolling_90: Decimal


class BurnRateResponse(ApiModel):
    points: list[BurnRatePoint]


# ─── Cash Flow (Sankey) ───────────────────────────────────────────────────────


class SankeyNode(ApiModel):
    id: str
    name: str
    type: str
    #: The entity this node stands for, when it stands for one. `id` is a
    #: display key that may compose several ids (a category node is keyed by
    #: group AND category, so one category can sit under both its own group
    #: and the savings trunk) — recovering an id by string-surgery on it sent
    #: "{group_uuid}_{category_uuid}" to the transactions API as a category id.
    entity_id: str | None = None


class SankeyLink(ApiModel):
    source: str
    target: str
    value: Decimal


class CategoryPayee(ApiModel):
    name: str
    total: Decimal


class CashFlowResponse(ApiModel):
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    total_income: Decimal
    #: Everything that left the budget. The links off the budget node sum to
    #: this — flow conservation, whatever the branches are.
    total_expense: Decimal
    #: How that outflow splits. Required, and None only in budgeted mode,
    #: which draws from assignments where activity class has no meaning —
    #: None is "this mode does not claim the figure", never zero.
    #:
    #: These defaulted to Decimal("0") and the route that builds this response
    #: never passed them, so the Cash Flow report drew "Spent $0.00" above a
    #: diagram of $83,716 in outflows for as long as the fields existed. A
    #: default is what let a path forget and still look like it had answered.
    total_spending: Decimal | None
    total_savings: Decimal | None
    total_debt_principal: Decimal | None
    category_payees: dict[str, list[CategoryPayee]]
    group_categories: dict[str, list[CategoryPayee]]


# ─── Budget vs Actual ─────────────────────────────────────────────────────────


class BudgetActualItem(ApiModel):
    category_id: uuid.UUID
    category_name: str
    category_group_name: str
    assigned: Decimal
    spent: Decimal
    #: Against the plan floored at zero (`domain.plan`), like Plan vs Reality.
    variance: Decimal
    variance_pct: float
    #: The server's verdict; the chart's filter, sort and red bar read it.
    overspent: bool


class BudgetActualResponse(ApiModel):
    categories: list[BudgetActualItem]
    total_assigned: Decimal
    total_spent: Decimal


# ─── Plan vs Reality ──────────────────────────────────────────────────────────


class PlanRealityCell(ApiModel):
    month: date
    assigned: Decimal
    spent: Decimal
    variance: Decimal


class PlanRealityCategory(ApiModel):
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


class PlanRealityResponse(ApiModel):
    months: list[date]
    categories: list[PlanRealityCategory]
    total_assigned: Decimal
    total_spent: Decimal
    chronic_count: int


# ─── Variance ─────────────────────────────────────────────────────────────────


class VariancePoint(ApiModel):
    month: date
    budget_assigned: Decimal
    actual_spent: Decimal
    monthly_variance: Decimal
    cumulative_variance: Decimal


class VarianceResponse(ApiModel):
    points: list[VariancePoint]


# ─── Volatility ───────────────────────────────────────────────────────────────


class VolatilityItem(ApiModel):
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


class VolatilityResponse(ApiModel):
    categories: list[VolatilityItem]
    #: True when each charge was spread forward over the months until the
    #: next one. Served so the page can say which reading it is showing —
    #: the same numbers under two definitions is how a chart lies quietly.
    amortized: bool = False


# ─── Spending Grouped (Pareto + Treemap) ──────────────────────────────────────


class SpendingGroupItem(ApiModel):
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


class SpendingClassExcluded(ApiModel):
    """Activity in the user's current scope that a spending report will not
    count — savings or debt payments in categories they selected or a view
    shows. Absence without this reads as a bug: "I picked Car Payment and it
    isn't here."""

    activity_class: str
    label: str
    categories: int
    total: Decimal


class SpendingGroupedResponse(ApiModel):
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
    #: The same, for a saved filter. Separate from `view_unavailable` because
    #: they are separate things: a view is an arrangement, a filter is a
    #: predicate, and losing one says nothing about the other.
    #: A saved filter was named and could not be found. REQUIRED, not
    #: defaulted: a report that forgets it would report an empty scope as an
    #: empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool


# ─── Seasonality ─────────────────────────────────────────────────────────────


class SeasonalityCell(ApiModel):
    category_id: uuid.UUID
    category_name: str
    month: date
    total: Decimal


class SeasonalityResponse(ApiModel):
    cells: list[SeasonalityCell]
    months: list[date]
    categories: list[dict]


# ─── Essentials ───────────────────────────────────────────────────────────────


class EssentialsCategory(ApiModel):
    #: None for payee-tagged rows with no category.
    category_id: uuid.UUID | None
    name: str
    group_name: str | None
    total: Decimal
    monthly_average: Decimal
    months_with_spend: int


class EssentialsMonth(ApiModel):
    month: date
    total: Decimal


class ReserveTarget(ApiModel):
    months: int
    amount: Decimal


class EssentialsReportResponse(ApiModel):
    """What a lean month costs, from what the household tagged Essential.

    `essentials_90d` is the Guide's figure (rolling 90 days ÷ 3) and what the
    Overview card shows; the per-category table averages over `months`
    complete months instead. `tagged` is False until something carries the
    tag — then every figure is 0 and the UI says where to apply it.
    """

    tagged: bool
    months: int
    window_start: date
    window_end: date
    essentials_90d: Decimal
    monthly_total_average: Decimal
    categories: list[EssentialsCategory]
    monthly_series: list[EssentialsMonth]
    #: 1 / 3 / 6 / 12 months of essentials, from `essentials_90d`.
    reserve: list[ReserveTarget]
    #: The roadmap's full-emergency-fund range, in months.
    roadmap_range: tuple[int, int]
    #: What the Guide reads as the emergency fund today — the bound
    #: category or account, else its own detection — and how many lean months
    #: that covers (`emergency_fund_balance / essentials_90d`). None when
    #: nothing looks like a fund, or nothing is tagged Essential yet.
    emergency_fund_balance: Decimal | None = None
    emergency_fund_source: str | None = None
    runway_months: Decimal | None = None
    #: Tagged Essential and still not counted, by class — see
    #: `CostOfLivingResponse.class_excluded`.
    class_excluded: list[SpendingClassExcluded] = []


# ─── Payee Analysis ───────────────────────────────────────────────────────────


class PayeeTrend(ApiModel):
    month: date
    total: Decimal


class PayeeTopCategory(ApiModel):
    category_name: str
    total: Decimal


class PayeeSpending(ApiModel):
    payee_id: uuid.UUID
    payee_name: str
    total: Decimal
    count: int
    pct: float
    monthly_trend: list[PayeeTrend]
    top_categories: list[PayeeTopCategory]
    is_recurring: bool


class PayeeAnalysisResponse(ApiModel):
    #: The `limit` largest by spend, never a page of a list.
    payees: list[PayeeSpending]
    #: Over EVERY payee in the window, not over `payees` — which is what
    #: `pct` is a share of, and what the Pareto card measures against.
    total: Decimal
    #: How many payees spent in the window. Required, because a client that
    #: knows only "25 rows" cannot say whether that is all of them, and both
    #: the payee table and the Pareto card were stating the cap as a
    #: period-wide fact.
    payee_count: int


# ─── Day Patterns ─────────────────────────────────────────────────────────────


class DayPatternItem(ApiModel):
    day_of_week: int
    day_name: str
    total: Decimal
    count: int
    avg_transaction: Decimal


class DayPatternsResponse(ApiModel):
    days: list[DayPatternItem]
    #: Present only when the user selected categories. Filtering to a category
    #: whose activity is all savings or debt payments otherwise draws an empty
    #: week with nothing to say why.
    class_excluded: list[SpendingClassExcluded] = []
    #: The requested saved filter no longer exists (deleted, or another
    #: budget's), so this report is unscoped. Said out loud for the reason
    #: `view_unavailable` is: a stale id resolving to nothing WIDENS the
    #: report, which reads as data appearing rather than a filter going
    #: missing.
    #: A saved filter was named and could not be found. REQUIRED, not
    #: defaulted: a report that forgets it would report an empty scope as an
    #: empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool
    #: The activity classes these figures count, so a drill-down opened from a
    #: bar totals what the bar says.
    counted_classes: list[str] = []


# ─── Large Transactions (Timeline) ────────────────────────────────────────────


class TimelineTransaction(ApiModel):
    id: uuid.UUID
    date: date
    amount: Decimal
    payee_name: str | None
    category_name: str | None
    memo: str | None
    #: What this row counts as. A large transfer into savings belongs on a
    #: timeline of large transactions, but calling it an expense because the
    #: amount is negative is the mislabelling this taxonomy exists to fix.
    #:
    #: None for a split whose legs do not agree on one class. The classifier is
    #: defined on LEAF rows, so a split parent — which carries no category —
    #: used to fall through every rule to the SPENDING default and an
    #: all-savings split was drawn as a red "Spending" dot. Where the legs
    #: agree, the parent takes their class; where they do not, the honest
    #: answer is that there isn't one, and `activity_label` reads "Split".
    activity_class: str | None = "spending"
    #: Its display label, served rather than mirrored. A local copy in the
    #: chart had already drifted ("Interest" vs the canonical "Interest &
    #: fees"), and a class added later would fall back to sign-based colouring
    #: there — the exact mislabelling this taxonomy exists to fix.
    activity_label: str = "Spending"


class TimelineResponse(ApiModel):
    transactions: list[TimelineTransaction]
    #: The requested saved filter no longer exists (deleted, or another
    #: budget's), so this report is unscoped. Said out loud for the reason
    #: `view_unavailable` is: a stale id resolving to nothing WIDENS the
    #: report, which reads as data appearing rather than a filter going
    #: missing.
    #: A saved filter was named and could not be found. REQUIRED, not
    #: defaulted: a report that forgets it would report an empty scope as an
    #: empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool


# ─── Liabilities Report ──────────────────────────────────────────────────────


class LiabilitiesReportItem(ApiModel):
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


class LiabilitiesBalancePoint(ApiModel):
    date: date
    per_liability: dict[str, Decimal]  # keyed by liability id
    total: Decimal


class LiabilitiesReportResponse(ApiModel):
    items: list[LiabilitiesReportItem]
    total_balance: Decimal
    # Sums only the rows whose terms are known; liabilities_missing_terms says
    # how many were left out, so a partial total can be labelled as one.
    total_interest_remaining: Decimal
    liabilities_missing_terms: int
    balance_over_time: list[LiabilitiesBalancePoint]
    #: Owed on accounts closed with a balance still on them, excluded from
    #: `total_balance` above. Net worth counts it — it spans every account —
    #: so without this the two figures disagree in silence and this one claims
    #: to be every debt.
    closed_with_balance_count: int
    closed_with_balance_total: Decimal


# ─── Subscriptions Report ────────────────────────────────────────────────────


class RecurringSpend(ApiModel):
    """The figures a recurring line carries. One shape for a category and for
    a payee inside it, because the arithmetic is the same."""

    monthly_amounts: list[Decimal]  # amounts per month in the period
    #: True monthly burden: total / months since the FIRST charge, so a
    #: quarterly $30 subscription reads $10/mo. Per payee that is a service's
    #: cost; per category it is the envelope's recurring burn rate.
    avg_monthly: Decimal
    total: Decimal
    avg_per_charge: Decimal  # typical charge: total / charge count
    last_charge_date: date | None
    transaction_count: int


class SubscriptionPayee(RecurringSpend):
    #: None for charges filed to a subscription category with no payee.
    payee_id: uuid.UUID | None
    payee_name: str


class SubscriptionCategory(RecurringSpend):
    #: Never null: the tag is on categories, so a row without one cannot be
    #: in this report at all.
    category_id: uuid.UUID
    category_name: str
    group_name: str
    payees: list[SubscriptionPayee]


class SubscriptionsSummary(ApiModel):
    total_monthly: Decimal  # average monthly total across all subscriptions
    total_annual: Decimal  # projected annual cost
    active_count: int  # number of tagged categories with charges in the period


class SubscriptionsReportResponse(ApiModel):
    subscriptions: list[SubscriptionCategory]
    summary: SubscriptionsSummary
    months: list[date]  # month labels for the period
    #: How many months an effective-monthly figure divides by: COMPLETE
    #: months. One less than the window on every day but the first of a
    #: month. Required, not optional — the page has to be able to say which
    #: months a per-month figure covers, and a default would let it claim the
    #: whole window.
    months_averaged: int


# ─── Savings Report ──────────────────────────────────────────────────────────


class SavingsCategory(ApiModel):
    category_id: uuid.UUID
    category_name: str
    group_name: str
    #: Available at the end of each month, as the Budget page states it. None
    #: where no figure can be stated — before the budget's history, or before
    #: an import whose history cannot reproduce YNAB's balance (see
    #: `SavingsReportResponse.unrecovered`). Absent, not zero.
    monthly_balances: list[Decimal | None]
    current_balance: Decimal
    target_balance: Decimal | None
    total_inflow: Decimal  # total assigned/deposited in the period


class SavingsSummary(ApiModel):
    total_balance: Decimal  # sum of current balances
    total_inflow: Decimal  # sum of inflows in the period
    avg_monthly_inflow: Decimal
    category_count: int


class ReportDrainMove(ApiModel):
    move_id: uuid.UUID
    month: date
    date: datetime
    amount: Decimal
    from_category_id: uuid.UUID
    from_name: str
    to_category_id: uuid.UUID | None
    to_name: str


class ReportDrains(ApiModel):
    """Money moved out of the report's envelopes in its window."""

    total: Decimal
    moves: list[ReportDrainMove]


class SavingsUnrecovered(ApiModel):
    """An envelope whose balance before an import could not be walked back
    from YNAB's figure: its line starts at `starts_from`."""

    category_id: uuid.UUID
    category_name: str
    starts_from: date


class SavingsReportResponse(ApiModel):
    categories: list[SavingsCategory]
    summary: SavingsSummary
    months: list[date]
    drains: ReportDrains
    #: Envelopes whose line starts late, so the page can say why rather than
    #: draw a gap nobody explained.
    unrecovered: list[SavingsUnrecovered]


# ─── Savings Rate Report ─────────────────────────────────────────────────────


class SavingsRateMonth(ApiModel):
    month: date
    income: Decimal
    spending: Decimal
    savings: Decimal
    debt_principal: Decimal
    #: None when there was no income that month — distinct from a rate of 0,
    #: which would read as "saved nothing out of real income".
    savings_rate: float | None
    savings_rate_with_debt: float | None


class SavingsRateSummary(ApiModel):
    income: Decimal
    spending: Decimal
    savings: Decimal
    debt_principal: Decimal
    savings_rate: float | None
    savings_rate_with_debt: float | None


class SavingsRateResponse(ApiModel):
    months: list[SavingsRateMonth]
    summary: SavingsRateSummary


# ─── Anomaly Detection Report ────────────────────────────────────────────────


class AnomalyItem(ApiModel):
    category_id: uuid.UUID
    category_name: str
    group_name: str
    month: date
    actual: Decimal
    baseline_mean: Decimal
    z_score: float
    direction: str  # 'high' or 'low'
    history: list[Decimal]  # trailing 12 months for sparkline


class AnomalyReportResponse(ApiModel):
    anomalies: list[AnomalyItem]


# ─── Payday Effect Report ────────────────────────────────────────────────────


class PaydayEffectDay(ApiModel):
    offset: int  # 0 = payday, 1 = day after, etc.
    avg_spend: Decimal


class PaydayEffectResponse(ApiModel):
    days: list[PaydayEffectDay]
    #: Average daily spend on days outside every payday window. None when the
    #: windows cover every day in the range — which `window=14` guarantees for
    #: biweekly pay. A served 0.00 would say "this household spends nothing
    #: outside payday", which is the opposite of "there is no outside".
    baseline_daily: Decimal | None
    event_count: int  # number of income events used


# ─── Cash Projection Report ──────────────────────────────────────────────────


class CashProjectionPoint(ApiModel):
    date: date
    p10: Decimal
    p25: Decimal
    p50: Decimal
    p75: Decimal
    p90: Decimal
    deterministic: Decimal  # projection with only scheduled/subscription events


class CashProjectionEvent(ApiModel):
    date: date
    payee: str
    amount: Decimal
    source: str  # 'scheduled' or 'subscription'


class CashProjectionResponse(ApiModel):
    start_balance: Decimal
    points: list[CashProjectionPoint]
    events: list[CashProjectionEvent]
    goes_negative_date: date | None  # first date P50 goes negative, if any


class ReportRangeResponse(ApiModel):
    """How far back this budget's reports can look — see
    `ReportService.available_range`."""

    #: First of the month the budget's oldest transaction falls in; None for a
    #: budget with no transactions at all.
    earliest_month: date | None
    #: Calendar months from that month to this one, inclusive. 0 means no
    #: history, which is not the same as 1.
    months_available: int


# ─── Spending Trends ─────────────────────────────────────────────────────────


class SpendingTrendSeries(ApiModel):
    """One category's spending per month over the window."""

    id: uuid.UUID
    name: str
    group_id: uuid.UUID | None
    group_name: str | None
    monthly: list[Decimal]
    total: Decimal


class SpendingTrendsResponse(ApiModel):
    """Spending over time for a chosen set of categories — the basic report
    that was missing. Same predicate set as the spending rollups
    (`ReportService._spending_query`), bucketed by month."""

    months: list[date]
    series: list[SpendingTrendSeries]
    #: Sum over every series per month, so a total line needs no client math.
    monthly_totals: list[Decimal]
    total: Decimal
    #: Present only when the user scoped the report (categories, a filter, a
    #: tag): activity in that scope a spending report will not count.
    class_excluded: list[SpendingClassExcluded] = []
    #: The saved filter no longer exists; the report fell back to unscoped.
    #: A saved filter was named and could not be found. REQUIRED, not
    #: defaulted: a report that forgets it would report an empty scope as an
    #: empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool


# ─── Income by Source ────────────────────────────────────────────────────────


class IncomeSource(ApiModel):
    payee_id: uuid.UUID | None
    payee_name: str
    monthly: list[Decimal]
    total: Decimal
    count: int


class IncomeBySourceResponse(ApiModel):
    """Income per payee per month: on-budget inflows the activity classifier
    reads as income (transfers, refunds and investment returns are not)."""

    months: list[date]
    sources: list[IncomeSource]
    monthly_totals: list[Decimal]
    total: Decimal


# ─── Category History ────────────────────────────────────────────────────────


class CategoryHistoryMonth(ApiModel):
    month: date
    assigned: Decimal
    activity: Decimal
    #: None for an income category: "Income categories do not hold money", so
    #: their `available` is a lifetime carryover the budget page never draws.
    #: Their monthly activity is meaningful and is still served.
    available: Decimal | None


class CategoryHistoryReportResponse(ApiModel):
    """One category month by month — assigned, activity, available — the
    figures the budget page shows, read from the same BudgetService."""

    category_id: uuid.UUID
    category_name: str
    months: list[CategoryHistoryMonth]


# ─── Cost of Living ──────────────────────────────────────────────────────────


class CostOfLivingGroup(ApiModel):
    group_name: str
    monthly_amounts: list[Decimal]
    total: Decimal
    avg_monthly: Decimal
    #: Share of the essentials total, 0-100 — not of income, so the shares
    #: add to 100 and the bar is arithmetic a reader can check.
    share: Decimal
    #: The categories behind the bar, so it can be opened. Empty on the
    #: Uncategorized bucket — that one drills by "no category", not by ids.
    category_ids: list[uuid.UUID] = []


class CostOfLivingResponse(ApiModel):
    months: list[date]
    #: The window the figures cover. Served so a drill-down asks for the same
    #: days rather than re-deriving them from `months`.
    window_start: date
    window_end: date
    #: How many months the AVERAGES divide by: COMPLETE months, so the newest
    #: column of `months` is outside it on every day but the first of a month.
    #: The RATIOS are not affected — both their terms cover the same days.
    months_averaged: int
    groups: list[CostOfLivingGroup]
    #: The wide tier: everything non-discretionary. Required, not optional — a
    #: path that forgets must raise rather than report a zero gap.
    avg_monthly_cost_of_living: Decimal
    #: The lean tier, measured over the SAME window, which is what makes the
    #: difference between them a real figure rather than a calendar artifact.
    #: None when nothing is tagged Essential (`basis_is_chosen`): all spending
    #: is not what a household could not cut, so the figure is unknown.
    avg_monthly_essentials: Decimal | None
    #: Cost of living less essentials: what a lean month could shed. None
    #: whenever essentials is.
    avg_monthly_non_essential: Decimal | None
    avg_monthly_income: Decimal
    #: Share of take-home already spoken for, against the WIDE tier. None when
    #: the averaged months carry no income: a ratio against zero is unknown,
    #: not 100%. Divides the same complete-month figures as the cards, so it is
    #: the quotient of avg_monthly_cost_of_living and avg_monthly_income.
    required_ratio: Decimal | None
    #: The lean tier against take-home, over the same complete months. Above
    #: 100 the household cannot cover what it could not cut.
    essentials_ratio: Decimal | None
    #: 'bound' | 'tag' | 'all' — how "essential" was decided.
    basis: str
    #: False when nothing carries the Essential tag, so the page can say the
    #: figure covers every category rather than a chosen few.
    tagged: bool
    #: Tagged Essential and still not counted, by class. Tagging a category is
    #: pointing at it, so this fires wherever the basis is a tag or a Guide
    #: binding — the case being "I tagged ten and two showed up".
    class_excluded: list[SpendingClassExcluded] = []
    #: The activity classes these figures count, so a drill-down opened from a
    #: bar totals what the bar says.
    counted_classes: list[str] = []
    #: The necessity tier the groups roll up. Membership is per row (debt
    #: principal by class), so the drill sends it too. Required: a drill that
    #: forgets it lists spending the bar never counted.
    necessity_tier: str


# ─── Wishlist discipline ─────────────────────────────────────────────────────


class WishlistDisciplineResponse(ApiModel):
    cooled_then_bought: int
    cooled_then_dropped: int
    bought_early: int
    #: Dropped before the cooling-off period ended. Counted as
    #: `cooled_then_dropped` until now, which reported a wish abandoned on day
    #: three of thirty under "waited, then decided against".
    dropped_early: int
    still_open: int
    #: Wanted, waited on, and not spent — the figure the report is for.
    resisted_total: Decimal
    bought_total: Decimal
    open_total: Decimal
    #: None with nothing bought: an average of no days is not zero days.
    avg_days_to_buy: int | None
    avg_wish_cost: Decimal | None
    #: Endings we cannot place against a cooling-off period — wishes that
    #: predate the drop date, or never had one. Shown, not folded in.
    unplaced: int


# ─── Starred reports ─────────────────────────────────────────────────────────


class ReportFavoritesResponse(ApiModel):
    #: Report ids, in the order they should read. The server does not know
    #: which ids are real — see `services/report_favorites.py` — so the client
    #: drops any it no longer recognises.
    tabs: list[str] = []


class ReportFavoritesUpdate(ApiModel):
    #: The whole list, not a delta: a star is a toggle on a short list, and a
    #: PUT of the result cannot disagree with itself the way an add/remove
    #: pair can when two tabs are open.
    tabs: list[str] = Field(default_factory=list, max_length=64)


# ─── Emergency fund coverage ─────────────────────────────────────────────────


class CoveragePoint(ApiModel):
    month: date
    #: What the fund held at the end of this month.
    fund_balance: Decimal
    #: The trailing three-month average of essential spending — the Guide's
    #: 90-day window said in months, so this line and the roadmap's target
    #: cannot tell different stories about the same household.
    essentials: Decimal
    #: None, never zero, for a month with no essential spending to divide by.
    coverage_months: Decimal | None
    #: The 3- and 6-month bands AT THIS MONTH. They move: as spending grows
    #: the target grows with it, and a fund standing still loses coverage
    #: without losing a cent.
    target_low: Decimal
    target_high: Decimal
    #: A self-reported balance is carried flat from the date it was given.
    #: Said per point, because a flat line drawn without a word reads as a
    #: fund that did not move.
    external_counted: bool


class EmergencyCoverageResponse(ApiModel):
    months: int
    #: False when nothing carries the Essential tag — there is no denominator,
    #: so the report explains itself instead of drawing zeroes.
    tagged: bool
    #: None when no fund has been found or declared.
    fund_balance: Decimal | None
    fund_source: str | None
    #: The Essentials report's own runway, quoted rather than recomputed.
    coverage_months: Decimal | None
    essentials_monthly: Decimal
    target_low: Decimal
    target_high: Decimal
    target_range: tuple[int, int]
    series: list[CoveragePoint] = []
    external_amount: Decimal | None = None
    external_as_of: date | None = None
    current_month: date
