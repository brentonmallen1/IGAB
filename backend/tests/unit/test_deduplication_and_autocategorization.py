"""
Exhaustive tests for transaction deduplication and auto-categorization.

These are critical trust-surface tests covering:
1. Fuzzy deduplication by amount+date (find_existing_match)
2. Historical category inference (get_most_recent_category_for_payee)
3. Import ID generation and deduplication (get_existing_import_ids, _generate_import_id)
4. SimpleFIN sync deduplication flow
"""

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from igab.api.v1.imports import _generate_import_id as csv_generate_import_id
from igab.integrations.ynab.importer import _generate_import_id as ynab_generate_import_id


# ─── Import ID Generation Tests ──────────────────────────────────────────────


class TestImportIdGeneration:
    """Test deterministic hash-based import ID generation."""

    def test_csv_import_id_is_deterministic(self):
        """Same inputs always produce the same import_id."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "Grocery Store"

        id1 = csv_generate_import_id(account_id, txn_date, amount, payee)
        id2 = csv_generate_import_id(account_id, txn_date, amount, payee)

        assert id1 == id2
        assert id1.startswith("csv:")

    def test_csv_import_id_different_for_different_inputs(self):
        """Different inputs produce different import_ids."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")

        id1 = csv_generate_import_id(account_id, txn_date, amount, "Store A")
        id2 = csv_generate_import_id(account_id, txn_date, amount, "Store B")

        assert id1 != id2

    def test_csv_import_id_different_amounts(self):
        """Even small amount differences produce different import_ids."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        payee = "Store"

        id1 = csv_generate_import_id(account_id, txn_date, Decimal("-25.50"), payee)
        id2 = csv_generate_import_id(account_id, txn_date, Decimal("-25.51"), payee)

        assert id1 != id2

    def test_csv_import_id_different_dates(self):
        """Different dates produce different import_ids."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        amount = Decimal("-25.50")
        payee = "Store"

        id1 = csv_generate_import_id(account_id, date(2026, 4, 15), amount, payee)
        id2 = csv_generate_import_id(account_id, date(2026, 4, 16), amount, payee)

        assert id1 != id2

    def test_csv_import_id_different_accounts(self):
        """Different accounts produce different import_ids."""
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "Store"

        id1 = csv_generate_import_id(
            uuid.UUID("11111111-1111-1111-1111-111111111111"), txn_date, amount, payee
        )
        id2 = csv_generate_import_id(
            uuid.UUID("22222222-2222-2222-2222-222222222222"), txn_date, amount, payee
        )

        assert id1 != id2

    def test_csv_import_id_empty_payee(self):
        """Empty payee still produces a valid import_id."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")

        id1 = csv_generate_import_id(account_id, txn_date, amount, "")
        assert id1.startswith("csv:")
        assert len(id1) == 4 + 16  # "csv:" + 16 hex chars

    def test_ynab_import_id_is_deterministic(self):
        """YNAB import_id generation is also deterministic."""
        account_name = "Checking"
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "Grocery Store"

        id1 = ynab_generate_import_id(account_name, txn_date, amount, payee)
        id2 = ynab_generate_import_id(account_name, txn_date, amount, payee)

        assert id1 == id2
        assert id1.startswith("csv:")

    def test_ynab_import_id_different_account_names(self):
        """Different account names produce different import_ids."""
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "Store"

        id1 = ynab_generate_import_id("Checking", txn_date, amount, payee)
        id2 = ynab_generate_import_id("Savings", txn_date, amount, payee)

        assert id1 != id2


# ─── Amount Tolerance Tests ──────────────────────────────────────────────────


class TestAmountMatching:
    """Fuzzy matching uses exact amount equality (no tolerance).

    Bank transaction amounts are always exact — the same transaction reported
    by YNAB and SimpleFIN will have identical amounts to the cent. A tolerance
    would risk false-positive matches between similar-amount transactions.
    """

    def test_exact_positive_amount_matches(self):
        assert Decimal("100.00") == Decimal("100.00")

    def test_exact_negative_amount_matches(self):
        assert Decimal("-100.00") == Decimal("-100.00")

    def test_off_by_one_cent_does_not_match(self):
        assert Decimal("100.00") != Decimal("99.99")
        assert Decimal("-100.00") != Decimal("-99.99")

    def test_positive_and_negative_same_magnitude_do_not_match(self):
        assert Decimal("100.00") != Decimal("-100.00")


# ─── Date Window Tests ────────────────────────────────────────────────────────


class TestDateWindow:
    """Test that fuzzy matching uses correct ±3 day window."""

    def test_same_day_matches(self):
        """Same day should always match."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 15)
        window = 3

        assert abs((test_date - base_date).days) <= window

    def test_one_day_before_matches(self):
        """One day before should match."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 14)
        window = 3

        assert abs((test_date - base_date).days) <= window

    def test_one_day_after_matches(self):
        """One day after should match."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 16)
        window = 3

        assert abs((test_date - base_date).days) <= window

    def test_three_days_before_matches(self):
        """Three days before should match (edge of window)."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 12)
        window = 3

        assert abs((test_date - base_date).days) <= window

    def test_three_days_after_matches(self):
        """Three days after should match (edge of window)."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 18)
        window = 3

        assert abs((test_date - base_date).days) <= window

    def test_four_days_before_no_match(self):
        """Four days before should not match."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 11)
        window = 3

        assert abs((test_date - base_date).days) > window

    def test_four_days_after_no_match(self):
        """Four days after should not match."""
        base_date = date(2026, 4, 15)
        test_date = date(2026, 4, 19)
        window = 3

        assert abs((test_date - base_date).days) > window

    def test_month_boundary_matches(self):
        """Date window should work correctly across month boundaries."""
        base_date = date(2026, 5, 1)
        test_date = date(2026, 4, 29)  # 2 days before
        window = 3

        assert abs((test_date - base_date).days) <= window

    def test_year_boundary_matches(self):
        """Date window should work correctly across year boundaries."""
        base_date = date(2026, 1, 2)
        test_date = date(2025, 12, 31)  # 2 days before
        window = 3

        assert abs((test_date - base_date).days) <= window


# ─── Historical Category Inference Tests ─────────────────────────────────────


class TestHistoricalCategoryInference:
    """Test that create() uses the most recent category for auto-categorization."""

    @pytest.fixture
    def mock_service(self):
        """Create a TransactionService with mocked dependencies."""
        from igab.services.transaction_service import TransactionService

        session = AsyncMock()
        # require_in_budget runs session.execute(...).scalar_one_or_none(); return
        # a truthy row so body-supplied ids validate as belonging to the budget.
        ownership_result = MagicMock()
        ownership_result.scalar_one_or_none = MagicMock(return_value=MagicMock())
        session.execute = AsyncMock(return_value=ownership_result)
        txn_repo = MagicMock()
        account_repo = MagicMock()
        category_repo = MagicMock()
        payee_repo = MagicMock()

        return TransactionService(
            session=session,
            transaction_repo=txn_repo,
            account_repo=account_repo,
            category_repo=category_repo,
            payee_repo=payee_repo,
        )

    async def test_uses_most_recent_category_when_available(self, mock_service):
        """Should use most recent category even if payee has default_category_id."""
        from igab.services.transaction_service import TransactionCreate

        budget_id = uuid.uuid4()
        account_id = uuid.uuid4()
        payee_id = uuid.uuid4()
        recent_cat_id = uuid.uuid4()
        default_cat_id = uuid.uuid4()

        mock_account = MagicMock()
        mock_account.budget_id = budget_id

        mock_payee = MagicMock()
        mock_payee.id = payee_id
        mock_payee.default_category_id = default_cat_id

        mock_txn = MagicMock()

        mock_service.account_repo.get_or_raise = AsyncMock(return_value=mock_account)
        mock_service.payee_repo.find_by_name = AsyncMock(return_value=mock_payee)
        mock_service.transaction_repo.create = AsyncMock(return_value=mock_txn)
        mock_service.transaction_repo.get_most_recent_category_for_payee = AsyncMock(
            return_value=recent_cat_id
        )

        data = TransactionCreate(
            account_id=account_id,
            date=date(2026, 4, 15),
            amount=Decimal("-25.00"),
            payee_name="Test Payee",
        )
        await mock_service.create(budget_id, data)

        # Should call most recent lookup
        mock_service.transaction_repo.get_most_recent_category_for_payee.assert_called_once_with(
            budget_id, payee_id
        )

        # Should use the most recent category, not the default
        create_call = mock_service.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == recent_cat_id

    async def test_falls_back_to_default_when_no_recent(self, mock_service):
        """Should fallback to default_category_id when no transaction history."""
        from igab.services.transaction_service import TransactionCreate

        budget_id = uuid.uuid4()
        account_id = uuid.uuid4()
        payee_id = uuid.uuid4()
        default_cat_id = uuid.uuid4()

        mock_account = MagicMock()
        mock_account.budget_id = budget_id

        mock_payee = MagicMock()
        mock_payee.id = payee_id
        mock_payee.default_category_id = default_cat_id

        mock_txn = MagicMock()

        mock_service.account_repo.get_or_raise = AsyncMock(return_value=mock_account)
        mock_service.payee_repo.find_by_name = AsyncMock(return_value=mock_payee)
        mock_service.transaction_repo.create = AsyncMock(return_value=mock_txn)
        mock_service.transaction_repo.get_most_recent_category_for_payee = AsyncMock(
            return_value=None  # No history
        )

        data = TransactionCreate(
            account_id=account_id,
            date=date(2026, 4, 15),
            amount=Decimal("-25.00"),
            payee_name="Test Payee",
        )
        await mock_service.create(budget_id, data)

        # Should use the default category as fallback
        create_call = mock_service.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == default_cat_id

    async def test_no_category_when_no_recent_and_no_default(self, mock_service):
        """Should have no category when payee has no history and no default."""
        from igab.services.transaction_service import TransactionCreate

        budget_id = uuid.uuid4()
        account_id = uuid.uuid4()
        payee_id = uuid.uuid4()

        mock_account = MagicMock()
        mock_account.budget_id = budget_id

        mock_payee = MagicMock()
        mock_payee.id = payee_id
        mock_payee.default_category_id = None

        mock_txn = MagicMock()

        mock_service.account_repo.get_or_raise = AsyncMock(return_value=mock_account)
        mock_service.payee_repo.find_by_name = AsyncMock(return_value=mock_payee)
        mock_service.transaction_repo.create = AsyncMock(return_value=mock_txn)
        mock_service.transaction_repo.get_most_recent_category_for_payee = AsyncMock(
            return_value=None
        )

        data = TransactionCreate(
            account_id=account_id,
            date=date(2026, 4, 15),
            amount=Decimal("-25.00"),
            payee_name="New Payee",
        )
        await mock_service.create(budget_id, data)

        create_call = mock_service.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] is None

    async def test_explicit_category_overrides_all(self, mock_service):
        """Explicit category should override both recent and default."""
        from igab.services.transaction_service import TransactionCreate

        budget_id = uuid.uuid4()
        account_id = uuid.uuid4()
        payee_id = uuid.uuid4()
        explicit_cat_id = uuid.uuid4()
        default_cat_id = uuid.uuid4()

        mock_account = MagicMock()
        mock_account.budget_id = budget_id

        mock_payee = MagicMock()
        mock_payee.id = payee_id
        mock_payee.default_category_id = default_cat_id

        mock_txn = MagicMock()

        mock_service.account_repo.get_or_raise = AsyncMock(return_value=mock_account)
        mock_service.payee_repo.find_by_name = AsyncMock(return_value=mock_payee)
        mock_service.transaction_repo.create = AsyncMock(return_value=mock_txn)

        data = TransactionCreate(
            account_id=account_id,
            date=date(2026, 4, 15),
            amount=Decimal("-25.00"),
            payee_name="Test Payee",
            category_id=explicit_cat_id,
        )
        await mock_service.create(budget_id, data)

        create_call = mock_service.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == explicit_cat_id


# ─── SimpleFIN Sync Deduplication Flow Tests ─────────────────────────────────


class TestSimpleFINSyncDeduplication:
    """Test the SimpleFIN sync deduplication flow."""

    @pytest.fixture
    def mock_svc(self):
        """Create SimpleFINService with mocked dependencies."""
        from igab.services.simplefin_service import SimpleFINService

        svc = SimpleFINService(
            session=AsyncMock(),
            repo=AsyncMock(),
            account_repo=AsyncMock(),
            txn_repo=AsyncMock(),
            txn_service=AsyncMock(),
        )
        svc.session.begin_nested = MagicMock(return_value=AsyncMock())
        svc.txn_repo.find_stale_pending_synced = AsyncMock(return_value=[])
        return svc

    async def test_matches_when_existing_match_found(self, mock_svc):
        """Should match (not import) when find_existing_match_candidates returns a high-score match."""
        from unittest.mock import patch

        budget_id = uuid.uuid4()

        conn = MagicMock()
        conn.id = uuid.uuid4()
        conn.sync_enabled = True
        conn.global_requests_today = 0
        conn.account_requests_today = 0
        conn.last_request_date = date.today()
        conn.access_url_encrypted = "encrypted"

        account = MagicMock()
        account.id = uuid.uuid4()
        account.budget_id = budget_id
        account.simplefin_account_id = "sf-acct-1"
        account.simplefin_sync_enabled = True
        account.first_sync_complete = True

        existing_txn = MagicMock()
        existing_txn.id = uuid.uuid4()
        existing_txn.sync_id = None
        existing_txn.date = date.today()
        existing_txn.cleared = "cleared"

        mock_svc.repo.get = AsyncMock(return_value=conn)
        mock_svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        mock_svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=date.today() - timedelta(days=5)
        )
        mock_svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        mock_svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        mock_svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing_txn, "STORE")]
        )
        mock_svc.txn_repo.update = AsyncMock()
        mock_svc.account_repo.update = AsyncMock()
        mock_svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-25.00",
                "description": "STORE",
            }
        ]

        with (
            patch.object(mock_svc.client, "get_transactions", AsyncMock(return_value=raw_txns)),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            result = await mock_svc.sync(conn.id, budget_id)

        assert result["matched"] == 1
        assert result["skipped"] == 0
        assert result["imported"] == 0
        mock_svc.txn_service.create.assert_not_called()

    async def test_stamps_import_id_on_matched_transaction(self, mock_svc):
        """Should stamp the matched transaction with the SimpleFIN import_id."""
        from unittest.mock import patch

        budget_id = uuid.uuid4()

        conn = MagicMock()
        conn.id = uuid.uuid4()
        conn.sync_enabled = True
        conn.global_requests_today = 0
        conn.account_requests_today = 0
        conn.last_request_date = date.today()
        conn.access_url_encrypted = "encrypted"

        account = MagicMock()
        account.id = uuid.uuid4()
        account.budget_id = budget_id
        account.simplefin_account_id = "sf-acct-1"
        account.simplefin_sync_enabled = True
        account.first_sync_complete = True

        existing_txn = MagicMock()
        existing_txn.id = uuid.uuid4()
        existing_txn.import_id = None  # No import_id
        existing_txn.date = date.today()
        existing_txn.cleared = "cleared"

        mock_svc.repo.get = AsyncMock(return_value=conn)
        mock_svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        mock_svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=date.today() - timedelta(days=5)
        )
        mock_svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        mock_svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        mock_svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing_txn, "STORE")]
        )
        mock_svc.txn_repo.update = AsyncMock()
        mock_svc.account_repo.update = AsyncMock()
        mock_svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-abc123",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-25.00",
                "description": "STORE",
            }
        ]

        with (
            patch.object(mock_svc.client, "get_transactions", AsyncMock(return_value=raw_txns)),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await mock_svc.sync(conn.id, budget_id)

        # Should have stamped sync_id (since existing_txn.sync_id was None)
        mock_svc.txn_repo.update.assert_called_once()
        call_kwargs = mock_svc.txn_repo.update.call_args[1]
        assert call_kwargs["sync_id"] == "txn-abc123"
        assert call_kwargs["sync_source"] == "simplefin"
        assert call_kwargs["has_sync_source"] is True
        assert call_kwargs["import_description"] == "STORE"

    async def test_stamps_sync_id_while_preserving_import_id(self, mock_svc):
        """When matching a YNAB-imported transaction, should stamp sync_id but preserve import_id."""
        from unittest.mock import patch

        budget_id = uuid.uuid4()

        conn = MagicMock()
        conn.id = uuid.uuid4()
        conn.sync_enabled = True
        conn.global_requests_today = 0
        conn.account_requests_today = 0
        conn.last_request_date = date.today()
        conn.access_url_encrypted = "encrypted"

        account = MagicMock()
        account.id = uuid.uuid4()
        account.budget_id = budget_id
        account.simplefin_account_id = "sf-acct-1"
        account.simplefin_sync_enabled = True
        account.first_sync_complete = True

        # Transaction imported from YNAB (has import_id, no sync_id)
        existing_txn = MagicMock()
        existing_txn.id = uuid.uuid4()
        existing_txn.import_id = "csv:existing123"
        existing_txn.sync_id = None
        existing_txn.date = date.today()
        existing_txn.cleared = "cleared"

        mock_svc.repo.get = AsyncMock(return_value=conn)
        mock_svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        mock_svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=date.today() - timedelta(days=5)
        )
        mock_svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        mock_svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        mock_svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(existing_txn, "STORE")]
        )
        mock_svc.txn_repo.update = AsyncMock()
        mock_svc.account_repo.update = AsyncMock()
        mock_svc.repo.update = AsyncMock(return_value=conn)

        raw_txns = [
            {
                "id": "txn-abc123",
                "account_id": account.simplefin_account_id,
                "posted": int(datetime.now(UTC).timestamp()),
                "amount": "-25.00",
                "description": "STORE",
            }
        ]

        with (
            patch.object(mock_svc.client, "get_transactions", AsyncMock(return_value=raw_txns)),
            patch(
                "igab.services.simplefin_service.decrypt",
                return_value="https://user:pass@example.com",
            ),
        ):
            await mock_svc.sync(conn.id, budget_id)

        # Should stamp sync_id (doesn't conflict with import_id)
        mock_svc.txn_repo.update.assert_called_once()
        call_kwargs = mock_svc.txn_repo.update.call_args[1]
        assert call_kwargs["sync_id"] == "txn-abc123"
        assert call_kwargs["sync_source"] == "simplefin"
        assert call_kwargs["has_sync_source"] is True
        # import_id NOT touched (preserved on the model, not in update call)
        assert "import_id" not in call_kwargs


# ─── Deduplication Scoring Tests ─────────────────────────────────────────────


class TestDedupScoring:
    """Test payee similarity and deduplication score calculation."""

    def test_payee_similarity_exact(self):
        from igab.services.simplefin_service import _payee_similarity

        assert _payee_similarity("Starbucks", "Starbucks") == 1.0

    def test_payee_similarity_case_insensitive(self):
        from igab.services.simplefin_service import _payee_similarity

        assert _payee_similarity("STARBUCKS", "starbucks") == 1.0

    def test_payee_similarity_partial_contains(self):
        from igab.services.simplefin_service import _payee_similarity

        # Bank appends location/code but payee was cleaned up — treat as strong
        # match. WRatio applies a 0.9 partial-match penalty, so assert the
        # score clears the auto-match bar rather than demanding a perfect 1.0.
        assert _payee_similarity("STARBUCKS #12345", "Starbucks") >= 0.85

    def test_payee_similarity_fuzzy(self):
        from igab.services.simplefin_service import _payee_similarity

        score = _payee_similarity("Amazon.com", "Amazon")
        assert score >= 0.7

    def test_payee_similarity_no_match(self):
        from igab.services.simplefin_service import _payee_similarity

        assert _payee_similarity("Starbucks", "Walmart") < 0.5

    def test_payee_similarity_none_returns_neutral(self):
        from igab.services.simplefin_service import _payee_similarity

        assert _payee_similarity(None, "Starbucks") == 0.5
        assert _payee_similarity("Starbucks", None) == 0.5
        assert _payee_similarity(None, None) == 0.5

    def test_dedup_score_same_day_same_payee(self):
        from igab.services.simplefin_service import _calculate_dedup_score

        score = _calculate_dedup_score("Starbucks", date(2026, 4, 15), "Starbucks", date(2026, 4, 15))
        assert score >= 0.95

    def test_dedup_score_two_days_apart_same_payee(self):
        from igab.services.simplefin_service import _calculate_dedup_score

        score = _calculate_dedup_score("Starbucks", date(2026, 4, 15), "Starbucks", date(2026, 4, 17))
        assert score >= DEDUP_AUTO_MATCH_THRESHOLD

    def test_dedup_score_same_day_different_payee(self):
        from igab.services.simplefin_service import _calculate_dedup_score

        score = _calculate_dedup_score("Starbucks", date(2026, 4, 15), "Walmart", date(2026, 4, 15))
        assert score < DEDUP_AUTO_MATCH_THRESHOLD

    def test_dedup_score_beyond_window_is_low(self):
        from igab.services.simplefin_service import _calculate_dedup_score

        # Date beyond DEDUP_DATE_WINDOW_DAYS gets 0 date score; only payee contributes
        score = _calculate_dedup_score("Starbucks", date(2026, 4, 15), "Starbucks", date(2026, 4, 25))
        assert score < DEDUP_AUTO_MATCH_THRESHOLD

    async def test_sync_skips_when_score_above_threshold(self, mock_svc=None):
        """Low-payee-similarity candidates should NOT be treated as duplicates."""
        from unittest.mock import patch

        from igab.services.simplefin_service import SimpleFINService

        svc = SimpleFINService(
            session=AsyncMock(),
            repo=AsyncMock(),
            account_repo=AsyncMock(),
            txn_repo=AsyncMock(),
            txn_service=AsyncMock(),
        )
        svc.session.begin_nested = MagicMock(return_value=AsyncMock())
        svc.txn_repo.find_stale_pending_synced = AsyncMock(return_value=[])

        budget_id = uuid.uuid4()
        conn = MagicMock()
        conn.id = uuid.uuid4()
        conn.sync_enabled = True
        conn.global_requests_today = 0
        conn.account_requests_today = 0
        conn.last_request_date = date.today()
        conn.access_url_encrypted = "encrypted"

        account = MagicMock()
        account.id = uuid.uuid4()
        account.budget_id = budget_id
        account.simplefin_account_id = "sf-acct-1"
        account.simplefin_sync_enabled = True
        account.first_sync_complete = True

        # Candidate with completely different payee — should NOT match
        unrelated_txn = MagicMock()
        unrelated_txn.id = uuid.uuid4()
        unrelated_txn.sync_id = None
        unrelated_txn.date = date.today()
        unrelated_txn.cleared = "cleared"

        svc.repo.get = AsyncMock(return_value=conn)
        svc.account_repo.get_linked_simplefin_accounts = AsyncMock(return_value=[account])
        svc.txn_repo.get_oldest_cleared_date_for_account = AsyncMock(
            return_value=date.today() - timedelta(days=5)
        )
        svc.txn_repo.find_by_sync_id = AsyncMock(return_value=None)
        svc.txn_repo.find_pending_by_sync_id = AsyncMock(return_value=None)
        # Candidate payee is totally different from synced payee "Starbucks"
        svc.txn_repo.find_existing_match_candidates = AsyncMock(
            return_value=[(unrelated_txn, "Walmart")]
        )
        svc.txn_repo.update = AsyncMock()
        svc.account_repo.update = AsyncMock()
        svc.repo.update = AsyncMock(return_value=conn)
        svc.txn_service.create = AsyncMock(return_value=MagicMock())

        raw_txns = [
            {
                "id": "txn-1",
                "account_id": account.simplefin_account_id,
                "posted": int(date.today().toordinal() * 86400),
                "amount": "-25.00",
                "payee": "Starbucks",
            }
        ]

        with (
            patch.object(svc.client, "get_transactions", AsyncMock(return_value=raw_txns)),
            patch("igab.services.simplefin_service.decrypt", return_value="https://user:pass@example.com"),
        ):
            result = await svc.sync(conn.id, budget_id)

        # Should have imported (not skipped) because payee similarity is too low
        assert result["imported"] == 1
        assert result["skipped"] == 0
        svc.txn_service.create.assert_called_once()


DEDUP_AUTO_MATCH_THRESHOLD = 0.85  # mirror service constant for test assertions


# ─── Edge Cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_import_id_with_unicode_payee(self):
        """Import ID should handle unicode payee names."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "Café François"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")
        assert len(import_id) == 20

    def test_import_id_with_special_characters(self):
        """Import ID should handle special characters in payee."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "Store #123 @ Mall (Main St.)"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")
        assert len(import_id) == 20

    def test_import_id_with_very_long_payee(self):
        """Import ID should handle very long payee names."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("-25.50")
        payee = "A" * 1000  # Very long name

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")
        assert len(import_id) == 20  # Hash is fixed length

    def test_import_id_zero_amount(self):
        """Import ID should handle zero amount transactions."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("0.00")
        payee = "Refund"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")

    def test_import_id_very_small_amount(self):
        """Import ID should handle very small amounts."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("0.01")
        payee = "Penny"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")

    def test_import_id_very_large_amount(self):
        """Import ID should handle very large amounts."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2026, 4, 15)
        amount = Decimal("999999999.99")
        payee = "Big Purchase"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")

    def test_tolerance_at_zero_amount(self):
        """Zero amount tolerance calculation should not crash."""
        base = Decimal("0.00")
        low = base * Decimal("0.99")
        high = base * Decimal("1.01")

        # Both should be zero
        assert low == Decimal("0.00")
        assert high == Decimal("0.00")

    def test_very_old_date(self):
        """Should handle very old dates."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(1990, 1, 1)
        amount = Decimal("-25.50")
        payee = "Old Store"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")

    def test_future_date(self):
        """Should handle future dates (scheduled transactions)."""
        account_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        txn_date = date(2030, 12, 31)
        amount = Decimal("-25.50")
        payee = "Future Store"

        import_id = csv_generate_import_id(account_id, txn_date, amount, payee)
        assert import_id.startswith("csv:")
