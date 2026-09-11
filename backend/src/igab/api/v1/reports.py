import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from igab.api.route import CommitRoute
from igab.api.v1.params import parse_uuid_list
from igab.api.v1.schemas.report import (
    AccountCompositionPoint,
    AccountCompositionResponse,
    AnomalyItem,
    AnomalyReportResponse,
    BudgetActualItem,
    BudgetActualResponse,
    BurnRatePoint,
    BurnRateResponse,
    CashFlowResponse,
    CashProjectionEvent,
    CashProjectionPoint,
    CashProjectionResponse,
    CategoryHistoryMonth,
    CategoryHistoryReportResponse,
    CostOfLivingGroup,
    CostOfLivingResponse,
    DashboardMetrics,
    DayPatternItem,
    DayPatternsResponse,
    EmergencyCoverageResponse,
    EssentialsReportResponse,
    IncomeBySourceResponse,
    IncomeExpenseMonth,
    IncomeExpenseResponse,
    IncomeSource,
    LiabilitiesBalancePoint,
    LiabilitiesReportItem,
    LiabilitiesReportResponse,
    NetWorthPoint,
    NetWorthResponse,
    PaydayEffectDay,
    PaydayEffectResponse,
    PayeeAnalysisResponse,
    PayeeSpending,
    PayeeTopCategory,
    PayeeTrend,
    PlanRealityCategory,
    PlanRealityResponse,
    ReportDrains,
    ReportFavoritesResponse,
    ReportFavoritesUpdate,
    ReportRangeResponse,
    SavingsCategory,
    SavingsRateResponse,
    SavingsReportResponse,
    SavingsSummary,
    SavingsUnrecovered,
    SeasonalityResponse,
    SpendingCategory,
    SpendingClassExcluded,
    SpendingGroupedResponse,
    SpendingGroupItem,
    SpendingReportResponse,
    SpendingTrendSeries,
    SpendingTrendsResponse,
    SubscriptionCategory,
    SubscriptionsReportResponse,
    SubscriptionsSummary,
    TimelineResponse,
    TimelineTransaction,
    TopCategory,
    VariancePoint,
    VarianceResponse,
    VolatilityItem,
    VolatilityResponse,
    WishlistDisciplineResponse,
)
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    SessionDep,
    get_budget_filter_repo,
    get_budget_service,
    get_category_repo,
    get_liability_service,
    get_report_favorites_service,
    get_report_service,
    get_tag_repo,
)
from igab.domain.activity_class import SPENDING_WITH_SAVINGS_CLASSES, ActivityClass
from igab.domain.dates import add_months
from igab.repositories.budget_filter_repo import BudgetFilterRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.tag_repo import TagRepository
from igab.services.budget_service import BudgetService
from igab.services.emergency_coverage import EmergencyCoverageService
from igab.services.liability_service import LiabilityService
from igab.services.report_basics import (
    cost_of_living,
    income_by_source,
    spending_trends,
    wishlist_discipline,
)
from igab.services.report_basics import (
    subscriptions_report as subscriptions_report_data,
)
from igab.services.report_favorites import ReportFavoritesService
from igab.services.report_scope import resolve_category_scope
from igab.services.report_service import ReportService


#: Spending reports mean money spent. Saving into a brokerage and paying down a
#: mortgage both leave the budget, but neither is spending, and counting them as
#: such skews every average. Callers that want the fuller picture opt in.
def _spending_classes(include_savings: bool) -> list[ActivityClass] | None:
    if not include_savings:
        return None  # service default: spending only
    return list(SPENDING_WITH_SAVINGS_CLASSES)


#: One bound for every report's month window.
#:
#: There were three: no validation at all on most endpoints, `ge=3, le=24` on
#: plan-vs-reality and `ge=1, le=60` on essentials. The 24 was invisible until
#: the range picker learned to offer longer windows, and then it was a 422 on
#: one report out of nine. The ceiling is deliberately far past any real
#: budget — it exists to refuse an absurd number, not to decide a horizon;
#: what a budget can actually show is `available_range`, served and used by
#: the picker.
MAX_REPORT_MONTHS = 600

