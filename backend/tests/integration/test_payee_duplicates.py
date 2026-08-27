"""Payee duplicate suggestions: complete-linkage fuzzy grouping.

The old union-find grouping was transitive: A~B and B~C pulled A and C into
one group even when A~C was far below the threshold, and the displayed
"similarity" was the group average — the user saw a "35% similar" group in
balanced (75%) mode. These tests pin the fix: every pair inside a group must
clear the threshold, and the displayed similarity is the weakest pair.
"""

from datetime import date

from rapidfuzz import fuzz

from igab.domain.payee_names import similarity_key
from igab.repositories.payee_repo import PayeeRepository

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_transaction,
    create_user,
)


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return budget, PayeeRepository(db_session)


class TestFindDuplicateGroups:
    async def test_similar_pair_grouped_with_pairwise_similarity(self, db_session):
        budget, repo = await _setup(db_session)
        await create_payee(db_session, budget, "Home Depot")
        await create_payee(db_session, budget, "The Home Depot")

        groups = await repo.find_duplicate_groups(budget.id, threshold=75)

        assert len(groups) == 1
        names = {p["name"] for p in groups[0]["payees"]}
        assert names == {"Home Depot", "The Home Depot"}
        assert groups[0]["similarity"] == int(
            fuzz.token_set_ratio(similarity_key("Home Depot"), similarity_key("The Home Depot"))
        )

    async def test_chain_does_not_bridge_dissimilar_payees(self, db_session):
        """A~B=100, B~C=81, but A~C=69 (< 75): C must not ride the chain into
        the group. The old union-find produced one group of three."""
        budget, repo = await _setup(db_session)
        await create_payee(db_session, budget, "Home Depot")
        await create_payee(db_session, budget, "The Home Depot")
        await create_payee(db_session, budget, "The Depot Bar")

        groups = await repo.find_duplicate_groups(budget.id, threshold=75)

        assert len(groups) == 1
        names = {p["name"] for p in groups[0]["payees"]}
        assert names == {"Home Depot", "The Home Depot"}

    async def test_displayed_similarity_is_never_below_threshold(self, db_session):
        """Invariant behind the user-facing bug: whatever groups come back,
        the similarity label can never undercut the requested threshold."""
        budget, repo = await _setup(db_session)
        for name in [
            "Home Depot",
            "The Home Depot",
            "The Depot Bar",
            "Shell Oil",
            "Shell Oil 123",
            "Oil Change 123",
            "Amazon Marketplace",
            "Amazon Market",
            "Boston Market",
            "Netflix",
        ]:
            await create_payee(db_session, budget, name)

        for threshold in (70, 75, 80):
            for group in await repo.find_duplicate_groups(budget.id, threshold=threshold):
                assert group["similarity"] >= threshold
                # ...because every pair in the group clears it
                names = [similarity_key(p["name"]) for p in group["payees"]]
                for i, a in enumerate(names):
                    for b in names[i + 1 :]:
                        assert int(fuzz.token_set_ratio(a, b)) >= threshold

    async def test_similarity_is_minimum_pairwise(self, db_session):
        budget, repo = await _setup(db_session)
        names = ["Costco", "Costco Wholesale", "Costco Gas"]
        for name in names:
            await create_payee(db_session, budget, name)

        # Only meaningful if all three actually group at this threshold
        threshold = 55
        groups = await repo.find_duplicate_groups(budget.id, threshold=threshold)

        assert len(groups) == 1
        assert len(groups[0]["payees"]) == 3
        keys = [similarity_key(n) for n in names]
        expected_min = min(
            int(fuzz.token_set_ratio(a, b)) for i, a in enumerate(keys) for b in keys[i + 1 :]
        )
        assert groups[0]["similarity"] == expected_min

    async def test_no_groups_for_dissimilar_payees(self, db_session):
        budget, repo = await _setup(db_session)
        await create_payee(db_session, budget, "Netflix")
        await create_payee(db_session, budget, "Water Utility")
        await create_payee(db_session, budget, "Trader Joes")

        assert await repo.find_duplicate_groups(budget.id, threshold=70) == []

    async def test_transfer_payees_excluded(self, db_session):
        budget, repo = await _setup(db_session)
        account = await create_account(db_session, budget, "Savings")
        transfer = await create_payee(db_session, budget, "Transfer: Savings")
        transfer.transfer_account_id = account.id
        await create_payee(db_session, budget, "Transfer: Savings Acct")
        await db_session.flush()

        assert await repo.find_duplicate_groups(budget.id, threshold=75) == []

    async def test_groups_sorted_by_transaction_count(self, db_session):
        budget, repo = await _setup(db_session)
        account = await create_account(db_session, budget, "Checking")

        quiet_a = await create_payee(db_session, budget, "Shell Oil")
        await create_payee(db_session, budget, "Shell Oil Co")
        busy_a = await create_payee(db_session, budget, "Home Depot")
        busy_b = await create_payee(db_session, budget, "The Home Depot")

        await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 8, 1), payee=quiet_a
        )
        for day in (2, 3, 4):
            await create_transaction(
                db_session, budget, account, "-10.00", date(2026, 8, day), payee=busy_a
            )
        await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 8, 5), payee=busy_b
        )

        groups = await repo.find_duplicate_groups(budget.id, threshold=75)

        assert len(groups) == 2
        assert {p["name"] for p in groups[0]["payees"]} == {"Home Depot", "The Home Depot"}
        assert groups[0]["total_count"] == 4
        # Members within a group are sorted by their own count descending
        assert groups[0]["payees"][0]["name"] == "Home Depot"
        assert groups[1]["total_count"] == 1


