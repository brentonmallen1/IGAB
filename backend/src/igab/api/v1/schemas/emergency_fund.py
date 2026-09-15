"""The emergency fund picker (`api/v1/emergency_fund.py`)."""

import uuid
from decimal import Decimal

from pydantic import ConfigDict, Field

from igab.api.v1.schemas.base import ApiModel
from igab.api.v1.schemas.report import EmergencyFundOut
from igab.repositories.category_filters import SavingsMode


class FundAccountCandidateOut(ApiModel):
    """A live, open off-budget account the fund may count
    (`txn_filters.EMERGENCY_FUND_ACCOUNT_CANDIDATE`)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    balance: Decimal
    #: False means choosing it also turns Counts as savings on.
    counts_as_savings: bool
    #: Counted by the fund now.
    member: bool


class EmergencyFundPickerOut(ApiModel):
    fund: EmergencyFundOut
    account_candidates: list[FundAccountCandidateOut]


class FundExternalChoice(ApiModel):
    declared: bool
    #: Canonical decimal string or null — "I have this covered" without a figure
    #: is a complete answer, never zero.
    amount: Decimal | None = Field(default=None, ge=0)
    note: str | None = None


class EmergencyFundChoiceRequest(ApiModel):
    """The picker's one save. Envelopes are a diff against the Emergency fund
    tag's checklist as loaded; accounts are the full chosen set."""

    add_categories: list[uuid.UUID] = []
    remove_categories: list[uuid.UUID] = []
    savings_modes: dict[uuid.UUID, SavingsMode | None] = {}
    account_ids: list[uuid.UUID]
    external: FundExternalChoice