ReportMonths = Annotated[int, Query(ge=1, le=MAX_REPORT_MONTHS)]

#: plan-vs-reality reads "chronic" as over-plan in 3+ of the window's last 6
#: months, so a window shorter than 3 has nothing to say. That floor is the
#: report's own rule and stays; only its old 24-month ceiling is gone.
PlanRealityMonths = Annotated[int, Query(ge=3, le=MAX_REPORT_MONTHS)]


#: Bounds for every report parameter that is not a month window.
#:
#: These carried no `Query()` at all, so `limit=-1` was a 500 on one endpoint
#: and a silently wrong 200 on the other, and `window`/`days` were unbounded
#: allocations — `days=100000` asks the projection to build a hundred thousand
#: daily buckets across five hundred simulations. Same reasoning as
#: MAX_REPORT_MONTHS above: a ceiling exists to refuse an absurd number, not to
#: decide a horizon.
ReportLimit = Annotated[int, Query(ge=1, le=500)]
#: A z-score. Below 1 every ordinary month is an anomaly and the report is
#: noise; above 10 nothing is ever flagged.
AnomalyThreshold = Annotated[float, Query(ge=1.0, le=10.0)]
#: Days after a payday to follow. One is a single day; a pay cycle is rarely
#: longer than a month, and the report draws one bar per day.
PaydayWindow = Annotated[int, Query(ge=1, le=31)]
#: Days to project. A year is already well past where a bootstrap of the last
#: 180 days says anything useful.
ProjectionDays = Annotated[int, Query(ge=1, le=365)]


router = APIRouter(route_class=CommitRoute)


@router.get("/{budget_id}/reports/emergency-fund", response_model=EmergencyCoverageResponse)
async def emergency_coverage_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    session: SessionDep,
    months: ReportMonths = 12,
) -> EmergencyCoverageResponse:
    data = await EmergencyCoverageService(session).coverage(budget_id, months=months)
    return EmergencyCoverageResponse(**data)


@router.get("/{budget_id}/reports/favorites", response_model=ReportFavoritesResponse)
async def report_favorites(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: Annotated[ReportFavoritesService, Depends(get_report_favorites_service)],
) -> ReportFavoritesResponse:
    return ReportFavoritesResponse(tabs=await service.favorites(budget_id))


@router.put("/{budget_id}/reports/favorites", response_model=ReportFavoritesResponse)
async def set_report_favorites(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: Annotated[ReportFavoritesService, Depends(get_report_favorites_service)],
    payload: ReportFavoritesUpdate,
) -> ReportFavoritesResponse:
    return ReportFavoritesResponse(tabs=await service.set_favorites(budget_id, payload.tabs))


@router.get("/{budget_id}/reports/range", response_model=ReportRangeResponse)
async def report_range(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
) -> ReportRangeResponse:
    """How far back this budget's reports can look, so the range picker offers
    only windows that exist — and can resolve "All" to a real number."""
    return ReportRangeResponse(**await report_svc.available_range(budget_id))


@router.get("/{budget_id}/reports/spending", response_model=SpendingReportResponse)
async def spending_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
    include_savings: bool = False,
    #: A saved filter: its effective category set (named + tagged) scopes the
    #: report — the same resolution the budget page reads.
    filter_id: uuid.UUID | None = None,
    #: Categories carrying any of these tags join the scope.
    tag_ids: str | None = Query(None),
) -> SpendingReportResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    scope = await resolve_category_scope(
        budget_id,
        category_ids=parse_uuid_list(category_ids),
        filter_id=filter_id,
        tag_ids=parse_uuid_list(tag_ids),
        filter_repo=filter_repo,
        tag_repo=tag_repo,
    )
    acct_ids = parse_uuid_list(account_ids)
    categories, total = await report_svc.spending_by_category(
        budget_id,
        start,
        end,
        scope.category_ids,
        acct_ids,
        _spending_classes(include_savings),
    )
    return SpendingReportResponse(
        categories=[SpendingCategory.model_validate(c) for c in categories], total=total
    )


