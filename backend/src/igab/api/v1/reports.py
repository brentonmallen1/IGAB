import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from igab.api.v1.schemas.report import (
    AccountCompositionPoint,
    AccountCompositionResponse,
    BudgetActualItem,
    BudgetActualResponse,
    BurnRatePoint,
    BurnRateResponse,
    CashFlowResponse,
    CategoryPayee,
    DashboardMetrics,
    DayPatternItem,
    DayPatternsResponse,
    IncomeExpenseMonth,
    IncomeExpenseResponse,
    NetWorthPoint,
    NetWorthResponse,
    PayeeAnalysisResponse,
    PayeeSpending,
    PayeeTopCategory,
    PayeeTrend,
    SankeyLink,
    SankeyNode,
    SeasonalityResponse,
    SpendingCategory,
    SpendingGroupedResponse,
    SpendingGroupItem,
    SpendingReportResponse,
    TimelineResponse,
    TimelineTransaction,
    TopCategory,
    VariancePoint,
    VarianceResponse,
    VolatilityItem,
    VolatilityResponse,
)
from igab.dependencies import CurrentUser, get_report_service
from igab.services.report_service import ReportService

router = APIRouter()


@router.get("/{budget_id}/reports/spending", response_model=SpendingReportResponse)
async def spending_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
) -> SpendingReportResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    cat_ids = _parse_uuids(category_ids)
    acct_ids = _parse_uuids(account_ids)
    categories, total = await report_svc.spending_by_category(
        budget_id, start, end, cat_ids, acct_ids
    )
    return SpendingReportResponse(
        categories=[SpendingCategory.model_validate(c) for c in categories], total=total
    )


@router.get("/{budget_id}/reports/income-expense", response_model=IncomeExpenseResponse)
async def income_expense_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> IncomeExpenseResponse:
    data = await report_svc.income_vs_expense(budget_id, months)
    return IncomeExpenseResponse(months=[IncomeExpenseMonth.model_validate(m) for m in data])


@router.get("/{budget_id}/reports/export")
async def export_transactions(
    budget_id: uuid.UUID,
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
    budget_id: uuid.UUID,
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
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> NetWorthResponse:
    data = await report_svc.net_worth_history(budget_id, months)
    return NetWorthResponse(points=[NetWorthPoint.model_validate(p) for p in data])


@router.get("/{budget_id}/reports/account-composition", response_model=AccountCompositionResponse)
async def account_composition_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> AccountCompositionResponse:
    data = await report_svc.account_composition(budget_id, months)
    return AccountCompositionResponse(
        points=[AccountCompositionPoint.model_validate(p) for p in data]
    )


@router.get("/{budget_id}/reports/burn-rate", response_model=BurnRateResponse)
async def burn_rate_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> BurnRateResponse:
    data = await report_svc.burn_rate(budget_id, months)
    return BurnRateResponse(points=[BurnRatePoint.model_validate(p) for p in data])


@router.get("/{budget_id}/reports/cash-flow", response_model=CashFlowResponse)
async def cash_flow_report(
    budget_id: uuid.UUID,
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
    acct_ids = _parse_uuids(account_ids)
    data = await report_svc.cash_flow_sankey(budget_id, start, end, mode, acct_ids)
    return CashFlowResponse(
        nodes=[SankeyNode.model_validate(n) for n in data["nodes"]],
        links=[SankeyLink.model_validate(lnk) for lnk in data["links"]],
        total_income=data["total_income"],
        total_expense=data["total_expense"],
        category_payees={
            cat_id: [CategoryPayee.model_validate(p) for p in payees]
            for cat_id, payees in data["category_payees"].items()
        },
        group_categories={
            grp_id: [CategoryPayee.model_validate(p) for p in cats]
            for grp_id, cats in data["group_categories"].items()
        },
    )


@router.get("/{budget_id}/reports/budget-actual", response_model=BudgetActualResponse)
async def budget_actual_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
) -> BudgetActualResponse:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    cat_ids = _parse_uuids(category_ids)
    data = await report_svc.budget_vs_actual(budget_id, start, end, cat_ids)
    return BudgetActualResponse(
        categories=[BudgetActualItem.model_validate(c) for c in data["categories"]],
        total_assigned=data["total_assigned"],
        total_spent=data["total_spent"],
    )


@router.get("/{budget_id}/reports/variance", response_model=VarianceResponse)
async def variance_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> VarianceResponse:
    data = await report_svc.cumulative_variance(budget_id, months)
    return VarianceResponse(points=[VariancePoint.model_validate(p) for p in data])


@router.get("/{budget_id}/reports/volatility", response_model=VolatilityResponse)
async def volatility_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> VolatilityResponse:
    data = await report_svc.category_volatility(budget_id, months)
    return VolatilityResponse(categories=[VolatilityItem.model_validate(c) for c in data])


@router.get("/{budget_id}/reports/spending-grouped", response_model=SpendingGroupedResponse)
async def spending_grouped_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
) -> SpendingGroupedResponse:
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or today
    cat_ids = _parse_uuids(category_ids)
    acct_ids = _parse_uuids(account_ids)
    items, total = await report_svc.spending_grouped(budget_id, start, end, cat_ids, acct_ids)
    return SpendingGroupedResponse(
        groups=[SpendingGroupItem.model_validate(i) for i in items],
        total=total,
    )


