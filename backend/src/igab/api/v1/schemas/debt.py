import datetime
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from igab.domain.money import Money

DebtType = Literal["mortgage", "auto", "student", "personal", "credit_card", "medical", "other"]


class DebtCreate(BaseModel):
    name: str
    debt_type: DebtType
    interest_rate: Decimal  # annual percent, e.g. 6.25
    minimum_payment: Money
    compounding: str = "monthly"
    # Managed (linked account) XOR unmanaged (manual balance) — not both
    linked_account_id: uuid.UUID | None = None
    manual_balance: Money | None = None
    origination_date: datetime.date | None = None
    original_principal: Money | None = None


class DebtUpdate(BaseModel):
    name: str | None = None
    debt_type: DebtType | None = None
    interest_rate: Decimal | None = None
    minimum_payment: Money | None = None
    compounding: str | None = None
    linked_account_id: uuid.UUID | None = None
    manual_balance: Money | None = None
    origination_date: datetime.date | None = None
    original_principal: Money | None = None


class DebtOut(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    debt_type: str
    mode: Literal["managed", "unmanaged"]
    linked_account_id: uuid.UUID | None
    linked_category_id: uuid.UUID | None
    current_balance: Decimal  # owed, positive
    interest_rate: Decimal
    minimum_payment: Decimal
    compounding: str
    origination_date: datetime.date | None
    original_principal: Decimal | None
    baseline_payoff_date: datetime.date | None
    baseline_never_pays_off: bool
    live_payoff_date: datetime.date | None
    live_never_pays_off: bool
    has_live_projection: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DebtBalanceSnapshotCreate(BaseModel):
    balance: Money
    date: datetime.date | None = None  # default: today


class DebtBalanceSnapshotOut(BaseModel):
    id: uuid.UUID
    debt_id: uuid.UUID
    date: datetime.date
    balance: Decimal
    source: str

    model_config = {"from_attributes": True}


class LinkDebtRequest(BaseModel):
    debt_id: uuid.UUID | None  # null unlinks


class AmortizationMonthOut(BaseModel):
    month_index: int
    date: datetime.date
    payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    balance: Decimal


class BalancePointOut(BaseModel):
    date: datetime.date
    balance: Decimal


class AmortizationResponse(BaseModel):
    current_balance: Decimal
    baseline_schedule: list[AmortizationMonthOut]
    baseline_payoff_date: datetime.date | None
    baseline_never_pays_off: bool
    baseline_total_interest: Decimal
    extra_payment: Decimal | None = None
    extra_schedule: list[AmortizationMonthOut] | None = None
    extra_payoff_date: datetime.date | None = None
    extra_never_pays_off: bool = False
    extra_total_interest: Decimal | None = None
    live_payoff_date: datetime.date | None = None
    live_never_pays_off: bool = False
    live_average_payment: Decimal | None = None
    # Actual balance points before today; populated when from=origination
    history: list[BalancePointOut] = []
