import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field

from igab.api.v1.schemas.base import ApiModel
from igab.domain.enums import TargetStatus

# ─── Existing ─────────────────────────────────────────────────────────────────


class SpendingCategory(ApiModel):
    #: None on the Uncategorized line (`domain.spending.UNCATEGORIZED`).
    id: uuid.UUID | None
    name: str
    group_name: str
    total: Decimal
    pct: float


class SpendingReportResponse(ApiModel):
    categories: list[SpendingCategory]
    total: Decimal
    #: A saved filter was named and could not be found (see `CategoryScope`).
    #: REQUIRED, not defaulted: a report that forgets it would report an empty
    #: scope as an empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool


class IncomeExpenseMonth(ApiModel):
    month: date
    #: True on the running month, whose figures are month-to-date
    #: (`domain.dates.ReportWindow`): drawn apart and labelled "so far", never
    #: in an average, a total or a headline. Required, not defaulted — a path
    #: that forgot it would present an unfinished month as a closed one.
    partial_month: bool
    income: Decimal
    #: Money spent. Saving and debt principal are reported separately — both
    #: leave the budget, but neither is spending.
    expenses: Decimal
    #: Saved: savings_moved + savings_held (`domain.savings`).
    savings: Decimal
    savings_moved: Decimal
    savings_held: Decimal
    debt_principal: Decimal
    #: income - expenses - savings_moved - debt_principal: money-moved, so it
    #: reconciles to the accounts. Held money never left them, so `net` is
    #: deliberately not reduced by `savings_held` (`income_vs_expense`).
    net: Decimal


class IncomeExpenseResponse(ApiModel):
    months: list[IncomeExpenseMonth]
    #: The classes `expenses` counts, served so the Expenses drill-down lists
    #: them — the client kept its own copy of this list beside a comment
    #: asking the next reader to keep the two in step.
    expense_classes: list[str]


# ─── Dashboard ────────────────────────────────────────────────────────────────


class TopCategory(ApiModel):
    #: None on the Uncategorized line (`domain.spending.UNCATEGORIZED`).
    id: uuid.UUID | None
    name: str
    group_name: str
    total: Decimal


class EssentialsFigures(ApiModel):
    """What a lean month costs, both ways (`guide.concepts.essentials_at`).

    `as_paid` is the last three complete months' average as bills landed;
    `spread` swaps the sinking-fund (Long-term expense) bills in it for a
    twelfth of the last twelve complete months' worth. `spread_on` is the
    budget's setting and `monthly` the one it selects — what every target,
    runway and reserve reads. Both are always served, so a surface can show
    the other beside it. `window_start`/`window_end` are the complete months
    averaged, so a card can say which; None before any history.
    """

    # Validated from the dataclass itself: `monthly` is its property, and the
    # rule choosing it is not respelled here.
    model_config = ConfigDict(from_attributes=True)

    as_paid: Decimal
    spread: Decimal
    spread_on: bool
    monthly: Decimal
    window_start: date | None
    window_end: date | None


