import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import field_validator

from igab.api.v1.schemas.base import ApiModel
from igab.integrations.simplefin.limits import GLOBAL_DAILY_LIMIT


class SimpleFINSetupRequest(ApiModel):
    setup_token: str


class SimpleFINConfigResponse(ApiModel):
    """Whether this server can store bank credentials at all.

    The client cannot work this out — the encryption key is server-side env —
    so it asks before offering the setup form. All three fields are required:
    a path that forgets one must raise, not report a misconfigured server as
    ready and let the user spend a single-use token finding out.

    ``generate_key_command`` is served rather than written into the frontend so
    the recipe lives in exactly one place (``simplefin.encryption``), beside
    the check that decides whether a key is acceptable.
    """

    configured: bool
    problem: str | None
    generate_key_command: str


class SimpleFINUpdateRequest(ApiModel):
    sync_enabled: bool | None = None
    #: UTC hours (0-23) to sync at; an empty list is "never". Omitted means
    #: "leave the schedule alone" — the route drops None fields.
    sync_hours: list[int] | None = None

    @field_validator("sync_hours")
    @classmethod
    def _canonical_hours(cls, hours: list[int] | None) -> list[int] | None:
        """Sorted, deduplicated, in range, and within the daily budget.

        The cap is the connection's own rate limit rather than a number picked
        here: scheduling a 13th sync would only queue a request the provider
        refuses, and the error should say so at the moment it is set rather
        than silently at 3am.
        """
        if hours is None:
            return None
        if any(h < 0 or h > 23 for h in hours):
            raise ValueError("sync hours must be between 0 and 23")
        unique = sorted(set(hours))
        if len(unique) > GLOBAL_DAILY_LIMIT:
            raise ValueError(
                f"at most {GLOBAL_DAILY_LIMIT} syncs a day — that is this "
                "connection's daily limit with SimpleFIN"
            )
        return unique


class SimpleFINConnectionResponse(ApiModel):
    id: uuid.UUID
    user_id: uuid.UUID
    last_sync_at: datetime | None
    sync_enabled: bool
    sync_hours: list[int]
    global_requests_today: int
    account_requests_today: int
    last_sync_error: str | None
    last_sync_error_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LinkSimpleFINRequest(ApiModel):
    simplefin_account_id: str
    simplefin_account_name: str | None = None


class RefetchRequest(ApiModel):
    """Which connection to ask. An account does not record its connection —
    the link is by bank account id — and the modal already knows which one
    it listed the account from."""

    connection_id: uuid.UUID


class OrphanedLinkInfo(ApiModel):
    """An account whose bank link the feed no longer offers.

    Carries its own suggested replacement so the UI can offer a one-click
    relink rather than making the user match bank strings by eye.
    """

    account_id: uuid.UUID
    account_name: str
    stored_simplefin_id: str
    suggested_feed_id: str | None = None
    suggested_feed_name: str | None = None
    #: The bridge reported an institution needing re-authentication in the
    #: same response and offered no replacement: the account is unreachable,
    #: not gone, and the fix is at the bridge rather than a relink here.
    may_need_auth: bool = False


class BankErrorInfo(ApiModel):
    """One entry from the bridge's `errlist`. `con.auth` means an institution
    needs re-authenticating, and the bridge's guide is explicit that these
    must be shown to the user."""

    code: str
    message: str
    connection_id: str | None = None


class BalanceDriftInfo(ApiModel):
    """A reconciled account whose ledger disagrees with the bank after a sync.

    The bank's figure was always stored; what was missing was anyone saying
    so at the moment it changed. A gap here is the sync's own admission that
    something did not arrive.
    """

    account_id: uuid.UUID
    account_name: str
    bank_balance: Decimal
    ledger_cleared_balance: Decimal


class SyncResult(ApiModel):
    imported: int
    skipped: int
    #: Why each skipped row was skipped. A single count conflating "belonged
    #: to no linked account" with "already filed" is what made a nine-day
    #: outage read as a normal sync.
    skip_reasons: dict[str, int] = {}
    matched: int = 0
    #: Rows whose bank id was replaced wholesale and re-stamped onto the
    #: existing row, rather than imported beside it as a duplicate.
    adopted: int = 0
    review_queued: int = 0
    cleared: int = 0
    removed_pending: int = 0
    orphaned_links: list[OrphanedLinkInfo] = []
    bank_errors: list[BankErrorInfo] = []
    balance_drift: list[BalanceDriftInfo] = []
    #: Accounts whose first sync wrote a Starting Balance row to anchor the
    #: ledger to the bank's reported balance — the 90-day window cannot
    #: carry an older carried balance any other way.
    anchored: int = 0
    error: str | None = None
    global_used: int | None = None
    global_remaining: int | None = None
    account_used: int | None = None
    account_remaining: int | None = None