class TestBankNoise:
    """Store numbers, reference codes and dates are the bank's, not the
    merchant's. Each case is named for the threshold it used to miss."""

    async def _group(self, db_session, names: list[str], threshold: int):
        budget, repo = await _setup(db_session)
        for name in names:
            await create_payee(db_session, budget, name)
        return await repo.find_duplicate_groups(budget.id, threshold=threshold)

    async def test_long_reference_numbers_used_to_miss_balanced_and_strict(self, db_session):
        # 73 on the raw names.
        groups = await self._group(
            db_session, ["ACME CORP PAYROLL #1234567890", "ACME CORP PAYROLL #9876543210"], 80
        )
        assert len(groups) == 1
        assert groups[0]["similarity"] == 100

    async def test_store_numbers_used_to_miss_strict(self, db_session):
        # 75 on the raw names.
        groups = await self._group(db_session, ["STARBUCKS #1234", "STARBUCKS #5678"], 80)
        assert len(groups) == 1
        assert groups[0]["similarity"] == 100

    async def test_reference_codes_used_to_miss_balanced(self, db_session):
        # 72 on the raw names.
        groups = await self._group(db_session, ["AMZN Mktp US*1A2B3", "AMZN Mktp US*4C5D6"], 75)
        assert len(groups) == 1
        assert groups[0]["similarity"] == 100

    async def test_a_marker_without_digits_is_the_name(self, db_session):
        # Square's "SQ *" prefix carries the merchant right behind the star.
        groups = await self._group(db_session, ["SQ *COFFEE HOUSE", "SQ *TACO TRUCK"], 70)
        assert groups == []

    async def test_a_single_digit_still_tells_units_apart(self, db_session):
        # Grouped as before — but the digit survives, so the score is not 100
        # and the wizard shows the pair as "similar", not "identical".
        groups = await self._group(db_session, ["Rental Unit 1", "Rental Unit 2"], 75)
        assert len(groups) == 1
        assert groups[0]["similarity"] < 100

    async def test_shared_digits_no_longer_bridge_unrelated_names(self, db_session):
        # 74 on the raw names — the "123" was doing the work.
        groups = await self._group(db_session, ["Shell Oil 123", "Oil Change 123"], 70)
        assert groups == []