class FundPartOut(ApiModel):
    """One envelope or account the emergency fund counted."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    balance: Decimal


class FundExternalOut(ApiModel):
    """What the household said it keeps elsewhere. `declared` with no `amount`
    is "I have this covered" — never zero."""

    model_config = ConfigDict(from_attributes=True)

    declared: bool
    amount: Decimal | None
    as_of: date | None
    note: str | None


class EmergencyFundOut(ApiModel):
    """The emergency fund and exactly what it counted
    (`services.emergency_fund.EmergencyFund`) — tagged envelopes, marked
    off-budget accounts and anything kept elsewhere. Nothing is guessed.
    Every field required: a surface that quotes the total can always say what
    went into it."""

    model_config = ConfigDict(from_attributes=True)

    set_up: bool
    #: None only when nothing in IGAB was chosen and no figure was declared.
    total: Decimal | None
    categories: list[FundPartOut]
    accounts: list[FundPartOut]
    external: FundExternalOut


class MeansMonth(ApiModel):
    """One complete month of the Overview's Means trend
    (`report_basics.means_months`)."""

    month: date
    #: The INCOME class, as `income_this_month` counts it.
    income: Decimal
    #: COST_OF_LIVING_CLASSES, as `outflows_this_month` counts it: spending
    #: plus debt payments, never savings.
    outflows: Decimal


class DashboardMetrics(ApiModel):
    # `to_be_assigned` lived here, defaulted to zero and populated by no code
    # path. The Overview's card reads the budget-month endpoint's own figure,
    # which is the one the budget page uses — so this served a constant 0 that
    # nothing read. A field that always lies is worse than an absent one,
    # because the next reader will use it.
    net_worth: Decimal
    net_worth_prev: Decimal
    #: What began being counted between `net_worth_prev`'s day and today —
    #: accounts arriving with their opening balances, stated values first
    #: entered (`domain.tracking_start`) — and the change less it, the
    #: card's figure. The change as drawn is `net_worth - net_worth_prev`.
    net_worth_entered: Decimal
    net_worth_change: Decimal
    #: Net spending over the trailing thirty days ending today, and over the
    #: sixty days before them per thirty days (`domain.burn_rate`). The two
    #: share no day; the card's percent change is composed on the client.
    burn_rate_30: Decimal
    burn_rate_prior_60: Decimal
    #: What a lean month costs, both ways — the figures the Guide's
    #: emergency-fund target is built from. None until something is tagged
    #: Essential (untagged, it would equal burn rate).
    essentials: EssentialsFigures | None
    essentials_tagged: bool
    #: None when no income was recorded in the window — the Savings Rate tab's
    #: convention, and a gap rather than a floor on the chart.
    savings_rate: float | None
    #: `burn_rate.days_until_zero`: 0 when cash is already at or below zero,
    #: None only when nothing is burning.
    days_until_zero: float | None
    #: The `*_this_month` figures cover the requested window, whatever its
    #: length; `expenses_prev_month` covers the equal-length window before it.
    income_this_month: Decimal
    expenses_this_month: Decimal
    expenses_prev_month: Decimal
    #: Principal paid into tracked debts over the window (DEBT_PRINCIPAL).
    debt_payments_this_month: Decimal
    #: What living cost over the window: every class in COST_OF_LIVING_CLASSES,
    #: so spending plus debt payments. Savings are not an outflow here. The
    #: Overview's above/at/below-your-means verdict reads it against income.
    outflows_this_month: Decimal
    top_categories: list[TopCategory]
    #: The last 12 COMPLETE months, oldest first, whatever the requested
    #: window — fewer on a budget whose history is younger, none on an empty
    #: one; a month with no activity inside the window is zeros. Required: the
    #: Means trend card has no other source.
    means_months: list[MeansMonth]


# ─── Net Worth ────────────────────────────────────────────────────────────────


class AccountSnapshot(ApiModel):
    account_id: uuid.UUID
    account_name: str
    account_type: str
    # 'asset' | 'liability' — drives which side of net worth the balance joins
    classification: str | None = None
    balance: Decimal


class TrackingEntry(ApiModel):
    """Something that began being counted in a point's stretch
    (`domain.tracking_start.Entry`): an account arriving with its opening
    balance, or a stated value or manual debt at its first dated point."""

    kind: Literal["account", "stated_asset", "manual_debt"]
    id: uuid.UUID
    name: str
    #: Its first day in the stretch.
    day: date
    #: Signed as net worth reads it: a card's opening debt is negative.
    amount: Decimal


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
    #: What entered net worth in the stretch this point closes, and what it
    #: was — required: the chart marks these months, and a path that forgot
    #: them would draw an arrival as growth.
    entered: Decimal
    entries: list[TrackingEntry]


class StatedValueOut(ApiModel):
    """A figure told rather than added up, with the day it was last true."""

    kind: Literal["stated_asset", "manual_debt"]
    id: uuid.UUID
    name: str
    value: Decimal
    #: None for a debt typed in with no dated balance.
    as_of: date | None


class StaleBalance(ApiModel):
    """A figure in today's net worth that has not moved in
    `tracking_start.STALE_AFTER_DAYS` days."""

    kind: Literal["account", "stated_asset", "manual_debt"]
    id: uuid.UUID
    name: str
    #: None when nothing says when it was last true.
    last_changed: date | None


class NetWorthResponse(ApiModel):
    points: list[NetWorthPoint]
    unmanaged_liability_total: Decimal = Decimal("0")
    asset_value_total: Decimal = Decimal("0")
    #: Newest point less oldest, as drawn.
    change: Decimal
    #: The same, less what began being counted after the oldest point
    #: (`tracking_start.like_for_like`) — the headline. None with no points.
    like_for_like_change: Decimal | None
    #: What began being counted after the oldest point: `change` less
    #: `like_for_like_change`.
    entered_total: Decimal
    stated_values: list[StatedValueOut]
    stale_balances: list[StaleBalance]


# ─── Account Composition ──────────────────────────────────────────────────────


class AccountCompositionPoint(ApiModel):
    date: date
    # Balance per account-type key in `series` (custom types included) — the
    # type set is per-budget, so it can't be a fixed schema
    balances: dict[str, Decimal]
    #: The bands no account holds, so the stack sums to `net_worth`: stated
    #: asset values (positive) and debts with no account (negative).
    stated_assets: Decimal
    manual_debts: Decimal
    # Required, not optional: the chart draws this as the net trend line, and
    # a path that forgot it would draw a flat zero over real data.
    net_worth: Decimal
    asset_value_total: Decimal
    #: As on the Net Worth point: what entered in this point's stretch.
    entered: Decimal
    entries: list[TrackingEntry]


class AccountCompositionResponse(ApiModel):
    points: list[AccountCompositionPoint]
    #: Every account type a live account has, registry order — a series'
    #: colour is its place here, so it holds across ranges.
    series: list[str]


# ─── Burn Rate ────────────────────────────────────────────────────────────────


class BurnRatePoint(ApiModel):
    """One month: the trailing thirty days ending on its last day (today, for
    this month) and the sixty before them per thirty days — the Overview's
    `burn_rate_30`/`burn_rate_prior_60` on the newest point."""

    date: date
    rolling_30: Decimal
    prior_60: Decimal


class BurnRateResponse(ApiModel):
    points: list[BurnRatePoint]


# ─── Cash Flow (Sankey) ───────────────────────────────────────────────────────


class SankeyNode(ApiModel):
    id: str
    name: str
    #: Left of the hub: "income_payee", "inflow" (refunds, from savings,
    #: borrowed, re-planned) or "shortfall". The hub is "budget". Right of it:
    #: "category_group" (and its "category" children) or "left_over".
    type: str
    #: The entity this node stands for, when it stands for one. `id` is a
    #: display key that may compose several ids (a category node is keyed by
    #: group AND category, so one category can sit under both its own group
    #: and the savings trunk) — recovering an id by string-surgery on it sent
    #: "{group_uuid}_{category_uuid}" to the transactions API as a category id.
    entity_id: str | None = None
    #: On a spent-mode category node: the activity classes it counted. Its
    #: drill-down lists exactly these, because the three pseudo-nodes
    #: (Savings, Debt Payments, Uncategorized) share "no category" and differ
    #: only by class. None on every other node.
    activity_classes: list[str] | None = None


class SankeyLink(ApiModel):
    source: str
    target: str
    value: Decimal


class CategoryPayee(ApiModel):
    name: str
    total: Decimal


class CashFlowResponse(ApiModel):
    """`domain.cash_flow`: sources → the hub ("__budget__") → groups →
    categories, with the two sides balanced by a Left over or Shortfall node."""

    nodes: list[SankeyNode]
    links: list[SankeyLink]
    #: INCOME_ROW, net — Income vs Expenses' income.
    total_income: Decimal
    #: What the right side draws, Left over aside: the links off the hub to
    #: category groups sum to this.
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
    #: Budgeted mode: assignments net of re-planning. None in spent mode.
    total_assigned: Decimal | None
    #: Spent mode: money in less money out — Income vs Expenses' `net` for the
    #: same window. None in budgeted mode, which has no such figure: income
    #: less assigned is not the growth of anything.
    net: Decimal | None
    #: Per category node: its payees netted, those that net to an outflow, the
    #: largest ten and "Other payees".
    category_payees: dict[str, list[CategoryPayee]]
    group_categories: dict[str, list[CategoryPayee]]
    #: Per category node whose payees are wider than it (a refund from a payee
    #: with no charge in the window): what came back, and what to call it.
    #: The payee level draws it as a source so that level balances too.
    category_returns: dict[str, CategoryPayee]


# ─── Budget vs Actual ─────────────────────────────────────────────────────────


class BudgetActualItem(ApiModel):
    category_id: uuid.UUID
    category_name: str
    category_group_name: str
    #: The window's budget assignments, as the budget grid shows them.
    assigned: Decimal
    #: Money moved into the envelope — a transfer from savings, a deposit
    #: filed to it (`domain.plan.plan_effect`). It raises the plan.
    moved_in: Decimal
    #: `assigned + moved_in`, floored at zero: what `variance` is measured
    #: against. Served so the chart never adds the two itself.
    plan: Decimal
    #: Net of refunds. Negative only when refunds beat the spending.
    spent: Decimal
    #: Against the plan floored at zero (`domain.plan`), like Plan vs Reality.
    variance: Decimal
    #: None where there was no plan to take a share of — "no plan", not 0%.
    variance_pct: float | None
    #: The server's verdict; the chart's filter, sort and red bar read it.
    overspent: bool


class BudgetActualResponse(ApiModel):
    categories: list[BudgetActualItem]
    total_assigned: Decimal
    total_moved_in: Decimal
    #: The rows' plans summed; `total_plan - total_spent == total_variance`.
    total_plan: Decimal
    total_spent: Decimal
    #: The rows' floored variances summed (`plan.total_variance`) — the
    #: headline. Not `total_assigned - total_spent`, which disagrees with the
    #: rows wherever an envelope was drained.
    total_variance: Decimal
    #: A saved filter was named and could not be found (see `CategoryScope`).
    #: REQUIRED, not defaulted: a report that forgets it would report an empty
    #: scope as an empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool


# ─── Plan vs Reality ──────────────────────────────────────────────────────────


class PlanRealityCell(ApiModel):
    month: date
    assigned: Decimal
    moved_in: Decimal
    #: `assigned + moved_in` floored at zero (`domain.plan.plan_outcome`).
    plan: Decimal
    spent: Decimal
    variance: Decimal
    #: The verdict — past the plan by a dollar and 1% of it. The cell's tint
    #: reads this, never the variance's sign.
    over: bool
    #: Anything planned or spent this month: the cells the matrix fills and
    #: `months_active` counts.
    active: bool


class PlanRealityCategory(ApiModel):
    category_id: uuid.UUID
    category_name: str
    category_group_name: str
    monthly: list[PlanRealityCell]
    months_over: int
    months_active: int
    total_assigned: Decimal
    total_moved_in: Decimal
    total_spent: Decimal
    avg_overspend: Decimal
    #: `domain.plan.is_chronic`. The Guide's checkup reads this flag.
    chronic: bool
    #: Tagged Long-term expense, which is never chronic — said, so the page
    #: can explain an over-plan month that carries no flag.
    sinking_fund: bool


class PlanRealityResponse(ApiModel):
    months: list[date]
    #: The newest of `months`, still running (`domain.dates.ReportWindow`):
    #: its cells are month-to-date, drawn apart and labelled "so far", and no
    #: verdict or total — chronic, months over, the headline sums — reads it.
    running_month: date
    categories: list[PlanRealityCategory]
    total_assigned: Decimal
    total_moved_in: Decimal
    total_spent: Decimal
    chronic_count: int


# ─── Variance ─────────────────────────────────────────────────────────────────


class VariancePoint(ApiModel):
    month: date
    #: True on the running month, whose figures are month-to-date
    #: (`domain.dates.ReportWindow`): drawn apart and labelled "so far", never
    #: in an average, a total or a headline. Required, not defaulted — a path
    #: that forgot it would present an unfinished month as a closed one.
    partial_month: bool
    budget_assigned: Decimal
    moved_in: Decimal
    #: The month's category plans summed, each floored at zero:
    #: `planned - actual_spent == monthly_variance`.
    planned: Decimal
    #: Net of refunds.
    actual_spent: Decimal
    monthly_variance: Decimal
    #: The drift of the complete months through this one. None on the running
    #: month: its whole assignment lands on the 1st and its spending over
    #: thirty days, so counting it read "under budget" every month's start.
    cumulative_variance: Decimal | None


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
    #: True when each charge was spread over the months it pays for
    #: (`domain.amortize.spread_forward`). Served so the page can say which
    #: reading it is showing — the same numbers under two definitions is how a
    #: chart lies quietly — and required, so a path that forgets it raises
    #: instead of calling amortized figures raw. The caption and the export
    #: filename read it.
    amortized: bool
    #: The complete months the statistics read. The drill-down lists exactly
    #: these; the chart used to compute its own, and it drifted.
    window_start: date
    window_end: date


# ─── Spending Grouped (Pareto + Treemap) ──────────────────────────────────────


class SpendingGroupItem(ApiModel):
    #: None on the Uncategorized line: spending with no category, which a
    #: drill opens by `no_category` (`domain.spending.UNCATEGORIZED`).
    id: uuid.UUID | None
    name: str
    #: Opaque rollup key, not a foreign key: a category-group id normally, a
    #: view-group id under a view, and the "__unassigned__" sentinel for
    #: categories a view has not placed. Typing it as a UUID made that last
    #: case a 500 the moment a view left anything unplaced.
    parent_id: str | None
    #: Always named — the Uncategorized line's group is
    #: `domain.spending.UNCATEGORIZED` — so the page never names a group
    #: itself. It was optional, and three charts each chose a name for a null
    #: the server never sent: "Uncategorized", "Other" and "Ungrouped".
    parent_name: str
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
    #: Separate from `view_unavailable`: a view is an arrangement, a filter
    #: is a predicate, and losing one says nothing about the other.
    #: A saved filter was named and could not be found (see `CategoryScope`).
    #: REQUIRED, not defaulted: a report that forgets it would report an empty
    #: scope as an empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool
    #: The activity classes these figures count, so a drill-down opened from
    #: them lists exactly those rows. REQUIRED: `[]` makes the client send no
    #: class filter, and the panel lists more than the chart.
    counted_classes: list[str]


# ─── Seasonality ─────────────────────────────────────────────────────────────


class SeasonalityCell(ApiModel):
    #: None on the Uncategorized row.
    category_id: uuid.UUID | None
    category_name: str
    month: date
    #: Net of refunds, so a month that took back more than it spent is negative.
    total: Decimal


class SeasonalityCategory(ApiModel):
    #: None on the Uncategorized row.
    id: uuid.UUID | None
    name: str


class SeasonalityResponse(ApiModel):
    cells: list[SeasonalityCell]
    months: list[date]
    #: The largest `report_service.SEASONALITY_TOP` by net spending.
    categories: list[SeasonalityCategory]
    #: Every category that spent in the window, so the page can say "top 20
    #: of N" rather than let the cut pass for the whole budget.
    category_count: int
    #: The activity classes these figures count, so a drill-down opened from
    #: them lists exactly those rows. REQUIRED: `[]` makes the client send no
    #: class filter, and the panel lists more than the chart.
    counted_classes: list[str]


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
    """One complete month of essential spending, as paid — a chart of what
    was spent never spreads a bill."""

    month: date
    total: Decimal
    #: The part of `total` filed to a sinking fund (`IN_SINKING_FUND`), so the
    #: coverage series can spread it.
    sinking_total: Decimal


class ReserveTarget(ApiModel):
    months: int
    amount: Decimal


class EssentialsReportResponse(ApiModel):
    """What a lean month costs, from what the household tagged Essential.

    `essentials` is the Guide's figure (the last three complete months,
    sinking-fund bills spread when the budget's setting is on) and what the
    Overview card shows; the per-category table averages over `months_averaged`
    complete months instead. `tagged` is False until something carries the
    tag — then every figure is 0 and the UI says where to apply it.
    """

    tagged: bool
    months: int
    window_start: date
    window_end: date
    #: The complete months the table's averages divide by: `months`, or fewer
    #: when the budget's history is younger (`history_window`).
    months_averaged: int
    #: Served whether or not anything is tagged — zeros when nothing is.
    essentials: EssentialsFigures
    #: How many Essential categories are also Long-term expense. None means
    #: the spread setting has nothing to spread, so the page hides its toggle
    #: and says why.
    long_term_essentials: int
    monthly_total_average: Decimal
    categories: list[EssentialsCategory]
    monthly_series: list[EssentialsMonth]
    #: 1 / 3 / 6 / 12 months of essentials, from `essentials.monthly`.
    reserve: list[ReserveTarget]
    #: The roadmap's full-emergency-fund range, in months.
    roadmap_range: tuple[int, int]
    #: The emergency fund and what it counted, read whatever the Guide tracks.
    emergency_fund: EmergencyFundOut
    #: How many lean months `emergency_fund.total` covers
    #: (`total / essentials.monthly`). None when nothing was chosen, or nothing
    #: is tagged Essential yet.
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
    #: How many of the largest payees make up 80% of `total`, counted over
    #: every payee (`domain.concentration`). None when nothing was spent. The
    #: Pareto card reads it: the client holds only the top 25.
    payees_to_80pct: int | None
    #: How many of the window's months a payee must appear in to be
    #: `is_recurring` (`domain.spending.recurring_months`). None when the
    #: window is too short to call anything recurring — the page says so.
    recurring_min_months: int | None
    #: The activity classes these figures count, so a drill-down opened from
    #: them lists exactly those rows. REQUIRED: `[]` makes the client send no
    #: class filter, and the panel lists more than the chart.
    counted_classes: list[str]


# ─── Day Patterns ─────────────────────────────────────────────────────────────


class DayPatternItem(ApiModel):
    day_of_week: int
    day_name: str
    #: Net spending on this weekday across the window.
    total: Decimal
    #: Purchases, not rows: a split's legs are one purchase.
    count: int
    #: How many of this weekday the window holds — the divisor of
    #: `avg_per_day`, quiet days included.
    weekdays: int
    #: `total` / `weekdays`: a typical such day. None when the window holds
    #: none of this weekday.
    avg_per_day: Decimal | None


class DayPatternsResponse(ApiModel):
    days: list[DayPatternItem]
    #: Present only when the user selected categories. Filtering to a category
    #: whose activity is all savings or debt payments otherwise draws an empty
    #: week with nothing to say why.
    class_excluded: list[SpendingClassExcluded] = []
    #: A saved filter was named and could not be found (see `CategoryScope`).
    #: REQUIRED, not defaulted: a report that forgets it would report an empty
    #: scope as an empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool
    #: The activity classes these figures count, so a drill-down opened from a
    #: bar totals what the bar says. REQUIRED: `[]` makes the client send no
    #: class filter, and the panel lists more than the bar.
    counted_classes: list[str]
    #: The days `weekdays` counts: the requested range, from no earlier than
    #: the budget's first transaction and through no later than today.
    window_start: date
    window_end: date


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
    #:
    #: Required, both of them: None now means "the legs disagree", so a
    #: default of "spending" filled in for a path that forgot would draw an
    #: all-savings split as a red Spending dot again, with no error.
    activity_class: str | None
    #: Its display label, served rather than mirrored. A local copy in the
    #: chart had already drifted ("Interest" vs the canonical "Interest &
    #: fees"), and a class added later would fall back to sign-based colouring
    #: there — the exact mislabelling this taxonomy exists to fix.
    activity_label: str


class TimelineResponse(ApiModel):
    transactions: list[TimelineTransaction]
    #: A saved filter was named and could not be found (see `CategoryScope`).
    #: REQUIRED, not defaulted: a report that forgets it would report an empty
    #: scope as an empty budget, which is the failure the flag exists to prevent.
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
    #: At the minimum payment. Null when the terms are unset — no schedule, so
    #: no interest to project — and when the minimum never retires the debt,
    #: which has no interest bill to quote (`AmortizationResult.interest_to_payoff`).
    total_interest_remaining: Decimal | None
    #: The minimum-payment schedule never retires the debt: the page says
    #: "Never at this payment" where the date and the interest would be.
    baseline_never_pays_off: bool
    #: The payoff verdict, measured at `payoff_basis`.
    never_pays_off: bool
    #: "observed" when two months of payments give a pace, "minimum" when only
    #: the contract speaks, null without terms. The page said "at current pace"
    #: for both, which a debt with no payment history does not have.
    payoff_basis: Literal["observed", "minimum"] | None
    #: The verdict's date (`amortization.payoff_verdict`): None when it never
    #: pays off at that payment, or without terms.
    payoff_date: date | None
    terms_complete: bool
    #: Why there is no payoff at the pace actually paid, when there is none
    #: (`liability_service.pace_missing`): the cell says it instead of "—".
    pace_missing: Literal["no_terms", "payments_not_linked", "too_little_history"] | None
    #: The entered payment contradicts the loan's own terms
    #: (`amortization.terms_check`) — most often escrow folded into it.
    terms_disagree: bool


class LiabilitiesBalancePoint(ApiModel):
    date: date
    #: Keyed by liability id. A debt is absent before its first point — not
    #: zero, which drew its arrival as a cliff up from nothing.
    per_liability: dict[str, Decimal]
    total: Decimal
    #: What began being counted this month, as owed (positive) and keyed to
    #: the liability: the net-worth chart's arrivals for these rows.
    entered: Decimal
    entries: list[TrackingEntry]


class LiabilitiesReportResponse(ApiModel):
    items: list[LiabilitiesReportItem]
    total_balance: Decimal
    # Sums only the rows with a finite interest bill; the two counts below say
    # how many were left out and why, so a partial total can be labelled as one.
    total_interest_remaining: Decimal
    liabilities_missing_terms: int
    #: What those rows owe: the caveat is said in dollars.
    missing_terms_balance: Decimal
    #: Rows owing anything today.
    carrying_balance_count: int
    #: Rows whose minimum payment never retires the debt — excluded from the
    #: total above rather than added in at $0 or at fifty years' worth.
    liabilities_never_paying_off: int
    balance_over_time: list[LiabilitiesBalancePoint]
    #: Owed on accounts closed with a balance still on them, excluded from
    #: `total_balance` above. Net worth counts it — it spans every account —
    #: so without this the two figures disagree in silence and this one claims
    #: to be every debt. Narrowed by the same type and mode filters as the
    #: items, so it describes only debt the filtered total could have held.
    closed_with_balance_count: int
    closed_with_balance_total: Decimal


# ─── Subscriptions Report ────────────────────────────────────────────────────


class SubscriptionService(ApiModel):
    """One service — a payee inside a Subscription-tagged category — and what
    it costs a year (`domain.subscriptions.service_cost`)."""

    #: None for charges filed to a subscription category with no payee.
    payee_id: uuid.UUID | None
    payee_name: str
    #: How Annual was arrived at: "observed" (the last 12 complete months'
    #: charges), "new" (younger than that year: latest charge × cycles a
    #: year), "price_change" (the year's charges at the latest price) or
    #: "stopped" (no charge for 1.5 cycles; Annual is zero).
    basis: Literal["observed", "new", "price_change", "stopped"]
    #: Net of refunds. Zero for a stopped service.
    annual: Decimal
    monthly: Decimal  # annual ÷ 12
    interval_days: int
    #: "monthly" and "yearly" are calendar cadences (`schedule.cadence_of`);
    #: "days" is every `interval_days`.
    cadence: Literal["monthly", "yearly", "days"]
    #: One charge says nothing about cadence: "monthly" is assumed for the
    #: stopped rule, and a "new" service counts its charge once.
    cadence_assumed: bool
    latest_charge: Decimal  # the most recent charge, positive
    first_charge_date: date
    last_charge_date: date
    charges_in_year: int
    refunded_in_year: Decimal  # already taken off `annual`


class SubscriptionCategory(ApiModel):
    #: Never null: the tag is on categories, so a row without one cannot be
    #: in this report at all.
    category_id: uuid.UUID
    category_name: str
    group_name: str
    #: The sum of its services' Annual — the table adds up.
    annual: Decimal
    monthly: Decimal  # annual ÷ 12
    #: Net charges per month of `months`, for the chart. The range picker
    #: moves only these; Annual reads its own year.
    monthly_amounts: list[Decimal]
    total: Decimal  # the sum of monthly_amounts
    last_charge_date: date
    services: list[SubscriptionService]


class SubscriptionsSummary(ApiModel):
    #: The sum of every category's Annual, itself the sum of its services'.
    total_annual: Decimal
    total_monthly: Decimal  # total_annual ÷ 12
    #: Categories with a service still charging, of `tagged_categories`. The
    #: card read "Active 2" — a count of categories, under a label that read
    #: as services, and stopped ones counted.
    charged_categories: int
    tagged_categories: int
    #: Services first charged in the month still running.
    new_this_month: int
    #: Services whose Annual is projected: a price change, or a new service
    #: with a cadence to project (one charge counts once, and is not).
    projected_services: int
    stopped_services: int


class SubscriptionsReportResponse(ApiModel):
    subscriptions: list[SubscriptionCategory]
    summary: SubscriptionsSummary
    months: list[date]  # the chart's complete months
    #: Every listed category's month, summed — what a stacked chart that
    #: draws the largest few and an Other band must stand at.
    monthly_totals: list[Decimal]
    #: The 12 complete months Annual reads, whatever `months` is.
    year_start: date
    year_end: date


# ─── Savings Report ──────────────────────────────────────────────────────────


class SavingsTargetOut(ApiModel):
    """An envelope's target, as the Budget page judges it this month."""

    type: str
    amount: Decimal
    target_date: date | None
    #: The Budget page's pill (`TargetService.calculate_status`).
    status: TargetStatus
    #: Available ÷ amount for a savings-balance target, floored at 0 and not
    #: capped. None for a funding target, which asks for a pace, not a balance.
    progress: Decimal | None