@router.get("/{budget_id}/reports/income-expense", response_model=IncomeExpenseResponse)
async def income_expense_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> IncomeExpenseResponse:
    data = await report_svc.income_vs_expense(budget_id, months)
    return IncomeExpenseResponse(months=[IncomeExpenseMonth.model_validate(m) for m in data])


@router.get("/{budget_id}/reports/export")
async def export_transactions(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    format: str = "csv",
    start_date: date | None = None,
    end_date: date | None = None,
) -> Response:
    content, content_type = await report_svc.export_transactions(
        budget_id, start_date, end_date, format
    )
    ext = "json" if format == "json" else "csv"
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename=transactions.{ext}"},
    )


@router.get("/{budget_id}/reports/dashboard", response_model=DashboardMetrics)
async def dashboard_metrics(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> DashboardMetrics:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    data = await report_svc.dashboard_metrics(budget_id, start, end)
    return DashboardMetrics(
        **{k: v for k, v in data.items() if k != "top_categories"},
        top_categories=[TopCategory.model_validate(c) for c in data["top_categories"]],
    )


@router.get("/{budget_id}/reports/net-worth", response_model=NetWorthResponse)
async def net_worth_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> NetWorthResponse:
    data = await report_svc.net_worth_history(budget_id, months)
    return NetWorthResponse(
        points=[NetWorthPoint.model_validate(p) for p in data],
        unmanaged_liability_total=data[-1]["unmanaged_liability_total"] if data else Decimal("0"),
        asset_value_total=data[-1]["asset_value_total"] if data else Decimal("0"),
    )


@router.get("/{budget_id}/reports/account-composition", response_model=AccountCompositionResponse)
async def account_composition_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> AccountCompositionResponse:
    data = await report_svc.account_composition(budget_id, months)
    return AccountCompositionResponse(
        points=[AccountCompositionPoint.model_validate(p) for p in data]
    )


@router.get("/{budget_id}/reports/burn-rate", response_model=BurnRateResponse)
async def burn_rate_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> BurnRateResponse:
    data = await report_svc.burn_rate(budget_id, months)
    return BurnRateResponse(points=[BurnRatePoint.model_validate(p) for p in data])


@router.get("/{budget_id}/reports/cash-flow", response_model=CashFlowResponse)
async def cash_flow_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    mode: str = "spent",  # "spent" or "budgeted"
    account_ids: str | None = Query(None),
) -> CashFlowResponse:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    acct_ids = parse_uuid_list(account_ids)
    data = await report_svc.cash_flow_sankey(budget_id, start, end, mode, acct_ids)
    # Validated whole rather than field by field: the hand-built version listed
    # the keys it knew about and silently dropped the three the service had
    # added beside them. Pydantic builds the nested models from the same dicts,
    # and a missing key now raises here instead of shipping a default.
    return CashFlowResponse.model_validate(data)


@router.get("/{budget_id}/reports/budget-actual", response_model=BudgetActualResponse)
async def budget_actual_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    #: A saved filter: its effective category set (named + tagged) scopes the
    #: report — the same resolution the budget page reads.
    filter_id: uuid.UUID | None = None,
    #: Categories carrying any of these tags join the scope.
    tag_ids: str | None = Query(None),
) -> BudgetActualResponse:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    scope = await resolve_category_scope(
        budget_id,
        category_ids=parse_uuid_list(category_ids),
        filter_id=filter_id,
        tag_ids=parse_uuid_list(tag_ids),
        filter_repo=filter_repo,
        tag_repo=tag_repo,
    )
    data = await report_svc.budget_vs_actual(budget_id, start, end, scope.category_ids)
    return BudgetActualResponse(
        categories=[BudgetActualItem.model_validate(c) for c in data["categories"]],
        total_assigned=data["total_assigned"],
        total_spent=data["total_spent"],
    )


