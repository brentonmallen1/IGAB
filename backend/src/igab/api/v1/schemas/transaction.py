import datetime
import re
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from igab.api.v1.schemas.tag import TagOutSimple
from igab.domain.enums import UserClearedStatus
from igab.domain.money import Money


class SplitCreate(BaseModel):
    amount: Money
    category_id: uuid.UUID | None = None
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    memo: str | None = None
    #: An existing line to update in place (PUT …/splits); omit for a new line.
    id: uuid.UUID | None = None


class ConvertToSplitRequest(BaseModel):
    splits: list[SplitCreate]


class ReplaceSplitsRequest(BaseModel):
    """The split's lines as they should be: named lines are updated, unnamed
    ones created, missing ones removed. They must sum to the parent."""

    splits: list[SplitCreate]


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    date: datetime.date
    amount: Money
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: UserClearedStatus = UserClearedStatus.UNCLEARED
    approved: bool = True
    transfer_account_id: uuid.UUID | None = None
    splits: list[SplitCreate] | None = None
    # Link back to the ai_jobs row this draft came from (NL entry). The server
    # derives created_via from the job's kind — provenance is never accepted
    # directly from the client.
    ai_job_id: uuid.UUID | None = None
    # Opt-in mobile capture; powers nearby-payee suggestions. Never money.
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def _location_both_or_neither(self) -> "TransactionCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class TransactionUpdate(BaseModel):
    """PATCH body: omitted fields are untouched; an explicit null clears the
    nullable fields (category_id, payee_id, memo, latitude/longitude)."""

    date: datetime.date | None = None
    amount: Money | None = None
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: UserClearedStatus | None = None
    approved: bool | None = None
    #: Make (or repoint) this row into a transfer to the given account —
    #: explicit null breaks a linked transfer, or clears an orphan leg's
    #: transfer payee. See TransactionService.update for the full semantics.
    #: The editor's "Transfer to account" toggle used to send this and be
    #: silently dropped (extra='ignore' Pydantic default behavior on an
    #: undeclared field): a no-op repair path.
    transfer_account_id: uuid.UUID | None = None
    #: With transfer_account_id: link THIS existing row in the target account
    #: as the partner, instead of searching/creating. The disambiguation the
    #: transfer-candidates endpoint feeds.
    transfer_partner_transaction_id: uuid.UUID | None = None
    #: With transfer_account_id: write the far leg even though the target
    #: account holds rows that could be it. Without this the server refuses
    #: rather than guess — creating alongside the real far leg double-counts
    #: the money. This is the picker's "none of these, create it" answer.
    transfer_create_partner: bool = False
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def _location_both_or_neither(self) -> "TransactionUpdate":
        lat_sent = "latitude" in self.model_fields_set
        lng_sent = "longitude" in self.model_fields_set
        mismatched_null = lat_sent and (self.latitude is None) != (self.longitude is None)
        if lat_sent != lng_sent or mismatched_null:
            raise ValueError("latitude and longitude must be provided together")
        return self

    @model_validator(mode="after")
    def _transfer_fields_consistent(self) -> "TransactionUpdate":
        if "transfer_account_id" in self.model_fields_set and "payee_id" in self.model_fields_set:
            raise ValueError(
                "Send either transfer_account_id or payee_id, not both — "
                "a transfer's payee is derived from its destination"
            )
        if self.transfer_partner_transaction_id is not None and self.transfer_account_id is None:
            raise ValueError("transfer_partner_transaction_id requires transfer_account_id")
        return self


class TransactionClassification(BaseModel):
    """Why a transaction counts the way it does in reports."""

    activity_class: str
    #: Short human label for the class, e.g. "Savings".
    label: str
    #: Stable rule identifier — safe to branch on, unlike the prose.
    reason: str
    #: A sentence completing "This counts as <label> because …".
    explanation: str


class TransactionResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    date: datetime.date
    entered_date: datetime.date | None = None
    #: The amount this row had before the bank's posted amount replaced it
    #: (see `Transaction.entered_amount`); None when the bank never changed it.
    entered_amount: Decimal | None = None
    bank_posted_date: datetime.date | None = None
    amount: Decimal
    bank_amount: Decimal | None = None
    bank_payee: str | None = None
    payee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    #: What this row was filed in before that category was deleted. Provenance
    #: for display only — the register shows "was: Groceries" beside the Needs
    #: Category chip. Never a category: the row is uncategorized, and
    #: `needs_category` below is the field that says so. See
    #: `Transaction.prior_category_id`.
    prior_category_id: uuid.UUID | None = None
    prior_category_name: str | None = None
    #: Server's answer to "does the user still have to file this?", so clients
    #: never re-derive it. Required, not optional: a missing value must fail
    #: here rather than reach the register as a quiet False. See
    #: `Transaction.needs_category` and `NEEDS_CATEGORY`.
    needs_category: bool
    #: The account on the other side of a transfer, or None for a plain
    #: transaction. Server-computed (`COUNTERPART_ACCOUNT_ID` in
    #: txn_filters.py) because a linked leg's payee can be null or wrong and
    #: the partner row may not be loaded client-side. Declared without a
    #: default so the key always serializes — but since None is legal, a path
    #: that skips the loader degrades silently to "not a transfer" instead of
    #: raising like needs_category does. test_transfer_counterpart.py sweeps
    #: the serializing paths for exactly that gap.
    counterpart_account_id: uuid.UUID | None
    memo: str | None
    cleared: str
    approved: bool
    transfer_id: uuid.UUID | None
    parent_transaction_id: uuid.UUID | None
    is_split: bool
    import_id: str | None
    import_description: str | None
    sync_id: str | None
    sync_source: str | None
    #: Where the row came from — see `Transaction.created_via`. None = unknown.
    created_via: str | None = None
    #: The schedule this row was entered from, or None. Declared without a
    #: default so the key always serializes.
    scheduled_transaction_id: uuid.UUID | None
    has_sync_source: bool
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class BudgetTransactionListResponse(BaseModel):
    """Paged drill-down listing; totals cover the full filter match, not just the page."""

    transactions: list[TransactionResponse]
    total_count: int
    total_amount: Decimal


class BulkClearedUpdate(BaseModel):
    transaction_ids: list[uuid.UUID]
    cleared: UserClearedStatus


class BulkCategorize(BaseModel):
    transaction_ids: list[uuid.UUID]
    category_id: uuid.UUID


class BulkDelete(BaseModel):
    transaction_ids: list[uuid.UUID]


class BulkApprove(BaseModel):
    transaction_ids: list[uuid.UUID]


class BulkItemFailure(BaseModel):
    id: uuid.UUID
    reason: str


class BulkActionResult(BaseModel):
    updated: list[uuid.UUID]
    failed: list[BulkItemFailure]
    # Change-log batch covering the whole bulk action, for undo
    batch_id: uuid.UUID | None = None


class DeleteTransactionResult(BaseModel):
    """Returned by transaction delete so the UI can offer toast-undo."""

    batch_id: uuid.UUID


class PendingReviewCount(BaseModel):
    unapproved: int
    uncategorized: int
    unapproved_only: int = 0
    uncategorized_only: int = 0
    both: int = 0
    total: int = 0


class MergeTransactionsRequest(BaseModel):
    transaction_ids: list[uuid.UUID]
    survivor_id: uuid.UUID | None = None


class SimilarTransactionResponse(BaseModel):
    id: uuid.UUID
    date: datetime.date
    amount: Decimal
    payee_id: uuid.UUID | None
    memo: str | None
    cleared: str
    import_description: str | None

    model_config = {"from_attributes": True}


class PayeeCreate(BaseModel):
    name: str


class PayeeUpdate(BaseModel):
    name: str | None = None
    default_category_id: uuid.UUID | None = None
    mapping_samples: str | None = None
    match_pattern: str | None = Field(default=None, max_length=500)

    @field_validator("match_pattern")
    @classmethod
    def validate_match_pattern(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
        return v


class PayeeResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    default_category_id: uuid.UUID | None
    transfer_account_id: uuid.UUID | None
    mapping_samples: str | None
    match_pattern: str | None = None
    tags: list[TagOutSimple] = []

    model_config = {"from_attributes": True}


class PayeeWithCount(PayeeResponse):
    transaction_count: int
    last_used: datetime.date | None = None


class PayeeMergeRequest(BaseModel):
    target_id: uuid.UUID


class PayeeMergeResult(BaseModel):
    """Returned by payee merge so the UI can offer toast-undo."""

    change_id: uuid.UUID


class NearbyPayeeResponse(BaseModel):
    """A payee the user has transacted with near the given point."""

    id: uuid.UUID
    name: str
    default_category_id: uuid.UUID | None
    distance_m: float
    visit_count: int
    last_date: datetime.date


class DuplicatePayeeEntry(BaseModel):
    id: uuid.UUID
    name: str
    transaction_count: int


class DuplicatePayeeGroup(BaseModel):
    """A group of payees that appear to be duplicates based on fuzzy matching."""

    payees: list[DuplicatePayeeEntry]
    similarity: int