class SavingsEnvelopeOut(ApiModel):
    category_id: uuid.UUID
    category_name: str
    group_name: str
    #: Available at the end of each month, as the Budget page states it. None
    #: where no figure can be stated — before the budget's history, or before
    #: an import whose history cannot reproduce YNAB's balance (see
    #: `SavingsReportResponse.unrecovered`). Absent, not zero.
    monthly_balances: list[Decimal | None]
    current_balance: Decimal
    #: Positive assignments in the window.
    total_inflow: Decimal
    target: SavingsTargetOut | None


class SavingsAccountOut(ApiModel):
    """An off-budget account that counts as savings (`txn_filters.SAVINGS_ACCOUNT`)."""

    account_id: uuid.UUID
    name: str
    account_type: str
    #: Balance through each month's end, the running month through today. None
    #: before the account's first row.
    monthly_balances: list[Decimal | None]
    current_balance: Decimal


class SavingsSavedOut(ApiModel):
    """Kept-here Savings and Emergency fund envelopes plus off-budget savings
    accounts. `total = envelopes_total + accounts_total`; envelopes count at
    their carryover-floored Available."""

    total: Decimal
    envelopes_total: Decimal
    accounts_total: Decimal
    #: Set aside at each month's end, aligned with `months`. None where
    #: nothing in the section has a figure yet — before a savings account's
    #: first row, say — which the chart leaves blank rather than drawing $0.
    monthly_totals: list[Decimal | None]
    #: What arrived in each month by a savings account being linked (its
    #: opening rows, `domain.tracking_start`), aligned with `months` — a step
    #: up nobody saved, marked as Net Worth marks it.
    monthly_entered: list[Decimal]
    monthly_entries: list[list[TrackingEntry]]
    envelopes: list[SavingsEnvelopeOut]
    accounts: list[SavingsAccountOut]


