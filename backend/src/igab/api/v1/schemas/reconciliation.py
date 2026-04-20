import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ReconcileFinishRequest(BaseModel):
    statement_balance: Decimal
    adjustment_transaction_id: uuid.UUID | None = None


class ReconcileAdjustmentRequest(BaseModel):
    adjustment_amount: Decimal


class ReconciliationStatusResponse(BaseModel):
    cleared_balance: Decimal
    uncleared_count: int
    pending_count: int = 0


class ReconciliationSnapshotResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    reconciled_at: datetime
    statement_balance: Decimal
    cleared_balance: Decimal
    adjustment_amount: Decimal
    note: str | None

    model_config = {"from_attributes": True}
