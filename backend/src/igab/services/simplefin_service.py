import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import SimpleFINConnection, Transaction
from igab.domain.exceptions import IGABError
from igab.integrations.simplefin.client import SimpleFINClient
from igab.integrations.simplefin.encryption import decrypt, encrypt
from igab.repositories.account_repo import AccountRepository
from igab.repositories.simplefin_repo import SimpleFINRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_matching_service import TransactionMatchingService
from igab.services.transaction_service import TransactionCreate, TransactionService

GLOBAL_DAILY_LIMIT = 12
ACCOUNT_DAILY_LIMIT = 12
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubles each attempt

DEDUP_AUTO_MATCH_THRESHOLD = 0.80
DEDUP_REVIEW_THRESHOLD = 0.55
DEDUP_DATE_WINDOW_DAYS = 5


def _payee_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.5  # Neutral when payee unknown
    # WRatio combines ratio, partial_ratio, token_sort, and token_set variants,
    # picking the best score — handles bank descriptions vs cleaned payee names.
    return fuzz.WRatio(a.lower(), b.lower()) / 100.0


def _date_proximity_score(synced: date, existing: date) -> float:
    delta = abs((synced - existing).days)
    if delta > DEDUP_DATE_WINDOW_DAYS:
        return 0.0
    return 1.0 - (delta / (DEDUP_DATE_WINDOW_DAYS + 1))


def _calculate_dedup_score(
    synced_payee: str | None,
    synced_date: date,
    existing_payee: str | None,
    existing_date: date,
) -> float:
    # Amount already exact. Date is weighted low because banks post 2-5 days
    # after YNAB records the due date. Payee carries most of the signal.
    # Weights: date 20%, payee 80%
    return round(
        _date_proximity_score(synced_date, existing_date) * 0.2
        + _payee_similarity(synced_payee, existing_payee) * 0.8,
        4,
    )


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
        access_url = await self.client.claim_access_url(setup_token)
        encrypted = encrypt(access_url)
        return await self.repo.create(user_id=user_id, access_url_encrypted=encrypted)

    async def list_connections(self, user_id: uuid.UUID) -> list[SimpleFINConnection]:
        return await self.repo.get_all_for_user(user_id)

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
        today = date.today()
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
        today = date.today()
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
        today = date.today()
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
        is_first_sync = any(not a.first_sync_complete for a in targets)
        since = await self._get_lookback_since(target_ids, is_first_sync)

        access_url = decrypt(conn.access_url_encrypted)

        txns_raw: list[dict] = []
        last_error: Exception | None = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                txns_raw = await self.client.get_transactions(access_url, since=since)
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

        target_sf_ids = {a.simplefin_account_id for a in targets}
        imported = 0
        skipped = 0
        cleared = 0

        for t in txns_raw:
            acct_sf_id = t.get("account_id")
            if acct_sf_id not in target_sf_ids:
                skipped += 1
                continue

            account = next((a for a in targets if a.simplefin_account_id == acct_sf_id), None)
            if account is None:
                skipped += 1
                continue

            import_id = f"sf:{t.get('id', '')}"
            posted_ts = t.get("posted")
            transacted_ts = t.get("transacted_at")
            timestamp = posted_ts or transacted_ts
            txn_date = (
                datetime.fromtimestamp(timestamp, tz=UTC).date()
                if isinstance(timestamp, (int, float)) and timestamp > 0
                else date.today()
            )
            is_posted = bool(posted_ts and posted_ts > 0)
            new_cleared = "cleared" if is_posted else "pending"

            # Check if already exists (any state)
            existing = await self.txn_repo.find_by_import_id(account.id, import_id)
            if existing is not None:
                # Transition pending → cleared if now posted
                if existing.cleared == "pending" and is_posted:
                    await self.txn_repo.update_cleared(existing.id, "cleared")
                    cleared += 1
                else:
                    skipped += 1
                continue

            # Also check if there's a pending version waiting to be cleared
            pending_existing = await self.txn_repo.find_pending_by_import_id(account.id, import_id)
            if pending_existing is not None:
                if is_posted:
                    await self.txn_repo.update_cleared(pending_existing.id, "cleared")
                    cleared += 1
                else:
                    skipped += 1
                continue

            amount = Decimal(str(t.get("amount", "0")))
            synced_payee = t.get("payee") or t.get("description") or ""

            # Dedup against cleared/reconciled transactions that may lack import_id
            # (e.g. YNAB imports, manual entries, CSV imports)
            candidates = await self.txn_repo.find_existing_match_candidates(
                account.id, amount, txn_date, date_window_days=DEDUP_DATE_WINDOW_DAYS
            )
            best_match: Transaction | None = None
            best_score = 0.0
            if candidates:
                for existing_txn, existing_payee in candidates:
                    score = _calculate_dedup_score(
                        synced_payee, txn_date, existing_payee, existing_txn.date
                    )
                    if score > best_score:
                        best_score, best_match = score, existing_txn

                if best_match is not None and best_score >= DEDUP_AUTO_MATCH_THRESHOLD:
                    updates: dict[str, object] = {
                        "import_id": import_id,
                        "import_description": t.get("description"),
                        "has_sync_source": True,
                    }
                    if best_match.cleared != "reconciled":
                        updates["date"] = txn_date
                        if best_match.cleared in ("pending", "uncleared") and is_posted:
                            updates["cleared"] = "cleared"
                            cleared += 1
                    await self.txn_repo.update(best_match.id, **updates)
                    skipped += 1
                    continue

            near_miss_candidate = (
                best_match
                if best_match is not None and best_score >= DEDUP_REVIEW_THRESHOLD
                else None
            )

            new_txn = await self.txn_service.create(
                budget_id,
                TransactionCreate(
                    account_id=account.id,
                    date=txn_date,
                    amount=amount,
                    payee_name=synced_payee,
                    import_description=t.get("description"),
                    import_id=import_id,
                    cleared=new_cleared,
                    approved=False,
                ),
            )
            if new_txn is not None:
                if near_miss_candidate is not None and self.matching_service is not None:
                    await self.matching_service.match_repo.create(
                        synced_transaction_id=new_txn.id,
                        manual_transaction_id=near_miss_candidate.id,
                        confidence_score=best_score,
                    )
                elif self.matching_service is not None:
                    await self.matching_service.try_match(new_txn)
            imported += 1

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
            "cleared": cleared,
            **rate_status,
        }

    async def _fresh_rate_status(self, connection_id: uuid.UUID) -> dict:
        conn = await self.repo.get(connection_id)
        if conn is None:
            return {}
        return self.get_rate_limit_status(conn)


def _next_midnight_utc() -> str:
    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat()