@router.get("/{budget_id}/reports/plan-vs-reality", response_model=PlanRealityResponse)
async def plan_vs_reality_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: PlanRealityMonths = 12,
) -> PlanRealityResponse:
    data = await report_svc.plan_vs_reality(budget_id, months)
    return PlanRealityResponse(
        months=data["months"],
        categories=[PlanRealityCategory.model_validate(c) for c in data["categories"]],
        total_assigned=data["total_assigned"],
        total_spent=data["total_spent"],
        chronic_count=data["chronic_count"],
    )


@router.get("/{budget_id}/reports/variance", response_model=VarianceResponse)
async def variance_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> VarianceResponse:
    data = await report_svc.cumulative_variance(budget_id, months)
    return VarianceResponse(points=[VariancePoint.model_validate(p) for p in data])


@router.get("/{budget_id}/reports/volatility", response_model=VolatilityResponse)
async def volatility_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
    amortize: bool = False,
) -> VolatilityResponse:
    """How much each category's monthly spending varies.

    `amortize` spreads each charge forward over the months until the next one,
    which separates a bill with steady cost and irregular timing from a
    category whose cost genuinely swings.
    """
    data = await report_svc.category_volatility(budget_id, months, amortize)
    return VolatilityResponse(
        categories=[VolatilityItem.model_validate(c) for c in data["categories"]],
        amortized=amortize,
        window_start=data["window_start"],
        window_end=data["window_end"],
    )


@router.get("/{budget_id}/reports/spending-grouped", response_model=SpendingGroupedResponse)
async def spending_grouped_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
    include_savings: bool = False,
    #: Roll up by this view's groups instead of the budget's own. A view is an
    #: ARRANGEMENT and the scope below is a PREDICATE — both can be on.
    view_id: uuid.UUID | None = None,
    #: A saved filter: its effective category set (named + tagged) scopes the
    #: report — the same resolution the budget page reads.
    filter_id: uuid.UUID | None = None,
    #: Categories carrying any of these tags join the scope.
    tag_ids: str | None = Query(None),
) -> SpendingGroupedResponse:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    scope = await resolve_category_scope(
        budget_id,
        category_ids=parse_uuid_list(category_ids),
        filter_id=filter_id,
        tag_ids=parse_uuid_list(tag_ids),
        filter_repo=filter_repo,
        tag_repo=tag_repo,
    )
    acct_ids = parse_uuid_list(account_ids)
    items, total, notes = await report_svc.spending_grouped(
        budget_id,
        start,
        end,
        scope.category_ids,
        acct_ids,
        _spending_classes(include_savings),
        view_id=view_id,
    )
    hidden = notes["view_hidden"]
    return SpendingGroupedResponse(
        groups=[SpendingGroupItem.model_validate(i) for i in items],
        total=total,
        view_hidden_categories=hidden["categories"] if hidden else 0,
        view_hidden_total=hidden["total"] if hidden else Decimal("0"),
        class_excluded=[
            SpendingClassExcluded.model_validate(c) for c in notes["class_excluded"] or []
        ],
        view_unavailable=notes["view_unavailable"],
        filter_unavailable=scope.filter_unavailable,
    )


@router.get("/{budget_id}/reports/spending-trends", response_model=SpendingTrendsResponse)
async def spending_trends_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
    include_savings: bool = False,
    #: A saved filter: its effective category set (named + tagged) scopes
    #: the report — the same resolution the budget page reads.
    filter_id: uuid.UUID | None = None,
    #: Categories carrying any of these tags join the scope.
    tag_ids: str | None = Query(None),
) -> SpendingTrendsResponse:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    scope = await resolve_category_scope(
        budget_id,
        category_ids=parse_uuid_list(category_ids),
        filter_id=filter_id,
        tag_ids=parse_uuid_list(tag_ids),
        filter_repo=filter_repo,
        tag_repo=tag_repo,
    )
    data = await spending_trends(
        report_svc,
        budget_id,
        start,
        end,
        scope.category_ids,
        parse_uuid_list(account_ids),
        _spending_classes(include_savings),
    )
    return SpendingTrendsResponse(
        months=data["months"],
        series=[SpendingTrendSeries.model_validate(e) for e in data["series"]],
        monthly_totals=data["monthly_totals"],
        total=data["total"],
        class_excluded=[SpendingClassExcluded.model_validate(c) for c in data["class_excluded"]],
        filter_unavailable=scope.filter_unavailable,
    )