class SavingsSectionOut(ApiModel):
    """On the way to savings, or Sinking funds: never added to Saved."""

    total: Decimal
    envelopes: list[SavingsEnvelopeOut]


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
    """The Savings report in three parts (`services/savings_report.py`)."""

    saved: SavingsSavedOut
    #: What sent-out Savings envelopes hold until the money leaves.
    on_the_way: SavingsSectionOut
    #: Long-term expense envelopes that are not savings.
    sinking_funds: SavingsSectionOut
    months: list[date]
    #: Moves out of Savings and Emergency fund envelopes (both modes), not
    #: sinking funds.
    drains: ReportDrains
    #: Envelopes whose line starts late, so the page can say why rather than
    #: draw a gap nobody explained.
    unrecovered: list[SavingsUnrecovered]


# ─── Savings Rate Report ─────────────────────────────────────────────────────


class SavingsRateMonth(ApiModel):
    month: date
    #: True on the running month, whose figures are month-to-date
    #: (`domain.dates.ReportWindow`): drawn apart and labelled "so far", never
    #: in an average, a total or a headline. Required, not defaulted — a path
    #: that forgot it would present an unfinished month as a closed one.
    partial_month: bool
    income: Decimal
    spending: Decimal
    #: Saved: savings_moved + savings_held (`domain.savings`).
    savings: Decimal
    savings_moved: Decimal
    savings_held: Decimal
    debt_principal: Decimal
    #: None when there was no income that month — distinct from a rate of 0,
    #: which would read as "saved nothing out of real income".
    savings_rate: float | None
    savings_rate_with_debt: float | None


