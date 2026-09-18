import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, SimpleFINConnection, Transaction
from igab.domain.bank_balance import BalanceDrift, describe_drift, drift_is_a_fault
from igab.domain.bank_identity import (
    FeedAccount,
    LinkAudit,
    LinkedAccount,
    audit_links,
)
from igab.domain.bank_posting import FeedRecord, Review
from igab.domain.enums import SkipReason
from igab.domain.exceptions import IGABError
from igab.domain.matching import (
    DATE_WINDOW_DAYS,
    best_payee_similarity,
    date_proximity,
    payee_similarity,
)
from igab.domain.payee_names import STARTING_BALANCE_PAYEE
from igab.domain.sync_window import SyncWindow, live_window
from igab.domain.transfers import PairableLeg, pair_legs
from igab.integrations.simplefin.client import SimpleFINClient, SimpleFINError, SimpleFINFeed
from igab.integrations.simplefin.encryption import (
    SimpleFINKeyMismatch,
    SimpleFINNotConfigured,
    decrypt,
    encrypt,
    require_configured,
)
from igab.integrations.simplefin.limits import ACCOUNT_DAILY_LIMIT, GLOBAL_DAILY_LIMIT
from igab.repositories.account_repo import AccountRepository
from igab.repositories.simplefin_repo import SimpleFINRepository
from igab.repositories.sync_run_repo import SyncRunRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import snapshot, snapshots_match
from igab.services.transaction_matching_service import (
    TransactionMatchingService,
    calculate_confidence,
)
from igab.services.transaction_service import TransactionCreate, TransactionService
from igab.utils.clock import today_utc

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubles each attempt

DEDUP_AUTO_MATCH_THRESHOLD = 0.80
# How far to search for exact-amount candidates. Wide enough to cover
# settlement lag: a payment the user dates when initiated can post a week+
# later (observed: credit-card payment dated 6/15, posted 6/22).
DEDUP_DATE_WINDOW_DAYS = 10
# Auto-matching is confined to this radius (the date-proximity score curve is
# anchored here too). Beyond it, exact amount + similar payee is as likely a
# recurring charge as a settlement-lagged duplicate — those candidates only
# ever reach the review queue.
DEDUP_AUTO_DATE_MAX_DAYS = 5
# Exact amount + a date this tight is near-certain identity regardless of payee
# (bank descriptors rarely resemble user-renamed payees).
DEDUP_TIGHT_DATE_DAYS = 1
# Payee-similarity margin that resolves a same-day tie between candidates.
DEDUP_TIEBREAK_MARGIN = 0.10
# A user row whose pending bank link vanished is offered for review against a
# posted row this run created when it scores at least this. Review only,
# never auto: the amounts differ by construction (an equal amount would have
# matched in the loop), so a human confirms the tip or the settled hold.
STALE_LINK_REVIEW_THRESHOLD = 0.5


#: What a missing payee counts for here. Neutral rather than zero: a SimpleFIN
#: row often arrives before its payee is resolved, and scoring it zero would
#: stop it deduplicating against a row it genuinely matches. Safe because
#: 0.2 (max date) + 0.8 x 0.5 = 0.6, below the 0.80 auto threshold — a
#: payee-less pair can never auto-merge on date evidence alone. Pinned in
#: test_matching_scores.py.
_UNKNOWN_PAYEE_SCORE = 0.5


def _payee_similarity(a: str | None, b: str | None) -> float:
    return payee_similarity(a, b, unknown=_UNKNOWN_PAYEE_SCORE)


def _date_proximity_score(synced: date, existing: date) -> float:
    return date_proximity(synced, existing, window_days=DEDUP_AUTO_DATE_MAX_DAYS)


def _dedup_score(payee_score: float, synced_date: date, existing_date: date) -> float:
    # Amount already exact. Date is weighted low because banks post 2-5 days
    # after YNAB records the due date. Payee carries most of the signal.
    # Weights: date 20%, payee 80%
    return round(_date_proximity_score(synced_date, existing_date) * 0.2 + payee_score * 0.8, 4)


def _calculate_dedup_score(
    synced_payee: str | None,
    synced_date: date,
    existing_payee: str | None,
    existing_date: date,
) -> float:
    return _dedup_score(_payee_similarity(synced_payee, existing_payee), synced_date, existing_date)


def _comparable_date(txn: Transaction) -> date:
    """The date to compare a row against a feed record on.

    The bank's own posting date when the row has one, because the feed
    record's date is a bank date too and the two are then the same kind of
    fact. A row a person typed has no posting date and is compared on the
    date they entered — which is why the two can sit days apart and still be
    one transaction.

    Without this, a row whose bank posted it on the 25th but which the user
    dated the 16th scored as nine days distant from its own re-issued
    posting, missed the auto threshold, and was written again as a duplicate.
    """
    return txn.bank_posted_date or txn.date


def _row_payee_strings(txn: Transaction, payee_name: str | None) -> list[str | None]:
    """Every string a row keeps for its merchant — the user's payee and the
    bank's own pending strings. See domain.matching.best_payee_similarity."""
    return [payee_name, txn.bank_payee, txn.import_description]


def _feed_record(t: dict) -> FeedRecord:
    """One SimpleFIN feed row as the posting rule reads it."""
    # A missing/empty bank id must never dedup by sync_id ("" would collide
    # every id-less transaction into one row).
    sync_id = (t.get("id") or "").strip() or None
    posted_ts = t.get("posted")
    transacted_ts = t.get("transacted_at")
    timestamp = posted_ts or transacted_ts
    txn_date = (
        datetime.fromtimestamp(timestamp, tz=UTC).date()
        if isinstance(timestamp, (int, float)) and timestamp > 0
        else today_utc()
    )
    return FeedRecord(
        amount=Decimal(str(t.get("amount", "0"))),
        date=txn_date,
        posted=bool(posted_ts and posted_ts > 0),
        payee=t.get("payee") or t.get("description") or None,
        description=t.get("description") or None,
        sync_id=sync_id,
    )


#: Below this, a candidate that carries the bank's OWN descriptor contradicts
#: the feed's rather than merely differing from it, and the structural
#: shortcut (same amount, a day apart, nothing else nearby) may not take it
#: unasked: "BIGGBY COFFEE" and "HOME DEPOT" are two purchases, and merging
#: them loses one. A row a person typed is judged as before — their "Rent"
#: never resembles the bank's "CHECK 1234", and that pair is one payment.
#: The floor applies only where both sides are the bank's words. Two
#: unrelated descriptors score around 0.3 on shared punctuation and store
#: numbers alone; the same merchant under two spellings scores above 0.9.
DEDUP_STRUCTURAL_MIN_PAYEE = 0.5


@dataclass(frozen=True)
class _MatchDecision:
    action: Literal["auto", "review", "create"]
    candidate: Transaction | None = None
    score: float = 0.0
    #: Days between the feed record and the candidate's comparable date.
    days: int = 0


