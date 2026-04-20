import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


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