class SavingsRateSummary(ApiModel):
    income: Decimal
    spending: Decimal
    savings: Decimal
    savings_moved: Decimal
    #: The months' held added up — the held change over the whole window.
    savings_held: Decimal
    debt_principal: Decimal
    savings_rate: float | None
    savings_rate_with_debt: float | None


class SavingsRateResponse(ApiModel):
    months: list[SavingsRateMonth]
    #: The dates `summary` covers: the complete months only, first day of the
    #: oldest through the last day of last month. Empty (start after end) when
    #: the history starts this month. The savings-rate dialog asks
    #: /savings-contributors for exactly this.
    start_date: date
    end_date: date
    summary: SavingsRateSummary


class SavingsContributor(ApiModel):
    """One place money counted toward savings (or debt principal) went.

    Named by destination: a transfer to a tracked account by that account,
    anything else by its category. `total` is the class magnitude — positive
    for money that left the budget, negative for money drawn back into it.
    A kept-here Savings envelope's held change is a category row with reason
    `held_in_savings_envelope`; its `count` is its register rows.
    """

    kind: Literal["account", "category"]
    id: uuid.UUID
    name: str
    #: The ActivityReason that decided these rows; where rules differed, the
    #: first in the classifier's own order.
    reason: str
    reason_label: str
    total: Decimal
    count: int


