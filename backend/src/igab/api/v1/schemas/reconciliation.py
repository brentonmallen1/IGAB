import uuid
from datetime import datetime
from decimal import Decimal

from igab.api.v1.schemas.base import ApiModel
from igab.domain.money import Money


class ReconcileFinishRequest(ApiModel):
    statement_balance: Money
    adjustment_transaction_id: uuid.UUID | None = None


class ReconcileAdjustmentRequest(ApiModel):
    adjustment_amount: Money


class ReconciliationStatusResponse(ApiModel):
    cleared_balance: Decimal
    uncleared_count: int
    pending_count: int = 0
    #: Cleared rows a pending duplicate review is holding beside the bank's
    #: copy. Required: finish and the adjustment refuse while it is above
    #: zero, and a status that forgot it would offer a Finish that 409s.
    in_review_count: int


class ReconciliationSnapshotResponse(ApiModel):
    id: uuid.UUID
    account_id: uuid.UUID
    reconciled_at: datetime
    statement_balance: Decimal
    cleared_balance: Decimal
    adjustment_amount: Decimal
    note: str | None

    model_config = {"from_attributes": True}