class ConnectionSyncOutcome(ApiModel):
    """What one connection did during a sync-all."""

    connection_id: uuid.UUID
    imported: int = 0
    skipped: int = 0
    adopted: int = 0
    error: str | None = None
    #: Carried per connection, not just in the totals: a broken link on one
    #: bank is the whole story of that connection's run.
    orphaned_links: list[OrphanedLinkInfo] = []
    bank_errors: list[BankErrorInfo] = []
    balance_drift: list[BalanceDriftInfo] = []


class SyncAllResult(ApiModel):
    """Every connection's sync, totalled.

    One failing connection does not stop the others, so the totals and the
    per-connection list are both needed: "imported 4" is not the whole story
    when a second bank was rate-limited.
    """

    imported: int
    skipped: int
    skip_reasons: dict[str, int] = {}
    matched: int = 0
    adopted: int = 0
    review_queued: int = 0
    cleared: int = 0
    removed_pending: int = 0
    anchored: int = 0
    connections: list[ConnectionSyncOutcome] = []


class RateLimitStatus(ApiModel):
    global_used: int
    global_remaining: int
    account_used: int
    account_remaining: int
    can_sync_global: bool
    can_sync_account: bool
    resets_at: str


class AccountSyncStatusResponse(ApiModel):
    account_id: uuid.UUID
    simplefin_account_id: str | None
    simplefin_sync_enabled: bool
    first_sync_complete: bool
    last_simplefin_sync_at: datetime | None
    simplefin_balance: Decimal | None

    model_config = {"from_attributes": True}


class TransactionMatchResponse(ApiModel):
    id: uuid.UUID
    synced_transaction_id: uuid.UUID
    manual_transaction_id: uuid.UUID
    confidence_score: Decimal
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncRunAccountResponse(ApiModel):
    """What one run did to one account.

    `feed_txn_count == 0` on an account the run was told to sync is the
    signature of a bank link that no longer resolves, and `feed_newest_date`
    is what says an account has quietly stopped receiving anything.
    """

    account_id: uuid.UUID | None = None
    account_name: str | None = None
    simplefin_account_id: str | None = None
    feed_txn_count: int = 0
    feed_oldest_date: date | None = None
    feed_newest_date: date | None = None
    imported: int = 0
    adopted: int = 0
    reidentified: bool = False
    orphaned: bool = False
    bank_balance: Decimal | None = None
    ledger_cleared_balance: Decimal | None = None

    model_config = {"from_attributes": True}


class SyncRunResponse(ApiModel):
    id: uuid.UUID
    connection_id: uuid.UUID | None = None
    trigger: str
    status: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
    bank_errors: list[BankErrorInfo] = []
    orphaned_links: list[OrphanedLinkInfo] = []
    balance_drift: list[BalanceDriftInfo] = []
    feed_txn_count: int = 0
    imported: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = {}
    matched: int = 0
    adopted: int = 0
    cleared: int = 0
    review_queued: int = 0
    removed_pending: int = 0
    anchored: int = 0
    #: Present when the run's writes can be taken back as a unit.
    change_batch_id: uuid.UUID | None = None
    undone_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncRunUndoResult(ApiModel):
    """What "Undo this run" managed. `skipped` are changes left in place
    because the row was edited since — the person's later word wins."""

    undone: int
    skipped: int


class UnservedAccount(ApiModel):
    """An account the latest run was told to sync and the feed offered
    nothing for — no rows and no balance. The link is broken or the
    institution is unreachable; either way the account has stopped."""

    account_id: uuid.UUID
    account_name: str | None = None


class SyncRunDetailResponse(SyncRunResponse):
    accounts: list[SyncRunAccountResponse] = []


class SyncRunListResponse(ApiModel):
    runs: list[SyncRunResponse]
    total_count: int


class SyncHealthResponse(ApiModel):
    """Whether anything about bank sync needs attention right now.

    Read from the most recent run rather than the most recent *problem*: the
    question is "is this broken now", and a stale finding would answer it
    wrongly in both directions.
    """

    orphaned_links: list[OrphanedLinkInfo] = []
    needs_auth: list[BankErrorInfo] = []
    #: Re-checked against the ledger as it is now, not as the run left it,
    #: so deleting the duplicates clears the badge without another sync.
    balance_drift: list[BalanceDriftInfo] = []
    unserved: list[UnservedAccount] = []
    last_run_at: datetime | None = None

    @property
    def clean(self) -> bool:
        return not (self.orphaned_links or self.needs_auth or self.balance_drift or self.unserved)