class SavingsIncomeSource(ApiModel):
    payee_id: uuid.UUID | None
    payee_name: str
    total: Decimal
    count: int


class SavingsContributorsResponse(ApiModel):
    """What a savings rate over [start_date, end_date] was made of.

    The totals are the figures the rate cards divide, and each list sums to
    its total exactly. The rate itself is not served here: the card that
    opens the dialog already has it.
    """

    start_date: date
    end_date: date
    income: Decimal
    #: Saved: savings_moved + savings_held.
    savings: Decimal
    savings_moved: Decimal
    savings_held: Decimal
    debt_principal: Decimal
    savings_contributors: list[SavingsContributor]
    debt_contributors: list[SavingsContributor]
    income_sources: list[SavingsIncomeSource]


# ─── Anomaly Detection Report ────────────────────────────────────────────────


class AnomalyItem(ApiModel):
    category_id: uuid.UUID
    category_name: str
    group_name: str
    month: date
    actual: Decimal
    baseline_mean: Decimal
    #: The baseline's mean one σ either way, floored at zero.
    usual_low: Decimal
    usual_high: Decimal
    z_score: float
    direction: str  # 'high' or 'low'
    #: True when `month` is the month still in progress, whose figure is
    #: month-to-date. Required, not optional: a path that forgets it would
    #: present an unfinished month as a closed one. Such rows are always
    #: `direction == 'high'` — `report_stats.anomaly_scan` says why.
    partial_month: bool
    #: Twelve calendar months ending with `month`; None before the category's
    #: first spending in the window.
    history: list[Decimal | None]