@router.get("/{budget_id}/reports/seasonality", response_model=SeasonalityResponse)
async def seasonality_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> SeasonalityResponse:
    data = await report_svc.seasonality(budget_id, months)
    return SeasonalityResponse(
        cells=data["cells"],
        months=data["months"],
        categories=data["categories"],
    )


@router.get("/{budget_id}/reports/payee-analysis", response_model=PayeeAnalysisResponse)
async def payee_analysis_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 25,
    payee_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
) -> PayeeAnalysisResponse:
    today = date.today()
    start = start_date or today.replace(year=today.year - 1, day=1)
    end = end_date or today
    p_ids = _parse_uuids(payee_ids)
    acct_ids = _parse_uuids(account_ids)
    payees, total = await report_svc.payee_analysis(budget_id, start, end, limit, p_ids, acct_ids)
    return PayeeAnalysisResponse(
        payees=[
            PayeeSpending(
                payee_id=p["payee_id"],
                payee_name=p["payee_name"],
                total=p["total"],
                count=p["count"],
                monthly_trend=[PayeeTrend.model_validate(t) for t in p["monthly_trend"]],
                top_categories=[PayeeTopCategory.model_validate(c) for c in p["top_categories"]],
                is_recurring=p["is_recurring"],
            )
            for p in payees
        ],
        total=total,
    )


@router.get("/{budget_id}/reports/day-patterns", response_model=DayPatternsResponse)
async def day_patterns_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
) -> DayPatternsResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    cat_ids = _parse_uuids(category_ids)
    acct_ids = _parse_uuids(account_ids)
    data = await report_svc.day_patterns(budget_id, start, end, cat_ids, acct_ids)
    return DayPatternsResponse(days=[DayPatternItem.model_validate(d) for d in data])


@router.get("/{budget_id}/reports/large-transactions", response_model=TimelineResponse)
async def timeline_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    category_ids: str | None = Query(None),
    account_ids: str | None = Query(None),
) -> TimelineResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    cat_ids = _parse_uuids(category_ids)
    acct_ids = _parse_uuids(account_ids)
    data = await report_svc.large_transactions(budget_id, start, end, limit, cat_ids, acct_ids)
    return TimelineResponse(transactions=[TimelineTransaction.model_validate(t) for t in data])


def _parse_uuids(value: str | None) -> list[uuid.UUID] | None:
    if not value:
        return None
    try:
        return [uuid.UUID(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError:
        return None
