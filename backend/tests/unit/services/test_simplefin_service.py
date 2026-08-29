"""
Tests for SimpleFIN integration:
  - Rate limit enforcement (global / account quotas, daily reset)
  - Lookback calculation (90d first sync, 24h subsequent)
  - Pending → cleared transition
  - Deduplication via import_id
  - Sync return values and error recording

Tests for TransactionMatchingService:
  - Confidence scoring (amount, date, payee components)
  - Auto-accept threshold
  - Pending match creation below threshold
  - Match acceptance and rejection
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from igab.integrations.simplefin.client import SimpleFINFeed
from igab.services.simplefin_service import (
    ACCOUNT_DAILY_LIMIT,
    DEDUP_AUTO_MATCH_THRESHOLD,
    GLOBAL_DAILY_LIMIT,
    RateLimitError,
    SimpleFINService,
    _decide_match,
)
from igab.services.transaction_matching_service import (
    AUTO_ACCEPT_THRESHOLD,
    TransactionMatchingService,
    _amount_score,
    _date_score,
    _payee_similarity,
    calculate_confidence,
)
from igab.services.transaction_service import TransactionService
from igab.utils.clock import today_utc

# ─── Helpers ──────────────────────────────────────────────────────────────────


def D(s: str) -> Decimal:
    return Decimal(s)


def make_connection(
    *,
    sync_enabled: bool = True,
    global_requests_today: int = 0,
    account_requests_today: int = 0,
    last_request_date: date | None = None,
) -> MagicMock:
    conn = MagicMock()
    conn.id = uuid.uuid4()
    conn.sync_enabled = sync_enabled
    conn.global_requests_today = global_requests_today
    conn.account_requests_today = account_requests_today
    conn.last_request_date = last_request_date or today_utc()
    conn.last_sync_at = None
    conn.access_url_encrypted = "encrypted"
    return conn


def make_account(
    *,
    simplefin_account_id: str = "sf-acct-1",
    simplefin_sync_enabled: bool = True,
    first_sync_complete: bool = True,
    budget_id: uuid.UUID | None = None,
    budget_start_date: date | None = None,
) -> MagicMock:
    acct = MagicMock()
    acct.id = uuid.uuid4()
    acct.budget_id = budget_id or uuid.uuid4()
    acct.simplefin_account_id = simplefin_account_id
    acct.simplefin_sync_enabled = simplefin_sync_enabled
    acct.first_sync_complete = first_sync_complete
    # Explicit: a bare MagicMock attribute is not None, so the import path's
    # "did this row predate the account?" check would compare a date against a
    # Mock and raise. The default is the real default — no start date set.
    acct.budget_start_date = budget_start_date
    return acct


def make_transaction(
    *,
    amount: str = "-50.00",
    date_: date | None = None,
    payee_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    import_id: str | None = None,
    sync_id: str | None = None,
    sync_source: str | None = None,
    cleared: str = "cleared",
    linked_transaction_id: uuid.UUID | None = None,
    parent_transaction_id: uuid.UUID | None = None,
    is_split: bool = False,
    transfer_id: uuid.UUID | None = None,
) -> MagicMock:
    txn = MagicMock()
    txn.id = uuid.uuid4()
    txn.amount = D(amount)
    txn.date = date_ or today_utc()
    txn.entered_date = None
    txn.entered_amount = None
    txn.bank_posted_date = None
    # Explicit None, not MagicMock auto-attributes: the posting rule drops
    # unchanged values, and an auto-attribute compares unequal to everything.
    txn.bank_amount = None
    txn.bank_payee = None
    txn.payee_id = payee_id
    txn.category_id = category_id
    txn.import_id = import_id
    txn.import_description = None
    txn.sync_id = sync_id
    txn.sync_source = sync_source
    txn.cleared = cleared
    txn.has_sync_source = False
    txn.is_deleted = False
    txn.is_split = is_split
    txn.transfer_id = transfer_id
    txn.linked_transaction_id = linked_transaction_id
    txn.parent_transaction_id = parent_transaction_id
    txn.account_id = uuid.uuid4()
    return txn


# ─── Rate Limiting ─────────────────────────────────────────────────────────────


class TestRateLimitCheck:
    def _make_svc(self) -> SimpleFINService:
        return SimpleFINService(
            session=MagicMock(),
            repo=MagicMock(),
            account_repo=MagicMock(),
            txn_repo=MagicMock(),
            txn_service=MagicMock(),
        )

    def test_allows_first_request_of_day(self) -> None:
        svc = self._make_svc()
        conn = make_connection(global_requests_today=0, last_request_date=today_utc())
        svc._check_rate_limit(conn, "global")  # should not raise

    def test_blocks_global_at_limit(self) -> None:
        svc = self._make_svc()
        conn = make_connection(
            global_requests_today=GLOBAL_DAILY_LIMIT,
            last_request_date=today_utc(),
        )
        with pytest.raises(RateLimitError):
            svc._check_rate_limit(conn, "global")

    def test_blocks_account_at_limit(self) -> None:
        svc = self._make_svc()
        conn = make_connection(
            account_requests_today=ACCOUNT_DAILY_LIMIT,
            last_request_date=today_utc(),
        )
        with pytest.raises(RateLimitError):
            svc._check_rate_limit(conn, "account")

    def test_allows_just_under_limit(self) -> None:
        svc = self._make_svc()
        conn = make_connection(
            global_requests_today=GLOBAL_DAILY_LIMIT - 1,
            last_request_date=today_utc(),
        )
        svc._check_rate_limit(conn, "global")  # should not raise

    def test_resets_on_new_day(self) -> None:
        svc = self._make_svc()
        yesterday = today_utc() - timedelta(days=1)
        # Was at limit yesterday — should be allowed today (new day resets)
        conn = make_connection(
            global_requests_today=GLOBAL_DAILY_LIMIT,
            last_request_date=yesterday,
        )
        svc._check_rate_limit(conn, "global")  # should not raise

    def test_global_limit_does_not_affect_account(self) -> None:
        svc = self._make_svc()
        conn = make_connection(
            global_requests_today=GLOBAL_DAILY_LIMIT,
            account_requests_today=0,
            last_request_date=today_utc(),
        )
        svc._check_rate_limit(conn, "account")  # should not raise

    def test_account_limit_does_not_affect_global(self) -> None:
        svc = self._make_svc()
        conn = make_connection(
            global_requests_today=0,
            account_requests_today=ACCOUNT_DAILY_LIMIT,
            last_request_date=today_utc(),
        )
        svc._check_rate_limit(conn, "global")  # should not raise


class TestRateLimitStatus:
    def _make_svc(self) -> SimpleFINService:
        return SimpleFINService(
            session=MagicMock(),
            repo=MagicMock(),
            account_repo=MagicMock(),
            txn_repo=MagicMock(),
            txn_service=MagicMock(),
        )

    def test_status_on_fresh_day(self) -> None:
        svc = self._make_svc()
        conn = make_connection(global_requests_today=3, last_request_date=today_utc())
        status = svc.get_rate_limit_status(conn)
        assert status["global_used"] == 3
        assert status["global_remaining"] == GLOBAL_DAILY_LIMIT - 3
        assert status["can_sync_global"] is True

    def test_status_resets_on_new_day(self) -> None:
        svc = self._make_svc()
        yesterday = today_utc() - timedelta(days=1)
        conn = make_connection(
            global_requests_today=GLOBAL_DAILY_LIMIT,
            last_request_date=yesterday,
        )
        status = svc.get_rate_limit_status(conn)
        assert status["global_used"] == 0
        assert status["global_remaining"] == GLOBAL_DAILY_LIMIT
        assert status["can_sync_global"] is True


# ─── Lookback Calculation ─────────────────────────────────────────────────────


class TestLookbackCalculation:
    @pytest.fixture
    def svc(self) -> SimpleFINService:
        s = SimpleFINService(
            session=MagicMock(),
            repo=MagicMock(),
            account_repo=MagicMock(),
            txn_repo=MagicMock(),
            txn_service=MagicMock(),
        )
        return s

    @pytest.mark.asyncio
    async def test_first_sync_uses_90_days(self, svc: SimpleFINService) -> None:
        since = await svc._get_lookback_since(account_ids=[uuid.uuid4()], first_sync=True)
        assert since is not None
        expected = datetime.now(UTC) - timedelta(days=90)
        assert abs((since - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_subsequent_sync_uses_oldest_cleared_minus_24h(
        self, svc: SimpleFINService
    ) -> None:
        acct_id = uuid.uuid4()
        oldest = today_utc() - timedelta(days=10)
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(return_value=oldest)

        since = await svc._get_lookback_since(account_ids=[acct_id], first_sync=False)
        assert since is not None
        expected = datetime.combine(oldest, datetime.min.time(), tzinfo=UTC) - timedelta(hours=24)
        assert abs((since - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_subsequent_sync_falls_back_to_90_days_when_no_cleared(
        self, svc: SimpleFINService
    ) -> None:
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(return_value=None)
        since = await svc._get_lookback_since(account_ids=[uuid.uuid4()], first_sync=False)
        assert since is not None
        expected = datetime.now(UTC) - timedelta(days=90)
        assert abs((since - expected).total_seconds()) < 5


# ─── Sync Flow ────────────────────────────────────────────────────────────────


class TestSyncFlow:
    def _make_svc(self) -> SimpleFINService:
        svc = SimpleFINService(
            session=AsyncMock(),
            repo=AsyncMock(),
            account_repo=AsyncMock(),
            txn_repo=AsyncMock(),
            txn_service=AsyncMock(),
        )
        # begin_nested is used as an async context manager (savepoint per row)
        svc.session.begin_nested = MagicMock(return_value=AsyncMock())
        # The posting rule is written by TransactionService. Give the mocked
        # service the real writer, bound to this test's mocked repo, so the
        # assertions below can watch txn_repo.update as they always have.
        real = TransactionService(
            session=AsyncMock(),
            transaction_repo=svc.txn_repo,
            account_repo=AsyncMock(),
            category_repo=AsyncMock(),
            payee_repo=AsyncMock(),
        )
        svc.txn_service.apply_bank_posting = real.apply_bank_posting
        svc.txn_service.release_bank_link = real.release_bank_link
        svc.txn_repo.get_splits = AsyncMock(return_value=[])
        # The after-loop passes iterate these — default to nothing stale
        svc.txn_repo.find_stale_pending_synced = AsyncMock(return_value=[])
        svc.txn_repo.find_stale_provisional_links = AsyncMock(return_value=[])
        return svc

    @pytest.mark.asyncio
    async def test_returns_error_when_connection_not_found(self) -> None:
        svc = self._make_svc()
        svc.repo.get = AsyncMock(return_value=None)
        result = await svc.sync(uuid.uuid4(), uuid.uuid4())
        assert result["error"] == "Connection not found"

    @pytest.mark.asyncio
    async def test_returns_error_when_sync_disabled(self) -> None:
        svc = self._make_svc()
        conn = make_connection(sync_enabled=False)
        svc.repo.get = AsyncMock(return_value=conn)
        result = await svc.sync(conn.id, uuid.uuid4())
        assert "disabled" in result["error"]

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_sync(self) -> None:
        svc = self._make_svc()
        conn = make_connection(
            global_requests_today=GLOBAL_DAILY_LIMIT,
            last_request_date=today_utc(),
        )
        svc.repo.get = AsyncMock(return_value=conn)
        result = await svc.sync(conn.id, uuid.uuid4(), sync_type="global")
        assert result["error"] is not None
        assert "limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_deduplication_skips_existing_import_id(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        existing_txn = make_transaction(import_id="sf:txn-1")
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=existing_txn)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-25.00",
                "description": "STARBUCKS",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, budget_id)

        assert result["imported"] == 0
        assert result["skipped"] == 1
        svc.txn_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_to_cleared_transition(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        pending_txn = make_transaction(import_id="sf:txn-1", cleared="pending")

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        # find_by_sync_id returns the existing pending transaction
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=pending_txn)
        svc.txn_repo.update = AsyncMock()
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        posted_ts = int(datetime.now(UTC).timestamp())
        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": posted_ts,  # now has a post date → cleared
                "amount": "-25.00",
                "description": "STARBUCKS",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, budget_id)

        # Posted values win: cleared flips AND the amount updates to the
        # bank's posted figure (-25.00 vs the pending -50.00).
        svc.txn_repo.update.assert_called_once()
        args, kwargs = svc.txn_repo.update.call_args
        assert args[0] == pending_txn.id
        assert kwargs["cleared"] == "cleared"
        assert kwargs["amount"] == D("-25.00")
        assert result["cleared"] == 1
        assert result["imported"] == 0

    @pytest.mark.asyncio
    async def test_new_transaction_imported(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        new_txn = make_transaction()

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=new_txn)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        posted_ts = int(datetime.now(UTC).timestamp())
        raw_txns = [
            {
                "id": "txn-new",
                "account_id": account.simplefin_account_id,
                "posted": posted_ts,
                "amount": "-99.50",
                "description": "WHOLE FOODS",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, budget_id)

        assert result["imported"] == 1
        assert result["skipped"] == 0
        svc.txn_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_pending_transaction_created_with_pending_status(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        new_txn = make_transaction(cleared="pending")

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(return_value=None)
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=new_txn)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-pending",
                "account_id": account.simplefin_account_id,
                "posted": 0,  # not yet posted
                "transacted_at": int(datetime.now(UTC).timestamp()),
                "amount": "-25.00",
                "description": "PENDING HOLD",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, budget_id)

        call_args = svc.txn_service.create.call_args
        create_data = call_args[0][1]
        assert create_data.cleared == "pending"

    @pytest.mark.asyncio
    async def test_api_error_recorded_and_retried(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(return_value=None)
        svc.repo.update = AsyncMock(return_value=conn)

        error = Exception("Connection refused")
        with (
            patch.object(svc.client, "get_feed", AsyncMock(side_effect=error)),
            patch("igab.services.simplefin_service.asyncio.sleep", AsyncMock()),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, budget_id)

        assert result["error"] is not None
        # update should record the error
        update_calls = svc.repo.update.call_args_list
        error_call = next(
            (c for c in update_calls if "last_sync_error" in c.kwargs),
            None,
        )
        assert error_call is not None

    @pytest.mark.asyncio
    async def test_sync_uses_payee_field_over_description(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        new_txn = make_transaction()

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=new_txn)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-11.30",
                "description": "PURCHASE BISCUITVILLE GRAHAM        NC CARD3951",
                "payee": "Biscuitville",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, budget_id)

        call_args = svc.txn_service.create.call_args
        create_data = call_args[0][1]
        assert create_data.payee_name == "Biscuitville"

    @pytest.mark.asyncio
    async def test_sync_falls_back_to_description_when_no_payee_field(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        new_txn = make_transaction()

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=new_txn)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-25.00",
                "description": "WHOLE FOODS MARKET",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, budget_id)

        call_args = svc.txn_service.create.call_args
        create_data = call_args[0][1]
        assert create_data.payee_name == "WHOLE FOODS MARKET"

    @pytest.mark.asyncio
    async def test_sync_uses_empty_string_when_both_fields_missing(self) -> None:
        svc = self._make_svc()
        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        new_txn = make_transaction()

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=new_txn)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-10.00",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, budget_id)

        call_args = svc.txn_service.create.call_args
        create_data = call_args[0][1]
        assert create_data.payee_name == ""

    @pytest.mark.asyncio
    async def test_sync_invokes_matching_service_for_new_transactions(self) -> None:
        svc = self._make_svc()
        matching_svc = AsyncMock()
        svc.matching_service = matching_svc

        budget_id = uuid.uuid4()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        new_txn = make_transaction()

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=new_txn)
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-50.00",
                "payee": "Starbucks",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, budget_id)

        matching_svc.try_match.assert_called_once_with(new_txn)

    # ─── find_existing_match dedup and cleared-state advancement ─────────────

    def _base_sync_mocks(
        self,
        svc: SimpleFINService,
        account: MagicMock,
        conn: MagicMock,
    ) -> None:
        """Wire up the common mocks needed for a sync call."""
        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=today_utc() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.update = AsyncMock()
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)

    def _posted_raw_txn(self, account: MagicMock) -> dict:
        return {
            "id": "txn-match",
            "account_id": account.simplefin_account_id,
            "posted": int(datetime.now(UTC).timestamp()),
            "amount": "-50.00",
            "description": "GROCERY",
        }

    @pytest.mark.asyncio
    async def test_find_existing_match_counts_as_matched_without_importing(self) -> None:
        """When fuzzy-match finds an existing transaction, no new import is created."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id="sf:txn-match", cleared="cleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["imported"] == 0
        assert result["matched"] == 1
        assert result["skipped"] == 0
        svc.txn_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_find_existing_match_stamps_import_id_when_missing(self) -> None:
        """When match has no import_id, it gets stamped with the SimpleFIN import_id."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id=None, cleared="cleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        svc.txn_repo.update.assert_called_once()
        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert call_kwargs.get("sync_id") == "txn-match"
        assert call_kwargs.get("sync_source") == "simplefin"

    @pytest.mark.asyncio
    async def test_sync_stamps_sync_id_while_preserving_import_id(self) -> None:
        """When matching a YNAB-imported transaction (has import_id), stamps sync_id but preserves import_id."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        # Transaction imported from YNAB (has import_id, no sync_id)
        existing = make_transaction(import_id="csv:existing123", sync_id=None, cleared="cleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        # Should stamp sync_id but NOT touch import_id (preserved on model, not in update)
        svc.txn_repo.update.assert_called_once()
        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert call_kwargs.get("sync_id") == "txn-match"
        assert call_kwargs.get("sync_source") == "simplefin"
        assert "import_id" not in call_kwargs
        # The user's ledger date is never rewritten by a match.
        assert "date" not in call_kwargs
        assert "entered_date" not in call_kwargs
        assert call_kwargs.get("bank_posted_date") == today_utc()

    @pytest.mark.asyncio
    async def test_find_existing_match_advances_pending_to_cleared_when_posted(self) -> None:
        """A fuzzy-matched pending transaction advances to cleared when SimpleFIN shows it posted."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id=None, cleared="pending")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        svc.txn_repo.update.assert_called_once()
        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert call_kwargs.get("cleared") == "cleared"
        assert call_kwargs.get("sync_id") == "txn-match"
        assert call_kwargs.get("sync_source") == "simplefin"
        assert result["cleared"] == 1
        assert result["imported"] == 0

    @pytest.mark.asyncio
    async def test_find_existing_match_advances_uncleared_to_cleared_when_posted(self) -> None:
        """A fuzzy-matched uncleared transaction advances to cleared when SimpleFIN shows it posted."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id=None, cleared="uncleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert call_kwargs.get("cleared") == "cleared"
        assert result["cleared"] == 1

    @pytest.mark.asyncio
    async def test_find_existing_match_no_clear_advance_when_not_posted(self) -> None:
        """Cleared state is NOT advanced when the SimpleFIN transaction is still pending (not posted)."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id=None, cleared="uncleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        # Not posted — pending transaction
        raw_txns = [
            {
                "id": "txn-match",
                "account_id": account.simplefin_account_id,
                "posted": 0,
                "transacted_at": int(datetime.now(UTC).timestamp()),
                "amount": "-50.00",
                "description": "GROCERY",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        # Only import_id update, no cleared update
        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert "cleared" not in call_kwargs
        assert result["cleared"] == 0

    @pytest.mark.asyncio
    async def test_find_existing_match_no_clear_advance_when_already_cleared(self) -> None:
        """A fuzzy-matched cleared transaction is not modified beyond stamping import_id."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id=None, cleared="cleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert "cleared" not in call_kwargs
        assert result["cleared"] == 0

    @pytest.mark.asyncio
    async def test_exact_sync_id_match_skips_entirely(self) -> None:
        """A row already carrying this sync_id is skipped: provenance may refresh, nothing else moves."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        # Transaction already has this sync_id from a previous sync
        existing = make_transaction(sync_id="txn-match", sync_source="simplefin", cleared="cleared")
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=existing)

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        # Should skip entirely (not call update or create)
        # The identity path refreshes bank provenance on a hit (bank_amount, the
        # posted date) but never the row's money or state.
        for call in svc.txn_repo.update.call_args_list:
            assert not ({"cleared", "amount", "date"} & call.kwargs.keys()), call.kwargs
        svc.txn_service.create.assert_not_called()
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_find_existing_match_deduplicates_expense_transactions(self) -> None:
        """Expense transactions (negative amounts) should be deduplicated on exact match."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(import_id=None, cleared="uncleared", amount="-100.00")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "GROCERY")]
        )

        raw_txns = [
            {
                "id": "txn-match",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-100.00",
                "description": "GROCERY",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["imported"] == 0
        assert result["matched"] == 1
        svc.txn_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_renamed_payee_auto_match_preserves_reconciled_row(self) -> None:
        """The Bread Financial scenario end-to-end at the loop level: a
        reconciled YNAB row with a renamed payee absorbs the bank row —
        sync identity and bank_posted_date only, no date/cleared changes."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(cleared="reconciled")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "Bread Financial")]
        )

        raw_txns = [
            {
                "id": "txn-comenity",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-320.35",
                "description": "COMENITY PAY VI WEB PYMT",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["matched"] == 1
        assert result["imported"] == 0
        svc.txn_service.create.assert_not_called()
        call_kwargs = svc.txn_repo.update.call_args.kwargs
        assert call_kwargs.get("sync_id") == "txn-comenity"
        assert call_kwargs.get("bank_posted_date") == today_utc()
        assert "date" not in call_kwargs
        assert "entered_date" not in call_kwargs
        assert "cleared" not in call_kwargs

    @pytest.mark.asyncio
    async def test_auto_match_on_split_parent_clears_children_too(self) -> None:
        """A YNAB split parent absorbing a posted bank row is upgraded to
        cleared — its children must mirror that, or the children-mirror-
        cleared invariant breaks and reconcile strands them."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(cleared="uncleared", is_split=True, amount="-50.00")
        children = [
            make_transaction(cleared="uncleared", parent_transaction_id=existing.id),
            make_transaction(cleared="uncleared", parent_transaction_id=existing.id),
        ]
        svc.txn_repo.get_splits = AsyncMock(return_value=children)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[(existing, "Costco")])

        raw_txns = [
            {
                "id": "txn-split",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-50.00",
                "description": "COSTCO WHSE",
            }
        ]
        decrypt_target = "igab.services.simplefin_service.decrypt"
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(decrypt_target, return_value="https://user:pass@example.com"),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["matched"] == 1
        parent_call, *child_calls = svc.txn_repo.update.call_args_list
        assert parent_call.args[0] == existing.id
        assert parent_call.kwargs.get("cleared") == "cleared"
        assert [c.args[0] for c in child_calls] == [child.id for child in children]
        assert all(c.kwargs == {"cleared": "cleared"} for c in child_calls)

    @pytest.mark.asyncio
    async def test_auto_match_on_already_cleared_split_parent_skips_children(self) -> None:
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(cleared="cleared", is_split=True, amount="-50.00")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[(existing, "Costco")])

        raw_txns = [
            {
                "id": "txn-split2",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-50.00",
                "description": "COSTCO WHSE",
            }
        ]
        decrypt_target = "igab.services.simplefin_service.decrypt"
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(decrypt_target, return_value="https://user:pass@example.com"),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["matched"] == 1
        svc.txn_repo.get_splits.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ambiguous_candidates_create_review_match(self) -> None:
        """Two same-day lookalike candidates: the bank row is created
        (approved=False) with a pending review match — never silently."""
        svc = self._make_svc()
        matching_svc = AsyncMock()
        svc.matching_service = matching_svc
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        cand_a = make_transaction(amount="-12.50", cleared="cleared")
        cand_b = make_transaction(amount="-12.50", cleared="cleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(cand_a, "Lunch"), (cand_b, "Lunch")]
        )
        new_txn = make_transaction(amount="-12.50")
        svc.txn_service.create = AsyncMock(return_value=new_txn)

        raw_txns = [
            {
                "id": "txn-food",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-12.50",
                "description": "SQ *FOOD TRUCK",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["imported"] == 1
        assert result["review_queued"] == 1
        create_data = svc.txn_service.create.call_args[0][1]
        assert create_data.approved is False
        match_kwargs = matching_svc.match_repo.create.call_args.kwargs
        assert match_kwargs["synced_transaction_id"] == new_txn.id
        assert match_kwargs["manual_transaction_id"] in (cand_a.id, cand_b.id)
        assert match_kwargs["confidence_score"] > 0.0
        matching_svc.try_match.assert_not_called()

    @pytest.mark.asyncio
    async def test_created_posted_row_carries_bank_posted_date(self) -> None:
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=make_transaction())

        with (
            patch.object(
                svc.client,
                "get_feed",
                AsyncMock(return_value=SimpleFINFeed([self._posted_raw_txn(account)])),
            ),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        create_data = svc.txn_service.create.call_args[0][1]
        assert create_data.bank_posted_date == today_utc()
        assert create_data.date == today_utc()

    @pytest.mark.asyncio
    async def test_created_pending_row_has_no_bank_posted_date(self) -> None:
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=make_transaction(cleared="pending"))

        raw_txns = [
            {
                "id": "txn-hold",
                "account_id": account.simplefin_account_id,
                "posted": 0,
                "transacted_at": int(datetime.now(UTC).timestamp()),
                "amount": "-40.00",
                "description": "GAS HOLD",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        create_data = svc.txn_service.create.call_args[0][1]
        assert create_data.bank_posted_date is None
        assert create_data.cleared == "pending"

    @pytest.mark.asyncio
    async def test_matched_candidate_excluded_for_subsequent_feed_rows(self) -> None:
        """Two identical feed rows, one existing candidate: the first row
        consumes it; the second row's candidate query must exclude it so the
        pair can't collapse onto the same existing transaction."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)

        existing = make_transaction(amount="-10.00", cleared="cleared")
        calls: list[set[uuid.UUID]] = []

        async def fake_candidates(*args, **kwargs):
            calls.append(set(kwargs.get("exclude_ids") or ()))
            if existing.id in (kwargs.get("exclude_ids") or ()):
                return []
            return [(existing, "GROCERY")]

        svc.txn_repo.find_existing_match_candidates = AsyncMock(side_effect=fake_candidates)
        created = make_transaction(amount="-10.00")
        svc.txn_service.create = AsyncMock(return_value=created)

        posted = int(datetime.now(UTC).timestamp())
        raw_txns = [
            {
                "id": "txn-a",
                "account_id": account.simplefin_account_id,
                "posted": posted,
                "amount": "-10.00",
                "description": "GROCERY",
            },
            {
                "id": "txn-b",
                "account_id": account.simplefin_account_id,
                "posted": posted,
                "amount": "-10.00",
                "description": "GROCERY",
            },
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await svc.sync(conn.id, uuid.uuid4())

        assert result["matched"] == 1
        assert result["imported"] == 1
        assert calls[0] == set()
        assert calls[1] == {existing.id}


class TestBankRecordCapture:
    """The bank's own amount and payee are provenance: they are captured on
    every path a bank row can reach a transaction, and never overwritten by
    the user's ledger edits. Without them a synced row keeps no trace of
    what the bank actually reported."""

    _make_svc = TestSyncFlow._make_svc
    _base_sync_mocks = TestSyncFlow._base_sync_mocks

    @pytest.mark.asyncio
    async def test_new_import_records_bank_amount_and_payee(self) -> None:
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=make_transaction())

        raw_txns = [
            {
                "id": "txn-new",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-50.00",
                "description": "SQ *FOOD TRUCK",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        create_data = svc.txn_service.create.call_args[0][1]
        assert create_data.bank_amount == D("-50.00")
        assert create_data.bank_payee == "SQ *FOOD TRUCK"

    @pytest.mark.asyncio
    async def test_pending_to_posted_records_the_posted_bank_amount(self) -> None:
        """The bank's figure changes at posting (tips, gas holds). The ledger
        amount follows it, and bank_amount records what the bank said."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)
        pending_txn = make_transaction(sync_id="txn-hold", cleared="pending", amount="-40.00")
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=pending_txn)

        raw_txns = [
            {
                "id": "txn-hold",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-52.75",
                "description": "SHELL OIL",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        kwargs = svc.txn_repo.update.call_args.kwargs
        assert kwargs["amount"] == D("-52.75")
        assert kwargs["bank_amount"] == D("-52.75")
        assert kwargs["bank_payee"] == "SHELL OIL"

    @pytest.mark.asyncio
    async def test_auto_match_stamps_bank_values_onto_the_existing_row(self) -> None:
        """The user's manual row keeps its own amount and payee — the bank's
        are recorded alongside so the pair stays reviewable."""
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)
        existing = make_transaction(amount="-50.00", cleared="cleared")
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing, "Groceries")]
        )

        raw_txns = [
            {
                "id": "txn-match",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-50.00",
                "description": "KROGER #412",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        kwargs = svc.txn_repo.update.call_args.kwargs
        assert kwargs["bank_amount"] == D("-50.00")
        assert kwargs["bank_payee"] == "KROGER #412"
        # The user's ledger values are never rewritten by a match
        assert "amount" not in kwargs
        assert "payee_id" not in kwargs

    @pytest.mark.asyncio
    async def test_payee_falls_back_to_description_then_to_none(self) -> None:
        svc = self._make_svc()
        conn = make_connection()
        account = make_account(first_sync_complete=True)
        self._base_sync_mocks(svc, account, conn)
        svc.txn_repo.find_existing_match_candidates = AsyncMock(return_value=[])
        svc.txn_service.create = AsyncMock(return_value=make_transaction())

        raw_txns = [
            {
                "id": "txn-bare",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-9.99",
            }
        ]
        with (
            patch.object(svc.client, "get_feed", AsyncMock(return_value=SimpleFINFeed(raw_txns))),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await svc.sync(conn.id, uuid.uuid4())

        create_data = svc.txn_service.create.call_args[0][1]
        assert create_data.bank_payee is None
        assert create_data.bank_amount == D("-9.99")


# ─── Match decision ladder ────────────────────────────────────────────────────


def _candidate(
    *,
    amount: str = "-320.35",
    days_ago: int = 0,
    payee: str | None = None,
    cleared: str = "reconciled",
) -> tuple[MagicMock, str | None]:
    txn = make_transaction(
        amount=amount,
        date_=today_utc() - timedelta(days=days_ago),
        cleared=cleared,
    )
    return (txn, payee)


class TestMatchDecision:
    """Pure decision-ladder tests. Candidates already share the exact amount
    within the ±10 day search window (SQL guarantees that); the ladder only
    chooses between auto / review / create. Auto-matching is confined to
    ±5 days — candidates beyond that only ever reach review."""

    def test_no_candidates_creates(self) -> None:
        d = _decide_match("STARBUCKS", today_utc(), True, [])
        assert d.action == "create"
        assert d.candidate is None

    def test_renamed_payee_same_day_auto_matches(self) -> None:
        """Bread Financial regression: the user renamed the payee in YNAB, the
        bank descriptor shares no words with it — exact amount + same day must
        still auto-match instead of silently duplicating."""
        cand = _candidate(days_ago=0, payee="Bread Financial")
        d = _decide_match("COMENITY PAY VI WEB PYMT", today_utc(), True, [cand])
        assert d.action == "auto"
        assert d.candidate is cand[0]

    def test_check_descriptor_one_day_off_auto_matches(self) -> None:
        cand = _candidate(days_ago=1, payee="Lawn Service")
        d = _decide_match("CHECK # 1234", today_utc(), True, [cand])
        assert d.action == "auto"
        assert d.candidate is cand[0]

    def test_dissimilar_payee_two_days_off_goes_to_review(self) -> None:
        """Outside the tight window, payee dissimilarity means real doubt —
        create the row but queue it for human review, never silently."""
        cand = _candidate(days_ago=2, payee="Bread Financial")
        d = _decide_match("COMENITY PAY VI WEB PYMT", today_utc(), True, [cand])
        assert d.action == "review"
        assert d.candidate is cand[0]
        assert d.score > 0.0

    def test_similar_payee_two_days_off_still_auto_matches(self) -> None:
        """Rule 1 preserved: strong payee similarity auto-matches at any
        distance inside the window, as before this fix."""
        cand = _candidate(days_ago=2, payee="Whole Foods Market")
        d = _decide_match("WHOLE FOODS MARKET #123", today_utc(), True, [cand])
        assert d.action == "auto"
        assert d.candidate is cand[0]
        assert d.score >= DEDUP_AUTO_MATCH_THRESHOLD

    def test_two_same_day_lookalikes_go_to_review(self) -> None:
        """Two identical-amount same-day candidates with equally weak payee
        similarity: guessing would corrupt one of them — review instead."""
        a = _candidate(days_ago=0, payee="Lunch")
        b = _candidate(days_ago=0, payee="Lunch")
        d = _decide_match("SQ *FOOD TRUCK", today_utc(), True, [a, b])
        assert d.action == "review"

    def test_same_day_pair_with_clear_payee_winner_auto_matches(self) -> None:
        with patch(
            "igab.services.simplefin_service.best_payee_similarity",
            side_effect=lambda names, other, **_: {"close": 0.62, "far": 0.30}[names[0]],
        ):
            close = _candidate(days_ago=0, payee="close")
            far = _candidate(days_ago=0, payee="far")
            d = _decide_match("BANK DESCRIPTOR", today_utc(), True, [close, far])
        assert d.action == "auto"
        assert d.candidate is close[0]

    def test_same_day_pair_below_margin_goes_to_review(self) -> None:
        with patch(
            "igab.services.simplefin_service.best_payee_similarity",
            side_effect=lambda names, other, **_: {"close": 0.45, "far": 0.40}[names[0]],
        ):
            close = _candidate(days_ago=0, payee="close")
            far = _candidate(days_ago=0, payee="far")
            d = _decide_match("BANK DESCRIPTOR", today_utc(), True, [close, far])
        assert d.action == "review"

    def test_far_candidates_do_not_block_structural_match(self) -> None:
        """A second candidate 3 days out does not make the same-day one
        ambiguous — date proximity disambiguates recurring amounts."""
        near = _candidate(days_ago=0, payee="Bread Financial")
        far = _candidate(days_ago=3, payee="Card Payment")
        d = _decide_match("COMENITY PAY VI WEB PYMT", today_utc(), True, [near, far])
        assert d.action == "auto"
        assert d.candidate is near[0]

    def test_missing_payees_tight_window_auto_matches(self) -> None:
        """Neutral 0.5 similarity on both sides: structure still decides."""
        cand = _candidate(days_ago=1, payee=None)
        d = _decide_match("", today_utc(), True, [cand])
        assert d.action == "auto"

    def test_pending_feed_row_never_structurally_matches(self) -> None:
        """Pending amounts are provisional (tips, gas holds) — a same-day
        dissimilar candidate goes to review, not auto."""
        cand = _candidate(days_ago=0, payee="Bread Financial")
        d = _decide_match("COMENITY PAY VI WEB PYMT", today_utc(), False, [cand])
        assert d.action == "review"

    def test_pending_feed_row_still_payee_matches(self) -> None:
        cand = _candidate(days_ago=0, payee="Whole Foods Market")
        d = _decide_match("WHOLE FOODS MARKET #123", today_utc(), False, [cand])
        assert d.action == "auto"

    def test_window_edge_dissimilar_goes_to_review(self) -> None:
        cand = _candidate(days_ago=5, payee="Bread Financial")
        d = _decide_match("COMENITY PAY VI WEB PYMT", today_utc(), True, [cand])
        assert d.action == "review"
        assert d.candidate is cand[0]

    def test_settlement_lag_candidate_reviews_instead_of_silent_create(self) -> None:
        """Sapphire regression: a card payment the user dated 6/15 posted 6/22 —
        7 days out, beyond the old ±5 search window, so it silently
        duplicated. The widened window must surface it for review."""
        cand = _candidate(days_ago=7, payee="Sapphire")
        d = _decide_match("SAPPHIRE CARD ONLINE PAYMENT", today_utc(), True, [cand])
        assert d.action == "review"
        assert d.candidate is cand[0]

    def test_identical_payee_beyond_auto_radius_never_auto_matches(self) -> None:
        """An identical payee a week out is as likely a weekly recurring
        charge as a settlement-lagged duplicate — review, never auto."""
        cand = _candidate(days_ago=7, payee="Spotify")
        d = _decide_match("SPOTIFY", today_utc(), True, [cand])
        assert d.action == "review"
        assert d.candidate is cand[0]

    def test_strong_far_candidate_blocks_structural_shortcut(self) -> None:
        """A perfect-payee candidate 7 days out plus a weak same-day one is
        genuinely ambiguous — review, not a silent structural pick."""
        far_strong = _candidate(days_ago=7, payee="Spotify")
        near_weak = _candidate(days_ago=0, payee="Lunch Money")
        d = _decide_match("SPOTIFY", today_utc(), True, [far_strong, near_weak])
        assert d.action == "review"

    def test_weak_far_candidates_do_not_block_structural_match(self) -> None:
        """Weak candidates in the widened 6–10 day band leave the same-day
        singleton auto-match intact."""
        near = _candidate(days_ago=0, payee="Bread Financial")
        far = _candidate(days_ago=8, payee="Card Payment")
        d = _decide_match("COMENITY PAY VI WEB PYMT", today_utc(), True, [near, far])
        assert d.action == "auto"
        assert d.candidate is near[0]


# ─── Confidence Scoring ───────────────────────────────────────────────────────


class TestConfidenceScoring:
    def test_perfect_match_returns_1(self) -> None:
        score = calculate_confidence(
            D("-50.00"),
            today_utc(),
            "STARBUCKS",
            D("-50.00"),
            today_utc(),
            "STARBUCKS",
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_exact_amount_contributes_40pct(self) -> None:
        score = _amount_score(D("-50.00"), D("-50.00"))
        assert score == pytest.approx(1.0)

    def test_zero_amount_score_on_mismatch(self) -> None:
        # 5% difference is beyond 1% tolerance → 0
        score = _amount_score(D("-50.00"), D("-47.00"))
        assert score == 0.0

    def test_same_day_date_score(self) -> None:
        today = today_utc()
        assert _date_score(today, today) == pytest.approx(1.0)

    def test_date_score_decays_with_distance(self) -> None:
        today = today_utc()
        yesterday = today - timedelta(days=1)
        score_1d = _date_score(today, yesterday)
        score_2d = _date_score(today, today - timedelta(days=2))
        assert 0 < score_2d < score_1d < 1.0

    def test_date_score_zero_beyond_window(self) -> None:
        today = today_utc()
        too_far = today - timedelta(days=10)
        assert _date_score(today, too_far) == 0.0

    def test_identical_payees_score_1(self) -> None:
        assert _payee_similarity("STARBUCKS", "STARBUCKS") == pytest.approx(1.0)

    def test_empty_payee_scores_0(self) -> None:
        assert _payee_similarity("", "STARBUCKS") == 0.0

    def test_partial_match_scores_well(self) -> None:
        score = _payee_similarity("STARBUCKS #1234", "STARBUCKS")
        assert score >= 0.8

    def test_unrelated_payees_score_low(self) -> None:
        score = _payee_similarity("WALMART SUPERCENTER", "NETFLIX.COM")
        assert score < 0.5

    def test_full_confidence_components(self) -> None:
        today = today_utc()
        score = calculate_confidence(
            D("-50.00"),
            today,
            "WHOLE FOODS",
            D("-50.00"),
            today,
            "WHOLE FOODS MARKET",
        )
        # Amount (0.4) + Date (0.3) + partial payee match (should be high)
        assert score > 0.85


# ─── Transaction Matching Service ─────────────────────────────────────────────


class TestTransactionMatchingService:
    def _make_svc(self) -> TransactionMatchingService:
        return TransactionMatchingService(
            session=AsyncMock(),
            txn_repo=AsyncMock(),
            match_repo=AsyncMock(),
            payee_repo=AsyncMock(),
            txn_service=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_no_match_when_no_candidates(self) -> None:
        svc = self._make_svc()
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[])
        synced = make_transaction()
        await svc.try_match(synced)
        svc.match_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_accepts_high_confidence_match(self) -> None:
        svc = self._make_svc()
        today = today_utc()
        payee_id = uuid.uuid4()

        synced = make_transaction(amount="-50.00", date_=today, payee_id=payee_id)
        candidate = make_transaction(amount="-50.00", date_=today, payee_id=payee_id)

        payee_mock = MagicMock()
        payee_mock.name = "STARBUCKS"
        svc.payee_repo.get = AsyncMock(return_value=payee_mock)
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[candidate])
        svc.match_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        await svc.try_match(synced)

        create_call = svc.match_repo.create.call_args
        assert create_call.kwargs["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_pending_match_created_for_medium_confidence(self) -> None:
        svc = self._make_svc()
        today = today_utc()
        two_days_ago = today - timedelta(days=2)

        synced = make_transaction(amount="-50.00", date_=today)
        candidate = make_transaction(amount="-50.00", date_=two_days_ago)

        payee_a = MagicMock()
        payee_a.name = "STARBUCKS PIKE"
        payee_b = MagicMock()
        payee_b.name = "NETFLIX.COM"
        svc.payee_repo.get = AsyncMock(side_effect=[payee_a, payee_b])
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[candidate])
        svc.match_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        await svc.try_match(synced)

        create_call = svc.match_repo.create.call_args
        confidence = create_call.kwargs["confidence_score"]
        # Score should be between 0.5 and AUTO_ACCEPT_THRESHOLD
        assert 0.5 <= confidence < AUTO_ACCEPT_THRESHOLD
        assert create_call.kwargs["status"] == "pending"

    @pytest.mark.asyncio
    async def test_no_match_when_best_score_below_threshold(self) -> None:
        svc = self._make_svc()
        # Very different date (beyond window) → low score → no match
        synced = make_transaction(amount="-50.00", date_=today_utc())
        # find_match_candidates returns empty (date/amount filter already screens them)
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[])
        await svc.try_match(synced)
        svc.match_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_match_links_transactions(self) -> None:
        svc = self._make_svc()
        match_id = uuid.uuid4()

        match = MagicMock()
        match.id = match_id
        match.status = "pending"
        match.synced_transaction_id = uuid.uuid4()
        match.manual_transaction_id = uuid.uuid4()
        match.confidence_score = Decimal("0.75")

        svc.match_repo.get = AsyncMock(return_value=match)
        svc.match_repo.update_status = AsyncMock()

        synced = make_transaction(amount="-50.00", sync_id="t-1", sync_source="simplefin")
        manual = make_transaction(amount="-50.00")

        select_results = iter([synced, manual])

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(side_effect=lambda: next(select_results))
            return result

        svc.session.execute = AsyncMock(side_effect=mock_execute)
        svc.session.flush = AsyncMock()

        await svc.accept_match(match_id)
        svc.match_repo.update_status.assert_called_once_with(match_id, "accepted")

    @pytest.mark.asyncio
    async def test_reject_match_updates_status(self) -> None:
        svc = self._make_svc()
        match_id = uuid.uuid4()
        svc.match_repo.update_status = AsyncMock()
        await svc.reject_match(match_id)
        svc.match_repo.update_status.assert_called_once_with(match_id, "rejected")

    @pytest.mark.asyncio
    async def test_accept_already_accepted_is_noop(self) -> None:
        svc = self._make_svc()
        match_id = uuid.uuid4()
        match = MagicMock()
        match.status = "accepted"
        svc.match_repo.get = AsyncMock(return_value=match)
        await svc.accept_match(match_id)
        svc.match_repo.update_status.assert_not_called()