@router.get("/{budget_id}/reports/income-by-source", response_model=IncomeBySourceResponse)
async def income_by_source_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> IncomeBySourceResponse:
    data = await income_by_source(report_svc.session, budget_id, months)
    return IncomeBySourceResponse(
        months=data["months"],
        sources=[IncomeSource.model_validate(e) for e in data["sources"]],
        monthly_totals=data["monthly_totals"],
        total=data["total"],
        avg_monthly=data["avg_monthly"],
        months_averaged=data["months_averaged"],
    )


@router.get("/{budget_id}/reports/category-history", response_model=CategoryHistoryReportResponse)
async def category_history_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    budget_service: Annotated[BudgetService, Depends(get_budget_service)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repo)],
    category_id: uuid.UUID = Query(...),
    months: ReportMonths = 12,
) -> CategoryHistoryReportResponse:
    """One category month by month, from the same BudgetService the budget
    page reads — this endpoint orchestrates, it computes nothing."""
    category = await category_repo.get(category_id)
    if category is None or category.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    today = date.today()
    month_list = [add_months(today.replace(day=1), -i) for i in range(months - 1, -1, -1)]
    # One assembly for the whole span, not one call per month — and
    # `in_system_group` comes off the row rather than being re-derived here
    # from the group repository.
    #
    # "Income categories do not hold money" is the app's own rule, raised by
    # `BudgetService._require_envelope`. Their `available` is a lifetime
    # carryover the budget page never draws, and this report published it as
    # an envelope balance under a docstring promising the budget page's own
    # numbers. Their month-by-month ACTIVITY is meaningful and stays.
    out = [
        CategoryHistoryMonth(
            month=bal.month,
            assigned=bal.assigned,
            activity=bal.activity,
            available=None if bal.in_system_group else bal.available,
        )
        for bal in await budget_service.category_history(category_id, month_list)
    ]
    return CategoryHistoryReportResponse(
        category_id=category_id, category_name=category.name, months=out
    )


@router.get("/{budget_id}/reports/seasonality", response_model=SeasonalityResponse)
async def seasonality_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> SeasonalityResponse:
    data = await report_svc.seasonality(budget_id, months)
    return SeasonalityResponse(
        cells=data["cells"],
        months=data["months"],
        categories=data["categories"],
    )


@router.get("/{budget_id}/reports/essentials", response_model=EssentialsReportResponse)
async def essentials_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> EssentialsReportResponse:
    return EssentialsReportResponse(**await report_svc.essentials_summary(budget_id, months))


@router.get("/{budget_id}/reports/payee-analysis", response_model=PayeeAnalysisResponse)
async def payee_analysis_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: ReportLimit = 25,
    payee_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
) -> PayeeAnalysisResponse:
    today = date.today()
    start = start_date or today.replace(year=today.year - 1, day=1)
    end = end_date or today
    p_ids = parse_uuid_list(payee_ids)
    acct_ids = parse_uuid_list(account_ids)
    payees, total, payee_count, payees_to_80pct = await report_svc.payee_analysis(
        budget_id, start, end, limit, p_ids, acct_ids
    )
    return PayeeAnalysisResponse(
        payees=[
            PayeeSpending(
                payee_id=p["payee_id"],
                payee_name=p["payee_name"],
                total=p["total"],
                count=p["count"],
                pct=p["pct"],
                monthly_trend=[PayeeTrend.model_validate(t) for t in p["monthly_trend"]],
                top_categories=[PayeeTopCategory.model_validate(c) for c in p["top_categories"]],
                is_recurring=p["is_recurring"],
            )
            for p in payees
        ],
        total=total,
        payee_count=payee_count,
        payees_to_80pct=payees_to_80pct,
    )


