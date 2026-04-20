import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from igab.api.v1.schemas.report import IncomeExpenseResponse, SpendingReportResponse
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
) -> SpendingReportResponse:
    today = date.today()
    start = start_date or today.replace(month=1, day=1)
    end = end_date or today
    categories, total = await report_svc.spending_by_category(budget_id, start, end)
    return SpendingReportResponse(categories=categories, total=total)


@router.get("/{budget_id}/reports/income-expense", response_model=IncomeExpenseResponse)
async def income_expense_report(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    report_svc: Annotated[ReportService, Depends(get_report_service)],
    months: int = 12,
) -> IncomeExpenseResponse:
    data = await report_svc.income_vs_expense(budget_id, months)
    return IncomeExpenseResponse(months=data)


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