class AnomalyReportResponse(ApiModel):
    anomalies: list[AnomalyItem]
    #: Categories with spending in the window, sinking funds aside.
    categories_seen: int
    #: Of those, how many had enough earlier months to be scored.
    categories_tested: int
    #: Long-term expense categories with spending, which are never tested.
    sinking_funds_skipped: int


# ─── Payday Effect Report ────────────────────────────────────────────────────


class PaydayEffectDay(ApiModel):
    offset: int  # 0 = payday, 1 = day after, etc.
    #: The median payday's discretionary spending on this day after it.
    median_spend: Decimal
    #: Paydays this offset has happened for: the newest may not have reached
    #: its later days yet.
    paydays: int


class PaydayEffectResponse(ApiModel):
    days: list[PaydayEffectDay]
    #: The median day's discretionary spending across the whole window,
    #: paydays included, over `baseline_days` days. None only when there were
    #: no paydays, and so nothing to compare it with.
    baseline_daily: Decimal | None
    baseline_days: int
    #: Paydays found in the window.
    event_count: int
    #: The days read: the last N complete months and the running month so far.
    window_start: date
    window_end: date
    #: The smallest inflow counted as a payday (report_service.PAYDAY_FLOOR),
    #: served so the panel states the rule without a second copy of it.
    payday_floor: Decimal


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
    #: The first day the median path is below zero, if any.
    goes_negative_date: date | None
    #: The first day the p10 band is below zero — about a 1 in 10 chance of
    #: being under $0 by then. Never later than `goes_negative_date`; the UI
    #: warns softly on this one alone (`domain.cash_projection`).
    p10_negative_date: date | None


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
    """One category's spending per month over the window, net of refunds."""

    #: None on the Uncategorized series.
    id: uuid.UUID | None
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
    #: `total` over the months the range holds whole and that are over
    #: (`domain.dates.complete_months_within`) — `months_averaged` of them.
    #: None when there is none: a range inside the running month has no
    #: complete month to average.
    avg_monthly: Decimal | None
    months_averaged: int
    #: The running month when the range draws it: month-to-date, labelled
    #: "so far", never in `avg_monthly`. None when the range ends before it.
    running_month: date | None
    #: Present only when the user scoped the report (categories, a filter, a
    #: tag): activity in that scope a spending report will not count.
    class_excluded: list[SpendingClassExcluded] = []
    #: A saved filter was named and could not be found (see `CategoryScope`).
    #: REQUIRED, not defaulted: a report that forgets it would report an empty
    #: scope as an empty budget, which is the failure the flag exists to prevent.
    filter_unavailable: bool
    #: The activity classes these figures count, so a drill-down opened from
    #: them lists exactly those rows. REQUIRED: `[]` makes the client send no
    #: class filter, and the panel lists more than the chart.
    counted_classes: list[str]


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
    #: `total` over the complete months it covers — the figure Cost of
    #: Living's Take-home quotes. Never re-derive it on the client.
    avg_monthly: Decimal
    months_averaged: int


# ─── Category History ────────────────────────────────────────────────────────


class CategoryHistoryMonth(ApiModel):
    month: date
    #: True on the running month, whose figures are month-to-date
    #: (`domain.dates.ReportWindow`): drawn apart and labelled "so far", never
    #: in an average, a total or a headline. Required, not defaulted — a path
    #: that forgot it would present an unfinished month as a closed one.
    partial_month: bool
    assigned: Decimal
    activity: Decimal
    #: Spent as every plan report counts it (`services/plan_ledger.py`): net
    #: of refunds, and not the money moved in, which `activity` nets away.
    spent: Decimal
    moved_in: Decimal
    #: None for an income category: "Income categories do not hold money", so
    #: their `available` is a lifetime carryover the budget page never draws.
    #: Their monthly activity is meaningful and is still served. None too for
    #: a month before an import whose balance the history cannot reproduce
    #: (`EnvelopeSeries.unrecovered_through`) — absent, not zero.
    available: Decimal | None


class CategoryHistoryReportResponse(ApiModel):
    """One category month by month — assigned, activity, available — the
    figures the budget page shows, read from the same BudgetService."""

    category_id: uuid.UUID
    category_name: str
    months: list[CategoryHistoryMonth]
    #: `spent` averaged over the window's COMPLETE months — the running month
    #: is month-to-date and would pull the average down.
    average_spent: Decimal
    months_averaged: int


# ─── Cost of Living ──────────────────────────────────────────────────────────