@router.get("/{budget_id}/reports/day-patterns", response_model=DayPatternsResponse)
async def day_patterns_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
    #: A saved filter: its effective category set (named + tagged) scopes the
    #: report — the same resolution the budget page reads.
    filter_id: uuid.UUID | None = None,
    #: Categories carrying any of these tags join the scope.
    tag_ids: str | None = Query(None),
) -> DayPatternsResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    scope = await resolve_category_scope(
        budget_id,
        category_ids=parse_uuid_list(category_ids),
        filter_id=filter_id,
        tag_ids=parse_uuid_list(tag_ids),
        filter_repo=filter_repo,
        tag_repo=tag_repo,
    )
    acct_ids = parse_uuid_list(account_ids)
    data = await report_svc.day_patterns(budget_id, start, end, scope.category_ids, acct_ids)
    return DayPatternsResponse(
        days=[DayPatternItem.model_validate(d) for d in data["days"]],
        class_excluded=[
            SpendingClassExcluded.model_validate(c) for c in (data["class_excluded"] or [])
        ],
        filter_unavailable=scope.filter_unavailable,
        counted_classes=data["counted_classes"],
    )


@router.get("/{budget_id}/reports/large-transactions", response_model=TimelineResponse)
async def timeline_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    tag_repo: Annotated[TagRepository, Depends(get_tag_repo)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: ReportLimit = 50,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
    #: A saved filter: its effective category set (named + tagged) scopes the
    #: report — the same resolution the budget page reads.
    filter_id: uuid.UUID | None = None,
    #: Categories carrying any of these tags join the scope.
    tag_ids: str | None = Query(None),
) -> TimelineResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    scope = await resolve_category_scope(
        budget_id,
        category_ids=parse_uuid_list(category_ids),
        filter_id=filter_id,
        tag_ids=parse_uuid_list(tag_ids),
        filter_repo=filter_repo,
        tag_repo=tag_repo,
    )
    acct_ids = parse_uuid_list(account_ids)
    data = await report_svc.large_transactions(
        budget_id, start, end, limit, scope.category_ids, acct_ids
    )
    return TimelineResponse(
        transactions=[TimelineTransaction.model_validate(t) for t in data],
        filter_unavailable=scope.filter_unavailable,
    )


@router.get("/{budget_id}/reports/liabilities", response_model=LiabilitiesReportResponse)
async def liabilities_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    liability_svc: Annotated[LiabilityService, Depends(get_liability_service)],
    liability_type: str | None = Query(default=None),
    mode: str | None = Query(default=None),
) -> LiabilitiesReportResponse:
    """Consolidated liability rollup — per-liability deep-dives live on /liabilities/:id."""
    data = await liability_svc.liabilities_report(
        budget_id, liability_type=liability_type, mode=mode
    )
    return LiabilitiesReportResponse(
        items=[LiabilitiesReportItem.model_validate(i) for i in data["items"]],
        total_balance=data["total_balance"],
        total_interest_remaining=data["total_interest_remaining"],
        liabilities_missing_terms=data["liabilities_missing_terms"],
        balance_over_time=[
            LiabilitiesBalancePoint.model_validate(p) for p in data["balance_over_time"]
        ],
        closed_with_balance_count=data["closed_with_balance_count"],
        closed_with_balance_total=data["closed_with_balance_total"],
    )


@router.get("/{budget_id}/reports/subscriptions", response_model=SubscriptionsReportResponse)
async def subscriptions_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> SubscriptionsReportResponse:
    """Recurring charges filed to categories tagged 'subscription', by category."""
    data = await subscriptions_report_data(report_svc.session, budget_id, months)
    return SubscriptionsReportResponse(
        subscriptions=[SubscriptionCategory.model_validate(s) for s in data["subscriptions"]],
        summary=SubscriptionsSummary.model_validate(data["summary"]),
        months=data["months"],
        months_averaged=data["months_averaged"],
    )


@router.get("/{budget_id}/reports/savings-rate", response_model=SavingsRateResponse)
async def savings_rate_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> SavingsRateResponse:
    """How much of what came in was kept. Distinct from /reports/savings, which
    asks what you *budgeted* toward savings; this asks what actually left as
    saving."""
    data = await report_svc.savings_rate(budget_id, months)
    return SavingsRateResponse.model_validate(data)