def _decide_match(
    synced_payee: str | None,
    txn_date: date,
    is_posted: bool,
    candidates: list[tuple[Transaction, str | None]],
) -> _MatchDecision:
    """Decide how an incoming bank transaction relates to existing rows.

    Candidates already share the exact amount within the date window. The
    ladder: payee-driven auto-match on combined score, then structural
    auto-match (≤1 day, posted rows only — pending amounts are provisional),
    then review. A candidate is never silently ignored: an unmatched
    exact-amount neighbor left behind is how duplicate rows are born.
    """
    if not candidates:
        return _MatchDecision("create")

    scored = []
    for txn, payee_name in candidates:
        similarity = best_payee_similarity(
            _row_payee_strings(txn, payee_name), synced_payee, unknown=_UNKNOWN_PAYEE_SCORE
        )
        against = _comparable_date(txn)
        scored.append(
            (
                txn,
                similarity,
                abs((txn_date - against).days),
                _dedup_score(similarity, txn_date, against),
                bool(txn.bank_payee or txn.import_description),
            )
        )

    best = max(scored, key=lambda s: s[3])
    if best[3] >= DEDUP_AUTO_MATCH_THRESHOLD:
        if best[2] <= DEDUP_AUTO_DATE_MAX_DAYS:
            return _MatchDecision("auto", best[0], best[3], best[2])
        # A candidate this strong but this distant (long settlement? weekly
        # recurring charge?) makes every structural shortcut below unsafe —
        # a human sorts it out.
        return _MatchDecision("review", best[0], best[3], best[2])

    if is_posted:
        near = [s for s in scored if s[2] <= DEDUP_TIGHT_DATE_DAYS]
        if len(near) == 1:
            txn, similarity, days, score, bank_words = near[0]
            # Same amount, a day apart, nothing else in reach — near-certain
            # identity, unless the bank's own descriptor on the row says
            # otherwise (see DEDUP_STRUCTURAL_MIN_PAYEE).
            if bank_words and similarity < DEDUP_STRUCTURAL_MIN_PAYEE:
                return _MatchDecision("review", txn, score, days)
            return _MatchDecision("auto", txn, score, days)
        if len(near) > 1:
            # Same-amount, same-day rows (recurring purchases, split legs):
            # payee similarity is the only disambiguator left. A clear winner
            # takes the match; a near-tie goes to human review over a guess.
            near.sort(key=lambda s: (-s[1], s[2]))
            if near[0][1] - near[1][1] >= DEDUP_TIEBREAK_MARGIN:
                return _MatchDecision("auto", near[0][0], near[0][3], near[0][2])
            return _MatchDecision("review", near[0][0], near[0][3], near[0][2])

    return _MatchDecision("review", best[0], best[3], best[2])


@dataclass
class _Tally:
    """What one run has done so far — shared by the two posting passes."""

    imported: int = 0
    matched: int = 0
    adopted: int = 0
    review_queued: int = 0
    cleared: int = 0
    skips: Counter[SkipReason] = field(default_factory=Counter)
    imported_by_account: Counter[uuid.UUID] = field(default_factory=Counter)
    adopted_by_account: Counter[uuid.UUID] = field(default_factory=Counter)
    #: Rows claimed this run — matched candidates, review candidates, and
    #: rows we created. Excluded from later candidate queries so two
    #: identical feed rows can never collapse onto the same existing row
    #: (or onto each other, for id-less feeds).
    consumed_ids: set[uuid.UUID] = field(default_factory=set)
    #: Rows this run created, with the feed record each came from — the
    #: stale-link pass looks among them for a re-identified posting.
    created_this_run: list[tuple[Transaction, FeedRecord]] = field(default_factory=list)


def _fault_summary(
    audit: LinkAudit,
    errors: list[SimpleFINError],
    drifts: Sequence[tuple[Account, BalanceDrift]] = (),
) -> str | None:
    """One line for the connection's error field, or None when all is well.

    Orphaned links lead because they are the fault the user can fix and the
    one that silently stops an account importing. `con.auth` follows: the
    bridge is naming an institution whose credentials have lapsed, and the
    guide is explicit that those must be shown. A reconciled account whose
    ledger no longer matches the bank comes last: it is the sync's own
    admission that something did not arrive.
    """
    parts: list[str] = []
    for orphan in audit.orphaned:
        if orphan.suggested_feed_name:
            fix = f' — relink it to "{orphan.suggested_feed_name}"'
        elif orphan.may_need_auth:
            fix = " — an institution needs re-authenticating at the bridge"
        else:
            fix = " — relink it in account settings"
        parts.append(f'"{orphan.account_name}" is no longer offered by the bank{fix}')
    parts.extend(e.message for e in errors if e.needs_auth)
    parts.extend(describe_drift(account.name, drift) for account, drift in drifts)
    return "; ".join(parts) or None


def _drift_records(drifts: list[tuple[Account, BalanceDrift]]) -> list[dict]:
    """The drift list as the run record, the result and the health check carry it."""
    return [
        {
            "account_id": str(account.id),
            "account_name": account.name,
            "bank_balance": str(drift.reported),
            "ledger_cleared_balance": str(drift.ledger_cleared),
        }
        for account, drift in drifts
    ]


class RateLimitError(IGABError):
    pass


SyncType = Literal["global", "account"]