class CostOfLivingGroup(ApiModel):
    group_name: str
    monthly_amounts: list[Decimal]
    total: Decimal
    avg_monthly: Decimal
    #: Share of the cost-of-living total, 0-100 — not of income, so the
    #: shares add to 100 and the bar is arithmetic a reader can check.
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
    #: How many months the AVERAGES divide by: every month in `months`, all of
    #: them complete, on every day (`domain.dates.complete_month_window`).
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
    avg_monthly_income: Decimal
    #: Spending outside both tiers over the same window — the Discretionary
    #: report's own rows — so the verdict can lay take-home out whole:
    #: committed + discretionary + left over. None when nothing is tagged, as
    #: that report serves it. The left-over is composed in `necessityView.ts`.
    avg_monthly_discretionary: Decimal | None
    #: The gap between the tiers (cost of living less essentials) and the two
    #: ratios against take-home are NOT served. They are arithmetic on the
    #: three averages above, which the client already has and no backend path
    #: reads, so they are composed once in `necessityView.ts` beside the
    #: sheddable share of the same shape — the boundary rule.
    #: 'bound' | 'tag' | 'all' — how "essential" was decided.
    basis: str
    #: False when no category is tagged Essential or Cost of living (basis
    #: 'all'), so the page can say the figure covers every category rather
    #: than a chosen few.
    tagged: bool
    #: Tagged Essential and still not counted, by class. Tagging a category is
    #: pointing at it, so this fires wherever the basis is a tag or a Guide
    #: binding — the case being "I tagged ten and two showed up".
    class_excluded: list[SpendingClassExcluded] = []
    #: The activity classes these figures count, so a drill-down opened from a
    #: bar totals what the bar says. REQUIRED: `[]` makes the client send no
    #: class filter, and the panel lists more than the bar.
    counted_classes: list[str]
    #: The necessity tier the groups roll up. Membership is per row (debt
    #: principal by class), so the drill sends it too. Required: a drill that
    #: forgets it lists spending the bar never counted.
    necessity_tier: str


# ─── Discretionary ───────────────────────────────────────────────────────────


class DiscretionaryLine(ApiModel):
    """One category's discretionary spending over the window."""

    category_id: uuid.UUID
    category_name: str
    total: Decimal
    avg_monthly: Decimal


class DiscretionaryGroup(ApiModel):
    """A category group's discretionary spending, with its categories."""

    #: None on the Uncategorized line — rows with no category at all, which
    #: the drill opens by `no_category`, never by an empty id list (that
    #: filters nothing and lists the whole window). Required: a group that
    #: forgot it would read as uncategorized.
    group_id: uuid.UUID | None
    group_name: str
    total: Decimal
    avg_monthly: Decimal
    #: Biggest first. Empty on the Uncategorized line, which is one line.
    categories: list[DiscretionaryLine]


class DiscretionaryResponse(ApiModel):
    """Spending outside Cost of living (`activity_class.DISCRETIONARY_ROW`),
    over the Cost of Living report's window."""

    months: list[date]
    #: The window the figures cover, served so a drill-down asks for the same
    #: days rather than re-deriving them.
    window_start: date
    window_end: date
    #: How many months `avg_monthly` divides by: every month in `months`, all
    #: of them complete.
    months_averaged: int
    #: 'tag' | 'all' — the wide tier's basis (`_necessity_scope`).
    basis: str
    #: False when nothing is tagged Essential or Cost of living. Then every
    #: figure below is None and `groups` is empty: "outside Cost of living"
    #: would be the whole burn rate, and the page says what to tag instead.
    tagged: bool
    #: Net of refunds over the window. Required and nullable: None only when
    #: `tagged` is False.
    total: Decimal | None
    avg_monthly: Decimal | None
    #: One per entry of `months`; empty when `tagged` is False.
    monthly_totals: list[Decimal]
    #: The SPENDING class over the same window, which `total` is a part of by
    #: construction. The share between them is composed on the client
    #: (`discretionaryView.ts`) — two served figures, no missing input.
    spending_total: Decimal | None
    #: The Cost of living tier over the same window, positive — the other half
    #: of spending. Cost of living + this report's `total` is `spending_total`
    #: plus the debt payments the tier counts by class; the page says so in
    #: one line (`discretionaryView.tierSumLine`). None when `tagged` is False.
    cost_of_living_total: Decimal | None
    #: Biggest first, the Uncategorized line among them by size.
    groups: list[DiscretionaryGroup]


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
    #: Wanted and not spent — every dropped wish, whether the wait ran its
    #: course or not. The figure the report is for.
    resisted_total: Decimal
    #: How many wishes `resisted_total` sums; the card's count reads this.
    resisted_count: int
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


# ─── Report settings ─────────────────────────────────────────────────────────


class ReportSettings(ApiModel):
    """Per-budget settings that change what the reports count
    (`services/report_settings.py`). The PUT sends the whole object."""

    #: Spread sinking-fund (Long-term expense) bills over twelve months in the
    #: essentials figures. On with no stored choice.
    spread_sinking_funds: bool


# ─── Emergency fund coverage ─────────────────────────────────────────────────


class CoveragePoint(ApiModel):
    month: date
    #: What the fund held at the end of this month.
    fund_balance: Decimal
    #: The essentials figure as of this month (`guide.concepts.essentials_at`),
    #: the one the headline is — the newest point IS the headline.
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
    #: The emergency fund and what it counted — the Essentials report's own.
    fund: EmergencyFundOut
    #: The Essentials report's own runway, quoted rather than recomputed.
    coverage_months: Decimal | None
    #: The Essentials report's own figures, quoted; the targets read `.monthly`.
    essentials: EssentialsFigures
    #: How many Essential categories are also Long-term expense. None means
    #: the spread setting has nothing to spread, so the page hides its toggle
    #: and says why.
    long_term_essentials: int
    target_low: Decimal
    target_high: Decimal
    target_range: tuple[int, int]
    series: list[CoveragePoint] = []
    external_amount: Decimal | None = None
    external_as_of: date | None = None
    current_month: date