@router.get("/{budget_id}/reports/savings", response_model=SavingsReportResponse)
async def savings_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> SavingsReportResponse:
    """Savings report — aggregates categories tagged 'savings' or 'long_term_expense'."""
    data = await report_svc.savings_report(budget_id, months)
    return SavingsReportResponse(
        categories=[SavingsCategory.model_validate(c) for c in data["categories"]],
        summary=SavingsSummary.model_validate(data["summary"]),
        months=data["months"],
        drains=ReportDrains.model_validate(data["drains"]),
        unrecovered=[SavingsUnrecovered.model_validate(u) for u in data["unrecovered"]],
    )


@router.get("/{budget_id}/reports/anomalies", response_model=AnomalyReportResponse)
async def anomalies_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
    threshold: AnomalyThreshold = 2.0,
) -> AnomalyReportResponse:
    """Anomaly detection — category-months with spending outside baseline z-score."""
    data = await report_svc.anomalies_report(budget_id, months, threshold)
    return AnomalyReportResponse(
        anomalies=[AnomalyItem.model_validate(a) for a in data["anomalies"]]
    )


@router.get("/{budget_id}/reports/payday-effect", response_model=PaydayEffectResponse)
async def payday_effect_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    window: PaydayWindow = 14,
    months: ReportMonths = 12,
) -> PaydayEffectResponse:
    """Payday effect — average daily spending for N days after income events."""
    data = await report_svc.payday_effect(budget_id, window, months)
    return PaydayEffectResponse(
        days=[PaydayEffectDay.model_validate(d) for d in data["days"]],
        baseline_daily=data["baseline_daily"],
        event_count=data["event_count"],
        payday_floor=data["payday_floor"],
    )


@router.get("/{budget_id}/reports/cash-projection", response_model=CashProjectionResponse)
async def cash_projection_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    days: ProjectionDays = 90,
) -> CashProjectionResponse:
    """Cash projection — fan chart with deterministic and stochastic layers."""
    data = await report_svc.cash_projection(budget_id, days)
    return CashProjectionResponse(
        start_balance=data["start_balance"],
        points=[CashProjectionPoint.model_validate(p) for p in data["points"]],
        events=[CashProjectionEvent.model_validate(e) for e in data["events"]],
        goes_negative_date=data.get("goes_negative_date"),
    )


@router.get("/{budget_id}/reports/cost-of-living", response_model=CostOfLivingResponse)
async def cost_of_living_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: ReportMonths = 12,
) -> CostOfLivingResponse:
    """The two necessity tiers and the gap between them, against take-home."""
    data = await cost_of_living(report_svc.session, budget_id, months)
    return CostOfLivingResponse(
        months=data["months"],
        window_start=data["window_start"],
        window_end=data["window_end"],
        months_averaged=data["months_averaged"],
        groups=[CostOfLivingGroup.model_validate(g) for g in data["groups"]],
        avg_monthly_cost_of_living=data["avg_monthly_cost_of_living"],
        avg_monthly_essentials=data["avg_monthly_essentials"],
        avg_monthly_non_essential=data["avg_monthly_non_essential"],
        avg_monthly_income=data["avg_monthly_income"],
        required_ratio=data["required_ratio"],
        essentials_ratio=data["essentials_ratio"],
        basis=data["basis"],
        tagged=data["tagged"],
        class_excluded=[SpendingClassExcluded.model_validate(c) for c in data["class_excluded"]],
        counted_classes=data["counted_classes"],
        necessity_tier=data["necessity_tier"],
    )


@router.get("/{budget_id}/reports/wishlist", response_model=WishlistDisciplineResponse)
async def wishlist_discipline_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
) -> WishlistDisciplineResponse:
    """What the cooling-off period did. All time, because a habit measured
    over twelve months forgets the wish you talked yourself out of two years
    ago."""
    return WishlistDisciplineResponse.model_validate(
        await wishlist_discipline(report_svc.session, budget_id)
    )
