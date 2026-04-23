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
    expenses: Decimal
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
    balance: Decimal


class NetWorthPoint(BaseModel):
    date: date
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    accounts: list[AccountSnapshot]


class NetWorthResponse(BaseModel):
    points: list[NetWorthPoint]


# ─── Account Composition ──────────────────────────────────────────────────────


class AccountCompositionPoint(BaseModel):
    date: date
    checking: Decimal
    savings: Decimal
    credit_card: Decimal
    loan: Decimal
    tracking: Decimal


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
    total_expense: Decimal
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
    parent_id: uuid.UUID | None
    parent_name: str | None
    total: Decimal
    count: int
    pct: float


class SpendingGroupedResponse(BaseModel):
    groups: list[SpendingGroupItem]
    total: Decimal


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


class TimelineResponse(BaseModel):
    transactions: list[TimelineTransaction]
