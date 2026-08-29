import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, SimpleFINConnection, Transaction
from igab.domain.bank_posting import FeedRecord, Review
from igab.domain.exceptions import IGABError
from igab.domain.matching import best_payee_similarity, date_proximity, payee_similarity
from igab.integrations.simplefin.client import SimpleFINClient, SimpleFINFeed
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
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_matching_service import (
    TransactionMatchingService,
    calculate_confidence,
)
from igab.services.transaction_service import TransactionCreate, TransactionService
from igab.utils.clock import today_utc

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


@dataclass(frozen=True)
class _MatchDecision:
    action: Literal["auto", "review", "create"]
    candidate: Transaction | None = None
    score: float = 0.0


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
        scored.append(
            (
                txn,
                similarity,
                abs((txn_date - txn.date).days),
                _dedup_score(similarity, txn_date, txn.date),
            )
        )

    best = max(scored, key=lambda s: s[3])
    if best[3] >= DEDUP_AUTO_MATCH_THRESHOLD:
        if best[2] <= DEDUP_AUTO_DATE_MAX_DAYS:
            return _MatchDecision("auto", best[0], best[3])
        # A candidate this strong but this distant (long settlement? weekly
        # recurring charge?) makes every structural shortcut below unsafe —
        # a human sorts it out.
        return _MatchDecision("review", best[0], best[3])

    if is_posted:
        near = [s for s in scored if s[2] <= DEDUP_TIGHT_DATE_DAYS]
        if len(near) == 1:
            return _MatchDecision("auto", near[0][0], near[0][3])
        if len(near) > 1:
            # Same-amount, same-day rows (recurring purchases, split legs):
            # payee similarity is the only disambiguator left. A clear winner
            # takes the match; a near-tie goes to human review over a guess.
            near.sort(key=lambda s: (-s[1], s[2]))
            if near[0][1] - near[1][1] >= DEDUP_TIEBREAK_MARGIN:
                return _MatchDecision("auto", near[0][0], near[0][3])
            return _MatchDecision("review", near[0][0], near[0][3])

    return _MatchDecision("review", best[0], best[3])


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
            "review_queued": 0,
            "cleared": 0,
            "removed_pending": 0,
            "anchored": 0,
        }
        outcomes: list[dict] = []
        for conn in await self.repo.get_all_for_user(user_id):
            result = await self.sync(conn.id, budget_id, sync_type="global")
            for key in totals:
                totals[key] += int(result.get(key) or 0)
            outcomes.append(
                {
                    "connection_id": conn.id,
                    "imported": int(result.get("imported") or 0),
                    "skipped": int(result.get("skipped") or 0),
                    "error": result.get("error"),
                }
            )
        return {**totals, "connections": outcomes}

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

    def _check_rate_limit(self, conn: SimpleFINConnection, sync_type: SyncType) -> None:
        today = today_utc()
        is_new_day = conn.last_request_date != today
        if is_new_day:
            return
        used = conn.global_requests_today if sync_type == "global" else conn.account_requests_today
        limit = GLOBAL_DAILY_LIMIT if sync_type == "global" else ACCOUNT_DAILY_LIMIT
        if used >= limit:
            raise RateLimitError(
                f"Daily {sync_type} sync limit of {limit} requests reached. Resets at midnight UTC."
            )

    async def _bump_request_count(
        self, connection_id: uuid.UUID, conn: SimpleFINConnection, sync_type: SyncType
    ) -> None:
        today = today_utc()
        is_new_day = conn.last_request_date != today
        global_today = 0 if is_new_day else conn.global_requests_today
        account_today = 0 if is_new_day else conn.account_requests_today
        if sync_type == "global":
            global_today += 1
        else:
            account_today += 1
        await self.repo.update(
            connection_id,
            last_request_date=today,
            global_requests_today=global_today,
            account_requests_today=account_today,
        )

    async def _get_lookback_since(
        self, account_ids: list[uuid.UUID], first_sync: bool
    ) -> datetime | None:
        if first_sync:
            return datetime.now(UTC) - timedelta(days=90)
        oldest: date | None = None
        for acct_id in account_ids:
            d = await self.txn_repo.get_oldest_cleared_date_for_account(acct_id)
            if d is not None and (oldest is None or d < oldest):
                oldest = d
        if oldest is None:
            return datetime.now(UTC) - timedelta(days=90)
        return datetime.combine(oldest, datetime.min.time(), tzinfo=UTC) - timedelta(hours=24)

    async def sync(
        self,
        connection_id: uuid.UUID,
        budget_id: uuid.UUID,
        sync_type: SyncType = "global",
        account_simplefin_id: str | None = None,
    ) -> dict:
        conn = await self.repo.get(connection_id)
        if conn is None:
            return {"imported": 0, "skipped": 0, "error": "Connection not found"}

        if not conn.sync_enabled:
            return {"imported": 0, "skipped": 0, "error": "Sync is disabled for this connection"}

        try:
            self._check_rate_limit(conn, sync_type)
        except RateLimitError as e:
            return {"imported": 0, "skipped": 0, "error": str(e)}

        # Determine which accounts to sync
        all_linked = await self.account_repo.get_linked_simplefin_accounts(budget_id)
        if account_simplefin_id:
            targets = [a for a in all_linked if a.simplefin_account_id == account_simplefin_id]
        else:
            targets = [a for a in all_linked if a.simplefin_sync_enabled]

        if not targets:
            return {"imported": 0, "skipped": 0, "error": "No linked accounts to sync"}

        target_ids = [a.id for a in targets]
        # Which accounts have never completed a sync — captured before the
        # flag flips below, because those are the ones whose ledger gets an
        # opening anchor once this run's rows are in.
        first_sync_ids = {a.id for a in targets if not a.first_sync_complete}
        is_first_sync = bool(first_sync_ids)
        since = await self._get_lookback_since(target_ids, is_first_sync)

        try:
            access_url = decrypt(conn.access_url_encrypted)
        except (SimpleFINNotConfigured, SimpleFINKeyMismatch) as exc:
            # Recorded like any other sync failure so the connection carries
            # the reason in the UI, rather than the request 500-ing with
            # "Internal server error" every time the scheduler runs.
            error_msg = str(exc)
            await self.repo.update(
                connection_id,
                last_sync_error=error_msg,
                last_sync_error_at=datetime.now(UTC),
            )
            return {"imported": 0, "skipped": 0, "error": error_msg}

        feed_data = SimpleFINFeed(transactions=[])
        last_error: Exception | None = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                feed_data = await self.client.get_feed(access_url, since=since)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2**attempt))

        if last_error is not None:
            error_msg = str(last_error)
            await self.repo.update(
                connection_id,
                last_sync_error=error_msg,
                last_sync_error_at=datetime.now(UTC),
            )
            return {"imported": 0, "skipped": 0, "error": error_msg}

        txns_raw = feed_data.transactions
        target_sf_ids = {a.simplefin_account_id for a in targets}
        imported = 0
        skipped = 0
        matched = 0
        review_queued = 0
        cleared = 0
        # Rows claimed this run — matched candidates, review candidates, and
        # rows we created. Excluded from later candidate queries so two
        # identical feed rows can never collapse onto the same existing row
        # (or onto each other, for id-less feeds).
        consumed_ids: set[uuid.UUID] = set()
        # Rows this run created, with the feed record each came from — the
        # stale-link pass below looks among them for a re-identified posting.
        created_this_run: list[tuple[Transaction, FeedRecord]] = []

        # How a posting reaches the row it belongs to, in order:
        #   1. Same bank id — the identity path. Most banks keep the id from
        #      pending to posted, so this is the main road, and it involves no
        #      scoring: same amount clears in place; a different amount on a
        #      user-entered row goes to the review queue.
        #   2. New id, same amount — the exact-amount candidate ladder, which
        #      also sees PROVISIONALLY_LINKED rows for a posted record.
        #   3. New id, different amount — the stale-link pass after the loop,
        #      the only step that needs payee similarity.
        for t in txns_raw:
            acct_sf_id = t.get("account_id")
            if acct_sf_id not in target_sf_ids:
                skipped += 1
                continue

            account = next((a for a in targets if a.simplefin_account_id == acct_sf_id), None)
            if account is None:
                skipped += 1
                continue

            feed = _feed_record(t)

            if feed.sync_id is not None:
                existing = await self.txn_repo.find_by_sync_id(account.id, feed.sync_id)
                if existing is not None:
                    consumed_ids.add(existing.id)
                    outcome = await self.txn_service.apply_bank_posting(
                        existing, feed, confirmed=False
                    )
                    if isinstance(outcome, Review):
                        if self.matching_service is None:
                            # Nowhere to queue the question — leave the row
                            # as it is rather than write a duplicate nobody
                            # will be asked about.
                            skipped += 1
                            continue
                        new_txn = await self._import_for_review(budget_id, account, feed, existing)
                        if new_txn is None:
                            skipped += 1
                        else:
                            consumed_ids.add(new_txn.id)
                            created_this_run.append((new_txn, feed))
                            imported += 1
                            review_queued += 1
                    elif "cleared" in outcome.updates:
                        cleared += 1
                    else:
                        # Provenance may have been refreshed; the row's state
                        # did not change.
                        skipped += 1
                    continue

            # Dedup against rows that lack a bank link (YNAB imports, manual
            # entries, CSV imports) — and, for a posted record, rows whose
            # link is to a pending record the bank may have re-identified.
            candidates = await self.txn_repo.find_existing_match_candidates(
                account.id,
                feed.amount,
                feed.date,
                date_window_days=DEDUP_DATE_WINDOW_DAYS,
                exclude_ids=consumed_ids,
                include_provisional=feed.posted,
            )
            decision = _decide_match(feed.payee, feed.date, feed.posted, candidates)

            if decision.action == "auto" and decision.candidate is not None:
                best_match = decision.candidate
                outcome = await self.txn_service.apply_bank_posting(
                    best_match, feed, confirmed=False
                )
                if isinstance(outcome, Review):
                    # Candidates share the feed's exact amount, so this cannot
                    # happen today. If it ever does, the review queue is the
                    # honest fallback — never a silent row beside a linked one.
                    decision = _MatchDecision("review", best_match, decision.score)
                else:
                    if "cleared" in outcome.updates:
                        cleared += 1
                    consumed_ids.add(best_match.id)
                    matched += 1
                    continue

            new_txn = await self._import_feed_row(budget_id, account, feed)
            if new_txn is None:
                skipped += 1
                continue
            consumed_ids.add(new_txn.id)
            created_this_run.append((new_txn, feed))
            if decision.action == "review" and decision.candidate is not None:
                if self.matching_service is not None:
                    await self.matching_service.match_repo.create(
                        synced_transaction_id=new_txn.id,
                        manual_transaction_id=decision.candidate.id,
                        confidence_score=decision.score,
                    )
                    # One review claim per candidate per run: a second
                    # identical feed row must queue against a different
                    # existing row, or import clean.
                    consumed_ids.add(decision.candidate.id)
                    review_queued += 1
            elif self.matching_service is not None:
                await self.matching_service.try_match(new_txn)
            imported += 1

        # After the loop: rows whose bank id vanished from the feed. Only rows
        # inside the fetched window are judged, and only when the feed
        # actually returned data (an empty feed proves nothing).
        removed_pending = 0
        if txns_raw:
            feed_sync_ids = {
                (t.get("id") or "").strip() for t in txns_raw if (t.get("id") or "").strip()
            }
            window_start = since.date() if since is not None else None
            for account in targets:
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

        # Update per-account sync state
        now = datetime.now(UTC)
        for account in targets:
            await self.account_repo.update(
                account.id,
                last_simplefin_sync_at=now,
                first_sync_complete=True,
            )

        await self._bump_request_count(connection_id, conn, sync_type)
        await self.repo.update(
            connection_id,
            last_sync_at=now,
            last_sync_error=None,
            last_sync_error_at=None,
        )

        rate_status = await self._fresh_rate_status(connection_id)
        return {
            "imported": imported,
            "skipped": skipped,
            "matched": matched,
            "review_queued": review_queued,
            "cleared": cleared,
            "removed_pending": removed_pending,
            "anchored": anchored,
            **rate_status,
        }

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
                payee_name="Starting Balance",
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
        exists (the partial unique index on (account_id, sync_id))."""
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
