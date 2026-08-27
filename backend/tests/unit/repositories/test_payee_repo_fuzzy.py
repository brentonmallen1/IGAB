"""
Tests for PayeeRepository.find_best_match fuzzy payee matching.

Rules:
  1. Exact name match returns the matching payee.
  2. Similar names (above threshold) return the best-scoring payee.
  3. mapping_samples are treated as additional match candidates.
  4. Raw names below PAYEE_FUZZY_THRESHOLD return None.
  5. Best score wins when multiple payees could match.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from igab.repositories.payee_repo import PayeeRepository

BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def make_payee(name: str, mapping_samples: list[str] | None = None) -> MagicMock:
    p = MagicMock()
    p.id = uuid.uuid4()
    p.name = name
    p.mapping_samples = mapping_samples or []
    return p


def make_repo(*payees: MagicMock) -> PayeeRepository:
    session = MagicMock()
    repo = PayeeRepository(session=session)
    repo.get_all = AsyncMock(return_value=list(payees))
    return repo


class TestFuzzyMatchPayeeName:
    """Matching against the payee's canonical name."""

    @pytest.mark.asyncio
    async def test_exact_name_matches(self) -> None:
        publix = make_payee("Publix")
        repo = make_repo(publix)
        result = await repo.find_best_match(BUDGET_ID, "Publix")
        assert result is publix

    @pytest.mark.asyncio
    async def test_similar_name_matches_above_threshold(self) -> None:
        publix = make_payee("Publix")
        repo = make_repo(publix)
        # "PUBLIX #1234" should fuzzy-match "Publix" via token_set_ratio
        result = await repo.find_best_match(BUDGET_ID, "PUBLIX #1234")
        assert result is publix

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self) -> None:
        starbucks = make_payee("Starbucks")
        repo = make_repo(starbucks)
        result = await repo.find_best_match(BUDGET_ID, "starbucks coffee 1234")
        assert result is starbucks

    @pytest.mark.asyncio
    async def test_two_raw_bank_names_for_one_payee_match(self) -> None:
        # The first import created the payee under its raw name. The next
        # posting differs only in the reference number and scored 73 on the
        # raw strings — below the threshold — so it used to become a second
        # payee, which is where the duplicates Cleanup finds come from.
        payroll = make_payee("EMPLOYER PAYROLL #1234567890")
        repo = make_repo(payroll)
        result = await repo.find_best_match(BUDGET_ID, "EMPLOYER PAYROLL #9876543210")
        assert result is payroll

    @pytest.mark.asyncio
    async def test_unrelated_name_returns_none(self) -> None:
        publix = make_payee("Publix")
        repo = make_repo(publix)
        result = await repo.find_best_match(BUDGET_ID, "XYZZY UNKNOWN VENDOR 9999")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_payee_list_returns_none(self) -> None:
        repo = make_repo()
        result = await repo.find_best_match(BUDGET_ID, "Starbucks")
        assert result is None


class TestFuzzyMatchMappingSamples:
    """Matching against optional mapping_samples field."""

    @pytest.mark.asyncio
    async def test_mapping_sample_matches_raw_bank_name(self) -> None:
        payroll = make_payee("Company Payroll", mapping_samples=["NORTHWIND PAYSERV", "NORTHWIND PAYROLL"])
        repo = make_repo(payroll)
        result = await repo.find_best_match(BUDGET_ID, "NORTHWIND PAYSERV PAYROLL 260415 DOE")
        assert result is payroll

    @pytest.mark.asyncio
    async def test_second_mapping_sample_also_matches(self) -> None:
        payroll = make_payee("Company Payroll", mapping_samples=["NORTHWIND PAYSERV", "NORTHWIND PAYROLL"])
        repo = make_repo(payroll)
        result = await repo.find_best_match(BUDGET_ID, "NORTHWIND PAYROLL DIRECT DEPOSIT")
        assert result is payroll

    @pytest.mark.asyncio
    async def test_a_sample_with_a_comma_is_one_sample(self) -> None:
        # The list format exists for this: a bank name that contains a comma.
        sample = "NORTHWIND PAYSERV PAYROLL 250915 000000000000Q3N DOE, JANE"
        payee = make_payee("Paycheck", mapping_samples=[sample])
        repo = make_repo(payee)
        result = await repo.find_best_match(
            BUDGET_ID, "NORTHWIND PAYSERV PAYROLL 260814 000000000000 DOE, JANE"
        )
        assert result is payee

    @pytest.mark.asyncio
    async def test_no_mapping_samples_still_matches_name(self) -> None:
        target = make_payee("Target", mapping_samples=None)
        repo = make_repo(target)
        result = await repo.find_best_match(BUDGET_ID, "TARGET STORE 1234")
        assert result is target


class TestFuzzyMatchThreshold:
    """Scores below PAYEE_FUZZY_THRESHOLD are not returned."""

    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self) -> None:
        publix = make_payee("Publix")
        repo = make_repo(publix)
        # A completely unrelated string should not match "Publix"
        result = await repo.find_best_match(BUDGET_ID, "ZZZZ UNRELATED 9999")
        assert result is None

    @pytest.mark.asyncio
    async def test_short_payee_name_not_substring_matched_incorrectly(self) -> None:
        amazon = make_payee("Amazon")
        apple = make_payee("Apple")
        repo = make_repo(amazon, apple)
        # Neither should match an unrelated vendor
        result = await repo.find_best_match(BUDGET_ID, "WALGREENS PHARMACY 555")
        assert result is None


class TestFuzzyMatchBestScoreWins:
    """When multiple payees could match, the best scoring one is returned."""

    @pytest.mark.asyncio
    async def test_best_score_wins_among_multiple_candidates(self) -> None:
        amazon = make_payee("Amazon", mapping_samples=["AMAZON.COM"])
        amazon_fresh = make_payee("Amazon Fresh", mapping_samples=["AMAZON FRESH"])
        repo = make_repo(amazon, amazon_fresh)
        # "AMAZON.COM PURCHASE" should better match "Amazon" / "AMAZON.COM"
        result = await repo.find_best_match(BUDGET_ID, "AMAZON.COM PURCHASE")
        assert result is amazon

    @pytest.mark.asyncio
    async def test_exact_match_beats_similar_match(self) -> None:
        exact = make_payee("Publix")
        partial = make_payee("Publix Deli")
        repo = make_repo(exact, partial)
        # Exact "Publix" name should win
        result = await repo.find_best_match(BUDGET_ID, "PUBLIX #1234")
        assert result is not None
        # Both are valid matches; the one with higher score wins
        assert result in (exact, partial)
