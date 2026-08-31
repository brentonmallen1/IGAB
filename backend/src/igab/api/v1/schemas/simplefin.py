import uuid
from datetime import datetime
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


class SyncResult(ApiModel):
    imported: int
    skipped: int
    matched: int = 0
    review_queued: int = 0
    cleared: int = 0
    removed_pending: int = 0
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
    error: str | None = None


class SyncAllResult(ApiModel):
    """Every connection's sync, totalled.

    One failing connection does not stop the others, so the totals and the
    per-connection list are both needed: "imported 4" is not the whole story
    when a second bank was rate-limited.
    """

    imported: int
    skipped: int
    matched: int = 0
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