class SimpleFINService:
    def __init__(
        self,
        session: AsyncSession,
        repo: SimpleFINRepository,
        account_repo: AccountRepository,
        txn_repo: TransactionRepository,
        txn_service: TransactionService,
        matching_service: TransactionMatchingService | None = None,
    ) -> None:
        self.session = session
        self.repo = repo
        self.account_repo = account_repo
        self.txn_repo = txn_repo
        self.txn_service = txn_service
        self.matching_service = matching_service
        self.client = SimpleFINClient()

    async def setup(self, user_id: uuid.UUID, setup_token: str) -> SimpleFINConnection:
        # Before the exchange, not after: a setup token is single-use, so a
        # server with no encryption key would otherwise burn the user's token
        # and then refuse to store the result.
        require_configured()
        access_url = await self.client.claim_access_url(setup_token)
        encrypted = encrypt(access_url)
        return await self.repo.create(user_id=user_id, access_url_encrypted=encrypted)

    async def list_connections(self, user_id: uuid.UUID) -> list[SimpleFINConnection]:
        return await self.repo.get_all_for_user(user_id)

    async def sync_all(self, user_id: uuid.UUID, budget_id: uuid.UUID) -> dict:
        """Sync every connection this user has, into one budget.

        One connection failing — rate-limited, credentials rotated, bank down
        — must not stop the rest, so each outcome is collected rather than
        raised. `sync` already reports its own failures as an `error` key and
        records them on the connection, so there is nothing to catch here
        beyond the unexpected.

        The totals and the per-connection list are both returned: "imported 4"
        is not the whole story when a second bank was refused.
        """
        totals = {
            "imported": 0,
            "skipped": 0,
            "matched": 0,
            "adopted": 0,
            "review_queued": 0,
            "cleared": 0,
            "removed_pending": 0,
            "anchored": 0,
        }
        skip_reasons: Counter[str] = Counter()
        outcomes: list[dict] = []
        for conn in await self.repo.get_all_for_user(user_id):
            result = await self.sync(conn.id, budget_id, sync_type="global")
            for key in totals:
                totals[key] += int(result.get(key) or 0)
            skip_reasons.update(result.get("skip_reasons") or {})
            outcomes.append(
                {
                    "connection_id": conn.id,
                    "imported": int(result.get("imported") or 0),
                    "skipped": int(result.get("skipped") or 0),
                    "adopted": int(result.get("adopted") or 0),
                    "error": result.get("error"),
                    # Per connection, not only in the totals: a broken link on
                    # one bank is the whole story of that connection's run,
                    # and a total of "skipped 586" hides which bank it was.
                    "orphaned_links": result.get("orphaned_links") or [],
                    "bank_errors": result.get("bank_errors") or [],
                    "balance_drift": result.get("balance_drift") or [],
                }
            )
        return {**totals, "skip_reasons": dict(skip_reasons), "connections": outcomes}

    async def update_connection(
        self, connection_id: uuid.UUID, **kwargs: object
    ) -> SimpleFINConnection:
        return await self.repo.update(connection_id, **kwargs)

    async def delete(self, connection_id: uuid.UUID) -> None:
        await self.repo.delete(connection_id)

    async def get_remote_accounts(self, connection_id: uuid.UUID) -> list[dict]:
        conn = await self.repo.get(connection_id)
        if conn is None:
            return []
        access_url = decrypt(conn.access_url_encrypted)
        return await self.client.get_accounts(access_url)

    def get_rate_limit_status(self, conn: SimpleFINConnection) -> dict:
        today = today_utc()
        is_new_day = conn.last_request_date != today
        global_used = 0 if is_new_day else conn.global_requests_today
        account_used = 0 if is_new_day else conn.account_requests_today
        return {
            "global_used": global_used,
            "global_remaining": max(0, GLOBAL_DAILY_LIMIT - global_used),
            "account_used": account_used,
            "account_remaining": max(0, ACCOUNT_DAILY_LIMIT - account_used),
            "can_sync_global": global_used < GLOBAL_DAILY_LIMIT,
            "can_sync_account": account_used < ACCOUNT_DAILY_LIMIT,
            "resets_at": _next_midnight_utc(),
        }

    def _check_rate_limit(
        self, conn: SimpleFINConnection, sync_type: SyncType, pending: int = 0
    ) -> None:
        """`pending`: requests this run has already made and not yet counted."""
        today = today_utc()
        is_new_day = conn.last_request_date != today
        used = pending
        if not is_new_day:
            used += (
                conn.global_requests_today if sync_type == "global" else conn.account_requests_today
            )
        limit = GLOBAL_DAILY_LIMIT if sync_type == "global" else ACCOUNT_DAILY_LIMIT
        if used >= limit:
            raise RateLimitError(
                f"Daily {sync_type} sync limit of {limit} requests reached. Resets at midnight UTC."
            )

    async def _bump_request_count(
        self,
        connection_id: uuid.UUID,
        conn: SimpleFINConnection,
        sync_type: SyncType,
        requests: int = 1,
    ) -> None:
        today = today_utc()
        is_new_day = conn.last_request_date != today
        global_today = 0 if is_new_day else conn.global_requests_today
        account_today = 0 if is_new_day else conn.account_requests_today
        if sync_type == "global":
            global_today += requests
        else:
            account_today += requests
        await self.repo.update(
            connection_id,
            last_request_date=today,
            global_requests_today=global_today,
            account_requests_today=account_today,
        )

    async def _lock_connection(self, connection_id: uuid.UUID) -> None:
        """A transaction-scoped advisory lock keyed on the connection."""
        key = int.from_bytes(connection_id.bytes[:8], "big", signed=True)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    async def _fail(
        self,
        connection_id: uuid.UUID,
        budget_id: uuid.UUID,
        sync_type: SyncType,
        started_at: datetime,
        error: str,
        *,
        status: str = "error",
        window: SyncWindow | None = None,
    ) -> dict:
        """A run that could not proceed: recorded on the connection and in
        the sync log, then reported. A quota-throttled hourly run used to
        return an error dict the scheduler discarded — no log line, no error
        on the connection, no run — which is the nine-day failure's shape."""
        await self.repo.update(
            connection_id,
            last_sync_error=error,
            last_sync_error_at=datetime.now(UTC),
        )
        await SyncRunRepository(self.session).create(
            connection_id=connection_id,
            budget_id=budget_id,
            trigger="account" if sync_type == "account" else "global",
            status=status,
            window_start=window.start if window else None,
            window_end=window.end if window else None,
            duration_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            error=error,
            accounts=[],
        )
        logger.warning(
            "simplefin: sync %s connection=%s %s: %s", sync_type, connection_id, status, error
        )
        return {"imported": 0, "skipped": 0, "error": error}

    @staticmethod
    def _lookback_window(targets: list[Account], first_sync: bool) -> SyncWindow:
        """The window to request, from when these accounts last synced.

        Anchored to the *earliest* `last_simplefin_sync_at` among the targets,
        so an account added to an established connection is not shortchanged
        by its neighbours' freshness — and a target with no stamp at all
        means the full window, not "ignore it". A relink clears the stamp
        for exactly this reason; the first version of this dropped missing
        stamps from the minimum, so a relinked account inherited the window
        of the runs that had served it nothing. `domain.sync_window` floors
        the result at the bridge's 90-day cap.
        """
        stamps: list[datetime] = []
        for account in targets:
            if account.last_simplefin_sync_at is None:
                stamps = []
                break
            stamps.append(account.last_simplefin_sync_at)
        return live_window(
            now=datetime.now(UTC),
            last_sync_at=min(stamps) if stamps else None,
            first_sync=first_sync,
        )

    async def _fetch_feed(self, access_url: str, since: datetime) -> SimpleFINFeed:
        """One request to the bridge, retried. Raises the last error."""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                return await self.client.get_feed(access_url, since=since)
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2**attempt))
        assert last_error is not None
        raise last_error

    async def sync(
        self,
        connection_id: uuid.UUID,
        budget_id: uuid.UUID,
        sync_type: SyncType = "global",
        account_simplefin_id: str | None = None,
    ) -> dict:
        started_at = datetime.now(UTC)
        # One sync per connection at a time, for the length of this
        # transaction. The hourly job and a person pressing Sync can land in
        # the same second on different sessions; without this each computes
        # its own candidates for the same feed rows, and the second to commit
        # either duplicates a row or re-points one the first already claimed.
        # Taken before the connection is read, so the request counters this
        # run adds to are the ones the other run left behind.
        await self._lock_connection(connection_id)
        conn = await self.repo.get(connection_id)
        if conn is None:
            return {"imported": 0, "skipped": 0, "error": "Connection not found"}

        if not conn.sync_enabled:
            return {"imported": 0, "skipped": 0, "error": "Sync is disabled for this connection"}

        try:
            self._check_rate_limit(conn, sync_type)
        except RateLimitError as e:
            return await self._fail(
                connection_id, budget_id, sync_type, started_at, str(e), status="rate_limited"
            )

        # Determine which accounts to sync
        all_linked = await self.account_repo.get_linked_simplefin_accounts(budget_id)
        if account_simplefin_id:
            targets = [a for a in all_linked if a.simplefin_account_id == account_simplefin_id]
        else:
            targets = [a for a in all_linked if a.simplefin_sync_enabled]

        if not targets:
            return {"imported": 0, "skipped": 0, "error": "No linked accounts to sync"}

        # Which accounts have never completed a sync — captured before the
        # flag flips below, because those are the ones whose ledger gets an
        # opening anchor once this run's rows are in.
        first_sync_ids = {a.id for a in targets if not a.first_sync_complete}
        is_first_sync = bool(first_sync_ids)
        window = self._lookback_window(targets, is_first_sync)
        since = window.start

        try:
            access_url = decrypt(conn.access_url_encrypted)
        except (SimpleFINNotConfigured, SimpleFINKeyMismatch) as exc:
            # Recorded like any other sync failure so the connection carries
            # the reason in the UI, rather than the request 500-ing with
            # "Internal server error" every time the scheduler runs.
            return await self._fail(connection_id, budget_id, sync_type, started_at, str(exc))

        requests_made = 0
        try:
            feed_data = await self._fetch_feed(access_url, since)
            requests_made += 1
        except Exception as exc:
            return await self._fail(
                connection_id, budget_id, sync_type, started_at, str(exc), window=window
            )

        # Everything this run writes — imports, adoptions, relinks, the rows
        # it removes, the merges it accepts — is one change-log batch, so the
        # run can be taken back as a unit from the sync log. ⌘Z never reaches
        # these (they are not the person's own edits); this is their undo.
        run_batch = self.txn_service.changes.batch()
        run_batch_id = run_batch.__enter__()
        try:
            return await self._sync_locked(
                connection_id,
                budget_id,
                sync_type,
                started_at,
                conn,
                targets,
                first_sync_ids,
                is_first_sync,
                window,
                access_url,
                feed_data,
                requests_made,
                run_batch_id,
            )
        finally:
            run_batch.__exit__(None, None, None)

    async def _sync_locked(
        self,
        connection_id: uuid.UUID,
        budget_id: uuid.UUID,
        sync_type: SyncType,
        started_at: datetime,
        conn: SimpleFINConnection,
        targets: list[Account],
        first_sync_ids: set[uuid.UUID],
        is_first_sync: bool,
        window: SyncWindow,
        access_url: str,
        feed_data: SimpleFINFeed,
        requests_made: int,
        run_batch_id: uuid.UUID | None,
    ) -> dict:
        since = window.start
        # Which bank accounts the feed actually offered, and which of our
        # links still resolve. Run before the loop because an orphaned link
        # explains every skip that follows it, and because a target that
        # matches nothing must not be reported as a clean sync.
        audit = self._audit_links(targets, feed_data)
        if audit.orphaned:
            logger.warning(
                "simplefin: %d account(s) have a bank link the feed no longer offers: %s",
                len(audit.orphaned),
                "; ".join(o.account_name for o in audit.orphaned),
            )

        # Heal what can be healed before importing, so one run both relinks
        # and catches up. Safe only because a re-linked account now adopts its
        # own history instead of duplicating it — without that, this would
        # automate the 277-duplicate failure across every account at once.
        relinked = await self._auto_relink(targets, audit)
        if relinked:
            # The feed in hand was fetched for the days since the runs that
            # served this account nothing. A relinked account needs the full
            # window — the days the broken link missed are exactly what it is
            # owed — so ask again, once, before importing anything. One extra
            # request against the quota, only on the run that heals a link.
            full = self._lookback_window(targets, is_first_sync)
            if full.start < since:
                try:
                    # The first request was checked; this one was not. With
                    # no headroom left the relink stands and the wider fetch
                    # waits for the next run, whose window is the floor
                    # anyway (the stamp is gone).
                    self._check_rate_limit(conn, sync_type, pending=requests_made)
                    window, since = full, full.start
                    feed_data = await self._fetch_feed(access_url, since)
                    requests_made += 1
                except RateLimitError as exc:
                    logger.warning("simplefin: relink refetch deferred to the next run: %s", exc)
                except Exception as exc:
                    await self._bump_request_count(connection_id, conn, sync_type, requests_made)
                    return await self._fail(
                        connection_id, budget_id, sync_type, started_at, str(exc), window=window
                    )
            audit = self._audit_links(targets, feed_data)

        txns_raw = feed_data.transactions
        # The feed's own ids per bank account. A row inside the window whose
        # id is missing here is one the bank has retired — the dedup ladder
        # offers such rows so they adopt the new id instead of being
        # duplicated (txn_filters.orphaned_link).
        feed_ids_by_account = self._feed_sync_ids_by_account(txns_raw)

        target_sf_ids = {a.simplefin_account_id for a in targets}
        tally = _Tally()
        by_sf_id = {a.simplefin_account_id: a for a in targets}
        prepared: list[tuple[Account, FeedRecord]] = []
        for t in txns_raw:
            acct_sf_id = t.get("account_id")
            if acct_sf_id not in target_sf_ids:
                tally.skips[SkipReason.FOREIGN_ACCOUNT] += 1
                continue
            account = by_sf_id.get(acct_sf_id)
            if account is None:
                tally.skips[SkipReason.ACCOUNT_NOT_FOUND] += 1
                continue
            prepared.append((account, _feed_record(t)))

        # How a posting reaches the row it belongs to, in order:
        #   1. Same bank id — the identity path. Most banks keep the id from
        #      pending to posted, so this is the main road, and it involves no
        #      scoring: same amount clears in place; a different amount on a
        #      user-entered row goes to the review queue.
        #   2. New id, same amount — the exact-amount candidate ladder, which
        #      also sees PROVISIONALLY_LINKED rows for a posted record, and
        #      rows in the window whose bank id the feed no longer reports.
        #   3. New id, different amount — the stale-link pass after the loop,
        #      the only step that needs payee similarity.
        #
        # In two passes, because feed order is not evidence. A record whose
        # own twin is a day away must not lose it to a record processed
        # earlier that had no twin and reached out for the nearest one — and
        # having consumed it, sent the next record reaching further still.
        # So every record that can claim a row on its own day claims first;
        # only then may the rest look wider.
        since_date = since.date()
        deferred: list[tuple[Account, FeedRecord]] = []
        for account, feed in prepared:
            feed_ids = feed_ids_by_account.get(account.simplefin_account_id or "", set())
            if not await self._post_feed_row(
                budget_id, account, feed, feed_ids, since_date, tally, strict=True
            ):
                deferred.append((account, feed))
        for account, feed in deferred:
            feed_ids = feed_ids_by_account.get(account.simplefin_account_id or "", set())
            await self._post_feed_row(
                budget_id, account, feed, feed_ids, since_date, tally, strict=False
            )

        imported = tally.imported
        skips = tally.skips
        matched = tally.matched
        adopted = tally.adopted
        review_queued = tally.review_queued
        cleared = tally.cleared
        imported_by_account = tally.imported_by_account
        adopted_by_account = tally.adopted_by_account
        created_this_run = tally.created_this_run

        # After the loop: rows whose bank id vanished from the feed. Only rows
        # inside the fetched window are judged, and only when the feed
        # actually returned data (an empty feed proves nothing).
        removed_pending = 0
        orphaned_ids = {o.account_id for o in audit.orphaned}
        if txns_raw:
            feed_sync_ids = {
                (t.get("id") or "").strip() for t in txns_raw if (t.get("id") or "").strip()
            }
            window_start = since.date() if since is not None else None
            for account in targets:
                # Only accounts this feed actually served. An orphaned account
                # has no rows in the feed at all, so every id it holds looks
                # "vanished" — and this pass deleted its pending rows every
                # hour for as long as the link stayed broken.
                if account.id in orphaned_ids:
                    continue
                # A pending row the sync itself created: the bank dropped the
                # auth, or re-identified it at posting with a changed amount
                # (a same-amount re-id was absorbed in the loop). Recorded, so
                # a category or memo the user put on it comes back with undo.
                stale_rows = await self.txn_repo.find_stale_pending_synced(
                    account.id, "simplefin", window_start, feed_sync_ids
                )
                for stale in stale_rows:
                    await self.txn_service.delete(budget_id, stale.id, source="system")
                    removed_pending += 1

                # A user row linked to a pending record that vanished can
                # never clear through that link. Unlink it, and if a posted
                # row this run created looks like the same purchase, offer the
                # pair for review — the amounts differ by construction.
                fresh = [
                    (txn, f)
                    for txn, f in created_this_run
                    if txn.account_id == account.id and f.posted
                ]
                for row in await self.txn_repo.find_stale_provisional_links(
                    account.id, "simplefin", window_start, feed_sync_ids
                ):
                    await self.txn_service.release_bank_link(row)
                    if self.matching_service is None or not fresh:
                        continue
                    if await self._queue_reidentified_review(row, fresh):
                        review_queued += 1

        # The bank's reported balance, kept every sync (the account page can
        # show drift against the ledger) — and, on an account's FIRST sync,
        # the opening anchor: the window is 90 days, so any balance older
        # than that never imports, and a ledger that is a bare sum of
        # imported rows starts thousands short on a carried-balance card.
        # One uncategorized "Starting Balance" row closes the gap: on a cash
        # account it lands in Ready to Assign, on a card it shows as
        # Uncovered — exactly where pre-history debt belongs.
        anchored = 0
        for account in targets:
            reported = feed_data.balances.get(account.simplefin_account_id or "")
            if reported is None:
                continue
            await self.account_repo.update(account.id, simplefin_balance=reported)
            if account.id in first_sync_ids:
                if await self._anchor_opening_balance(budget_id, account, reported) is not None:
                    anchored += 1

        # Two legs of one movement arrive on two accounts with ordinary bank
        # payees and nothing linking them. Pair them now, while it is still
        # cheap — see domain/transfers.pair_legs for what each unpaired kind
        # costs. Runs last so every row this sync produced (anchors included)
        # is visible to it.
        paired, pairs_for_review = await self._pair_transfer_legs(
            budget_id, [txn for txn, _feed in created_this_run]
        )

        # Does the ledger now agree with the bank? Asked after every row is
        # in, and only of accounts the user reconciles — see
        # domain.bank_balance for why a mortgage's drift is not a fault.
        drifts: list[tuple[Account, BalanceDrift]] = []
        ledger_cleared: dict[uuid.UUID, Decimal] = {}
        for account in targets:
            reported = feed_data.balances.get(account.simplefin_account_id or "")
            if reported is None:
                continue
            cleared_total = await self.account_repo.get_cleared_balance(account.id)
            ledger_cleared[account.id] = cleared_total
            drift = drift_is_a_fault(
                reported, cleared_total, reconciled=account.last_reconciled_at is not None
            )
            if drift is not None:
                drifts.append((account, drift))

        # Update per-account sync state — for the accounts this feed actually
        # served. An orphaned account keeps the stamp of the last run that
        # reached it, so the window a relink asks for starts there. Stamping
        # it anyway is how a relinked account came back with a window that
        # began after the days its broken link had missed.
        now = datetime.now(UTC)
        for account in targets:
            if account.id in orphaned_ids:
                continue
            await self.account_repo.update(
                account.id,
                last_simplefin_sync_at=now,
                first_sync_complete=True,
            )

        await self._bump_request_count(connection_id, conn, sync_type, requests=requests_made)
        # A run that could not reach an account, or that the bridge reported
        # errors for, is not a clean sync — and `last_sync_error` is the one
        # field the settings panel already renders in full. Clearing it on a
        # degraded run is how a broken link stayed invisible for nine days.
        fault = _fault_summary(audit, feed_data.errors, drifts)
        await self.repo.update(
            connection_id,
            last_sync_at=now,
            last_sync_error=fault,
            last_sync_error_at=datetime.now(UTC) if fault else None,
        )

        skipped = sum(skips.values())
        await self._record_run(
            connection_id=connection_id,
            budget_id=budget_id,
            sync_type=sync_type,
            window=window,
            started_at=started_at,
            targets=targets,
            feed=feed_data,
            audit=audit,
            imported_by_account=imported_by_account,
            adopted_by_account=adopted_by_account,
            ledger_cleared=ledger_cleared,
            drifts=drifts,
            fault=fault,
            change_batch_id=run_batch_id,
            counts={
                "feed_txn_count": len(txns_raw),
                "imported": imported,
                "skipped": skipped,
                "matched": matched,
                "adopted": adopted,
                "cleared": cleared,
                "review_queued": review_queued,
                "removed_pending": removed_pending,
                "anchored": anchored,
            },
            skip_reasons={r.value: n for r, n in skips.items()},
        )
        logger.info(
            "simplefin: sync %s connection=%s window_start=%s feed_rows=%d "
            "imported=%d adopted=%d matched=%d cleared=%d skipped=%d (%s)",
            sync_type,
            connection_id,
            since.date() if since else "none",
            len(txns_raw),
            imported,
            adopted,
            matched,
            cleared,
            skipped,
            ", ".join(f"{r.value}={n}" for r, n in sorted(skips.items())) or "none",
        )

        rate_status = await self._fresh_rate_status(connection_id)
        return {
            "imported": imported,
            "skipped": skipped,
            "skip_reasons": {r.value: n for r, n in skips.items()},
            "matched": matched,
            "adopted": adopted,
            "review_queued": review_queued,
            "cleared": cleared,
            "removed_pending": removed_pending,
            "anchored": anchored,
            "paired": paired,
            "pairs_for_review": pairs_for_review,
            "orphaned_links": [
                {
                    "account_id": str(o.account_id),
                    "account_name": o.account_name,
                    "stored_simplefin_id": o.stored_simplefin_id,
                    "suggested_feed_id": o.suggested_feed_id,
                    "suggested_feed_name": o.suggested_feed_name,
                    "may_need_auth": o.may_need_auth,
                }
                for o in audit.orphaned
            ],
            "bank_errors": [
                {"code": e.code, "message": e.message, "connection_id": e.connection_id}
                for e in feed_data.errors
            ],
            "balance_drift": _drift_records(drifts),
            **rate_status,
        }

    async def _post_feed_row(
        self,
        budget_id: uuid.UUID,
        account: Account,
        feed: FeedRecord,
        feed_ids: set[str],
        since_date: date,
        tally: _Tally,
        *,
        strict: bool,
    ) -> bool:
        """Post one feed record. Returns False when `strict` and the record
        could not be settled on its own day — the caller brings it back in
        the second pass, where the wider window is allowed.

        Nothing is written or consumed for a deferred record.
        """
        if feed.sync_id is not None:
            existing = await self.txn_repo.find_by_sync_id(account.id, feed.sync_id)
            if existing is None and await self.txn_repo.was_deleted_by_user(
                account.id, feed.sync_id
            ):
                # The person removed this one. A bank that keeps reporting
                # it is not evidence they changed their mind; the row used to
                # come back on the next run, every run.
                tally.skips[SkipReason.DELETED_BY_USER] += 1
                return True
            if existing is not None:
                tally.consumed_ids.add(existing.id)
                outcome = await self.txn_service.apply_bank_posting(existing, feed, confirmed=False)
                if isinstance(outcome, Review):
                    if self.matching_service is None:
                        # Nowhere to queue the question — leave the row as
                        # it is rather than write a duplicate nobody will be
                        # asked about.
                        tally.skips[SkipReason.NO_MATCHER] += 1
                        return True
                    new_txn = await self._import_for_review(budget_id, account, feed, existing)
                    if new_txn is None:
                        tally.skips[SkipReason.REVIEW_IMPORT_DUPLICATE] += 1
                    else:
                        tally.consumed_ids.add(new_txn.id)
                        tally.created_this_run.append((new_txn, feed))
                        tally.imported += 1
                        tally.imported_by_account[account.id] += 1
                        tally.review_queued += 1
                elif "cleared" in outcome.updates:
                    tally.cleared += 1
                else:
                    # Provenance may have been refreshed; the row's state did
                    # not change.
                    tally.skips[SkipReason.ALREADY_POSTED] += 1
                return True

        # Dedup against rows that lack a bank link (YNAB imports, manual
        # entries, CSV imports); for a posted record, rows whose link is to a
        # pending record the bank may have re-identified; and rows inside the
        # window whose bank id the feed no longer reports.
        candidates = await self.txn_repo.find_existing_match_candidates(
            account.id,
            feed.amount,
            feed.date,
            date_window_days=DEDUP_DATE_WINDOW_DAYS,
            exclude_ids=tally.consumed_ids,
            include_provisional=feed.posted,
            orphaned_feed_sync_ids=feed_ids,
            orphaned_since=since_date,
        )
        decision = _decide_match(feed.payee, feed.date, feed.posted, candidates)
        if strict and not (decision.action == "auto" and decision.days == 0):
            return False

        if decision.action == "auto" and decision.candidate is not None:
            best_match = decision.candidate
            # A candidate that already carries a (now retired) bank id is
            # being re-identified, not cleared: `posting_updates` writes the
            # new `sync_id` as provenance, which a reconciled row accepts
            # because reconciliation locks only amount, date, cleared and
            # account. Its category, payee and memo survive.
            #
            # Adopted, not matched, when the row it claims had already posted
            # under the retired id. A posted record claiming the row that
            # held its own *pending* id is the ordinary re-identification the
            # ladder has always done — a match.
            was_adopted = best_match.sync_id is not None and best_match.cleared in (
                "cleared",
                "reconciled",
            )
            outcome = await self.txn_service.apply_bank_posting(best_match, feed, confirmed=False)
            if isinstance(outcome, Review):
                # Candidates share the feed's exact amount, so this cannot
                # happen today. If it ever does, the review queue is the
                # honest fallback — never a silent row beside a linked one.
                decision = _MatchDecision("review", best_match, decision.score, decision.days)
            else:
                if "cleared" in outcome.updates:
                    tally.cleared += 1
                tally.consumed_ids.add(best_match.id)
                if was_adopted:
                    tally.adopted += 1
                    tally.adopted_by_account[account.id] += 1
                else:
                    tally.matched += 1
                return True

        new_txn = await self._import_feed_row(budget_id, account, feed)
        if new_txn is None:
            tally.skips[SkipReason.DUPLICATE_SYNC_ID] += 1
            return True
        tally.consumed_ids.add(new_txn.id)
        tally.created_this_run.append((new_txn, feed))
        if decision.action == "review" and decision.candidate is not None:
            if self.matching_service is not None:
                await self.matching_service.match_repo.create(
                    synced_transaction_id=new_txn.id,
                    manual_transaction_id=decision.candidate.id,
                    confidence_score=decision.score,
                )
                # One review claim per candidate per run: a second identical
                # feed row must queue against a different existing row, or
                # import clean.
                tally.consumed_ids.add(decision.candidate.id)
                tally.review_queued += 1
        elif self.matching_service is not None:
            await self.matching_service.try_match(new_txn)
        tally.imported += 1
        tally.imported_by_account[account.id] += 1
        return True

    async def _auto_relink(self, targets: list[Account], audit: LinkAudit) -> list[str]:
        """Repoint an orphaned account at the bank account carrying its own name.

        Only an exact name match, and only when exactly one unclaimed account
        has it. A similar name is not evidence: two of one person's brokerage
        accounts score 0.95 against each other, and a wrong relink files one
        account's transactions into another — the worst thing this app can do.
        Anything less certain waits for a person, who gets the suggestion
        prefilled.

        Recorded like a manual relink, so it undoes with Cmd+Z and appears in
        the change log as something that happened rather than something that
        was always true.
        """
        if not audit.orphaned:
            return []
        if not await self._auto_relink_enabled():
            return []

        by_id = {a.id: a for a in targets}
        relinked: list[str] = []
        for orphan in audit.orphaned:
            if not orphan.suggestion_is_exact or not orphan.suggested_feed_id:
                continue
            account = by_id.get(orphan.account_id)
            if account is None:
                continue
            before = snapshot("account", account)
            # The stamp goes too, like the link endpoint's: the window this
            # account is owed starts at the floor, not at the last run that
            # served it nothing.
            updated = await self.account_repo.update(
                account.id,
                simplefin_account_id=orphan.suggested_feed_id,
                simplefin_account_name=orphan.suggested_feed_name,
                last_simplefin_sync_at=None,
            )
            after = snapshot("account", updated)
            if snapshots_match(after, before):
                await self.txn_service.changes.record(
                    budget_id=updated.budget_id,
                    entity_type="account",
                    entity_id=updated.id,
                    action="update",
                    before=before,
                    after=after,
                )
            # `targets` is read again below for the id set and the per-account
            # log rows, so the in-memory row has to move with the database.
            account.simplefin_account_id = orphan.suggested_feed_id
            account.simplefin_account_name = orphan.suggested_feed_name
            account.last_simplefin_sync_at = None
            relinked.append(orphan.account_name)
            logger.warning(
                "simplefin: relinked %r to %r — the bank reissued its account id",
                orphan.account_name,
                orphan.suggested_feed_name,
            )
        return relinked

    async def _auto_relink_enabled(self) -> bool:
        from igab.repositories.settings_repo import SettingsRepository
        from igab.services.settings_service import SettingsService

        raw = await SettingsService(SettingsRepository(self.session)).get("simplefin_auto_relink")
        return (raw or "true").strip().lower() not in ("false", "0", "no", "off")

    async def _record_run(
        self,
        *,
        connection_id: uuid.UUID,
        budget_id: uuid.UUID,
        sync_type: SyncType,
        window: SyncWindow,
        started_at: datetime,
        targets: list[Account],
        feed: SimpleFINFeed,
        audit: LinkAudit,
        imported_by_account: Counter[uuid.UUID],
        adopted_by_account: Counter[uuid.UUID],
        ledger_cleared: dict[uuid.UUID, Decimal],
        drifts: list[tuple[Account, BalanceDrift]],
        fault: str | None,
        change_batch_id: uuid.UUID | None,
        counts: dict[str, int],
        skip_reasons: dict[str, int],
    ) -> None:
        """Leave a record of what this run did.

        Written in the sync's own transaction: the counts are only true if the
        rows they describe were committed, and a run that rolls back should
        take its own record with it. That is the opposite trade from
        `ai/call_log.py`, whose whole point is surviving a failed request —
        the failure paths here record themselves separately, before returning.
        """
        orphaned_ids = {o.account_id for o in audit.orphaned}
        per_account = []
        for account in targets:
            rows = [
                t for t in feed.transactions if t.get("account_id") == account.simplefin_account_id
            ]
            dates = sorted(d for d in (_feed_record(t).date for t in rows) if d is not None)
            per_account.append(
                {
                    "account_id": account.id,
                    "account_name": account.name,
                    "simplefin_account_id": account.simplefin_account_id,
                    "feed_txn_count": len(rows),
                    "feed_oldest_date": dates[0] if dates else None,
                    "feed_newest_date": dates[-1] if dates else None,
                    "imported": imported_by_account[account.id],
                    "adopted": adopted_by_account[account.id],
                    "reidentified": adopted_by_account[account.id] > 0,
                    "orphaned": account.id in orphaned_ids,
                    "bank_balance": feed.balances.get(account.simplefin_account_id or ""),
                    "ledger_cleared_balance": ledger_cleared.get(account.id),
                }
            )

        await SyncRunRepository(self.session).create(
            connection_id=connection_id,
            budget_id=budget_id,
            trigger="account" if sync_type == "account" else "global",
            status="degraded" if fault else "ok",
            window_start=window.start,
            window_end=window.end,
            duration_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            error=fault,
            bank_errors=[
                {"code": e.code, "message": e.message, "connection_id": e.connection_id}
                for e in feed.errors
            ],
            orphaned_links=[
                {
                    "account_id": str(o.account_id),
                    "account_name": o.account_name,
                    "stored_simplefin_id": o.stored_simplefin_id,
                    "suggested_feed_id": o.suggested_feed_id,
                    "suggested_feed_name": o.suggested_feed_name,
                    "may_need_auth": o.may_need_auth,
                }
                for o in audit.orphaned
            ],
            balance_drift=_drift_records(drifts),
            change_batch_id=change_batch_id,
            skip_reasons=skip_reasons,
            accounts=per_account,
            **counts,
        )

    def _audit_links(self, targets: list[Account], feed: SimpleFINFeed) -> LinkAudit:
        """Which of this run's bank links still resolve against the feed."""
        counts: Counter[str] = Counter(
            t["account_id"] for t in feed.transactions if t.get("account_id")
        )
        # Every account the response mentioned, whether or not it had rows —
        # an account with no activity is still claimed, not orphaned.
        feed_ids = set(feed.account_names) | set(feed.balances) | set(counts)
        return audit_links(
            needs_auth=any(e.needs_auth for e in feed.errors),
            linked=[
                LinkedAccount(
                    id=a.id,
                    name=a.name,
                    simplefin_account_id=a.simplefin_account_id,
                    simplefin_account_name=a.simplefin_account_name,
                )
                for a in targets
                if a.simplefin_account_id
            ],
            feed=[
                FeedAccount(id=fid, name=feed.account_names.get(fid), txn_count=counts.get(fid, 0))
                for fid in sorted(feed_ids)
            ],
        )

    @staticmethod
    def _feed_sync_ids_by_account(txns_raw: list[dict]) -> dict[str, set[str]]:
        """The bank ids the feed reported, grouped by its own account id."""
        by_account: dict[str, set[str]] = {}
        for t in txns_raw:
            acct = t.get("account_id")
            sync_id = (t.get("id") or "").strip()
            if acct and sync_id:
                by_account.setdefault(acct, set()).add(sync_id)
        return by_account

    async def _pair_transfer_legs(
        self, budget_id: uuid.UUID, created: list[Transaction]
    ) -> tuple[int, int]:
        """Link the two sides of every movement this sync can be sure about.

        Returns `(linked, left_for_review)`. The decision is
        `domain/transfers.pair_legs`, which is pure and tested without a
        database; this method is the wiring — fetch the window, say which
        categories were this run's own guesses, write the links.

        The window is the created rows' own date span widened by
        `DATE_WINDOW_DAYS` on both sides, because banks post the two sides of
        one movement days apart and the far leg is often already in the ledger
        from an earlier run.

        A category on a row this sync created came from auto-categorization
        moments ago — a guess, clearable to make a correct link. Any other
        category is a person's, and the pair goes to review instead; the
        Accounts page's hygiene findings are where those surface.
        """
        if not created:
            return 0, 0
        span_start = min(t.date for t in created) - timedelta(days=DATE_WINDOW_DAYS)
        span_end = max(t.date for t in created) + timedelta(days=DATE_WINDOW_DAYS)
        rows = await self.txn_repo.list_pairable_legs(budget_id, since=span_start, until=span_end)
        if not rows:
            return 0, 0

        all_accounts = await self.account_repo.get_all(budget_id, include_closed=True)
        accounts = {a.id: a for a in all_accounts}
        guesses = {t.id for t in created}
        legs = [
            PairableLeg(
                id=row.id,
                account_id=row.account_id,
                on_budget=accounts[row.account_id].on_budget,
                date=row.date,
                amount=row.amount,
                categorized=row.category_id is not None,
                category_is_a_guess=row.id in guesses,
            )
            for row in rows
            if row.account_id in accounts
        ]
        confident, review = pair_legs(legs, window_days=DATE_WINDOW_DAYS)

        by_id = {row.id: row for row in rows}
        for pair in confident:
            await self.txn_service.link_legs(
                budget_id,
                by_id[pair.outflow_id],
                by_id[pair.inflow_id],
                clear_categories=pair.clears_categories,
            )
        return len(confident), len(review)

    async def _anchor_opening_balance(
        self, budget_id: uuid.UUID, account: Account, reported: Decimal
    ) -> Transaction | None:
        """One row that makes the ledger equal what the bank says — first
        sync only.

        The fetch window is 90 days and later syncs never reach further
        back, so everything older lives only in the reported balance. Dated
        the day before the oldest imported row (history genuinely starts
        there), reconciled (the bank itself is the source), and
        uncategorized on purpose — the reconciliation adjustment's rule:
        on a cash account the gap belongs in Ready to Assign, on a card it
        is pre-history debt and shows as Uncovered. Through the service, so
        it is change-logged and undoable. None when the ledger already
        agrees.
        """
        ledger = Decimal(str(await self.account_repo.get_balance(account.id)))
        gap = reported - ledger
        if gap == 0:
            return None
        oldest = await self.txn_repo.get_oldest_cleared_date_for_account(account.id)
        anchor_date = oldest - timedelta(days=1) if oldest is not None else today_utc()
        return await self.txn_service.create(
            budget_id,
            TransactionCreate(
                account_id=account.id,
                date=anchor_date,
                amount=gap,
                payee_name=STARTING_BALANCE_PAYEE,
                category_id=None,
                memo="Anchors this account to the balance your bank reported",
                cleared="reconciled",
                approved=True,
                auto_categorize=False,
            ),
        )

    async def _import_feed_row(
        self, budget_id: uuid.UUID, account: Account, feed: FeedRecord
    ) -> Transaction | None:
        """Write a feed record as a new row, or None when its identity already
        exists (the partial unique index on (account_id, sync_id)).

        Rows dated before `account.budget_start_date` arrive uncategorized.
        The bank hands over whatever history it kept, and history from before
        an account joined the budget is opening position: every guess made
        there lands in an envelope that was never funded for it, so the grid
        fills with red for money spent before the budget existed. A card
        carried in with three months of history is the case this exists for —
        that debt belongs in the card's Uncovered, paid down by assigning to
        the card. `NEEDS_CATEGORY` then leaves those rows alone rather than
        asking about them forever, and anyone who wants one in their reports
        can still file it by hand.
        """
        before_start = (
            account.budget_start_date is not None and feed.date < account.budget_start_date
        )
        try:
            # Savepoint so a duplicate-identity IntegrityError skips this row
            # without poisoning the session.
            async with self.session.begin_nested():
                return await self.txn_service.create(
                    budget_id,
                    TransactionCreate(
                        account_id=account.id,
                        date=feed.date,
                        amount=feed.amount,
                        payee_name=feed.payee or "",
                        import_description=feed.description,
                        sync_id=feed.sync_id,
                        sync_source="simplefin",
                        cleared="cleared" if feed.posted else "pending",
                        approved=False,
                        bank_posted_date=feed.date if feed.posted else None,
                        bank_amount=feed.amount,
                        bank_payee=feed.payee,
                        auto_categorize=not before_start,
                    ),
                )
        except IntegrityError:
            return None

    async def _import_for_review(
        self, budget_id: uuid.UUID, account: Account, feed: FeedRecord, existing: Transaction
    ) -> Transaction | None:
        """The bank posted a different amount against a row the user entered.

        Never applied silently. The user's row gives up the bank id, the
        posted record becomes its own row carrying it, and the pair is queued
        for review: accepting merges them with the bank's amount (see
        TransactionService.merge), rejecting keeps both.
        """
        await self.txn_service.release_bank_link(existing)
        new_txn = await self._import_feed_row(budget_id, account, feed)
        if new_txn is not None and self.matching_service is not None:
            await self.matching_service.match_repo.create(
                synced_transaction_id=new_txn.id,
                manual_transaction_id=existing.id,
                confidence_score=await self._review_confidence(feed, existing),
            )
        return new_txn

    async def _review_confidence(self, feed: FeedRecord, row: Transaction) -> float:
        """The review queue's own score for a queued pair, so the modal's
        confidence bar means the same thing whichever path queued it."""
        payee_name = ""
        if self.matching_service is not None and row.payee_id:
            payee = await self.matching_service.payee_repo.get(row.payee_id)
            if payee is not None:
                payee_name = payee.name
        return calculate_confidence(
            feed.amount, feed.date, feed.payee or "", row.amount, row.date, payee_name
        )

    async def _queue_reidentified_review(
        self, row: Transaction, fresh: list[tuple[Transaction, FeedRecord]]
    ) -> bool:
        """Offer a posted row this run created as the re-identified posting of
        a user row whose pending link vanished. Scored on the best of the
        row's payee strings — the user's payee and the bank's own pending
        strings — because a bank's posted descriptor usually matches its
        pending one even when the user renamed the payee."""
        assert self.matching_service is not None
        payee_name: str | None = None
        if row.payee_id:
            payee = await self.matching_service.payee_repo.get(row.payee_id)
            payee_name = payee.name if payee is not None else None
        names = _row_payee_strings(row, payee_name)

        best: tuple[float, Transaction] | None = None
        for txn, feed in fresh:
            if txn.id == row.id or abs((feed.date - row.date).days) > DEDUP_TIGHT_DATE_DAYS:
                continue
            similarity = best_payee_similarity(names, feed.payee, unknown=_UNKNOWN_PAYEE_SCORE)
            score = _dedup_score(similarity, feed.date, row.date)
            if score >= STALE_LINK_REVIEW_THRESHOLD and (best is None or score > best[0]):
                best = (score, txn)
        if best is None:
            return False
        score, synced = best
        if await self.matching_service.match_repo.exists_for_pair(synced.id, row.id):
            return False
        await self.matching_service.match_repo.create(
            synced_transaction_id=synced.id,
            manual_transaction_id=row.id,
            confidence_score=score,
        )
        return True

    async def _fresh_rate_status(self, connection_id: uuid.UUID) -> dict:
        conn = await self.repo.get(connection_id)
        if conn is None:
            return {}
        return self.get_rate_limit_status(conn)


def _next_midnight_utc() -> str:
    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat()
