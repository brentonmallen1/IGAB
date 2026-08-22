"""Orphaned transfer legs must not read as income or expense.

A transfer leg normally carries `transfer_id` pointing at its partner. The
YNAB importer deliberately writes legs whose partner never turns up — the
partner account was skipped, or the leg's categorized counterpart never
entered the pairing pool — so that account balances stay right.

Those rows are still transfers. Recognizing one only by `transfer_id` meant an
orphan fell through `CASH_FLOW_ROW` and was counted as real money in or out.
`TRANSFER_LEG` therefore matches on the transfer *payee* as well, which is why
`Payee.transfer_account_id` has to actually be populated.

The categorized case must keep working unchanged: a YNAB "spending transfer"
to an off-budget account is real spending and stays in cash flow.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.payee_repo import PayeeRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)

TODAY = date.today()
START = TODAY - timedelta(days=20)


async def _budget_with_accounts(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    return budget, checking, brokerage


async def _income(db_session, budget) -> Decimal:
    """total_income as the sankey computes it — a direct CASH_FLOW_ROW read."""
    result = await ReportService(db_session).cash_flow_sankey(budget.id, START, TODAY)
    return result["total_income"]


class TestOrphanedLegsAreNotCashFlow:
    async def test_orphaned_inflow_is_not_income(self, db_session):
        budget, checking, brokerage = await _budget_with_accounts(db_session)
        payee = await PayeeRepository(db_session).find_or_create_transfer(
            budget.id, brokerage.id, brokerage.name
        )
        # No transfer_id: the partner leg never imported.
        await create_transaction(
            db_session, budget, checking, "500.00", TODAY, payee=payee, category=None
        )
        assert await _income(db_session, budget) == Decimal("0")

    async def test_a_real_inflow_is_still_income(self, db_session):
        """Guards the fix from over-reaching: an ordinary uncategorized inflow
        is exactly the shape of an orphan minus the transfer payee."""
        budget, checking, _ = await _budget_with_accounts(db_session)
        payee = await create_payee(db_session, budget, "Employer")
        await create_transaction(
            db_session, budget, checking, "500.00", TODAY, payee=payee, category=None
        )
        assert await _income(db_session, budget) == Decimal("500.00")

    async def test_linked_leg_is_still_excluded(self, db_session):
        budget, checking, brokerage = await _budget_with_accounts(db_session)
        payee = await PayeeRepository(db_session).find_or_create_transfer(
            budget.id, brokerage.id, brokerage.name
        )
        partner = await create_transaction(
            db_session, budget, brokerage, "-500.00", TODAY, payee=payee
        )
        await create_transaction(
            db_session,
            budget,
            checking,
            "500.00",
            TODAY,
            payee=payee,
            transfer_id=partner.id,
        )
        assert await _income(db_session, budget) == Decimal("0")

    async def test_payee_with_no_transfer_account_does_not_suppress(self, db_session):
        """A payee merely *named* "Transfer : X" is not enough — that is the
        state the backfill migration exists to repair, and until it is
        repaired the row must keep its old behaviour rather than silently
        vanish from income."""
        budget, checking, _ = await _budget_with_accounts(db_session)
        payee = await create_payee(db_session, budget, "Transfer : Brokerage")
        await create_transaction(
            db_session, budget, checking, "500.00", TODAY, payee=payee, category=None
        )
        assert await _income(db_session, budget) == Decimal("500.00")


class TestCategorizedTransfersStillCount:
    async def test_categorized_orphan_stays_in_cash_flow(self, db_session):
        """A categorized transfer leg keeps its category, so it passes
        CASH_FLOW_ROW even though it is a transfer — orphaned or not.

        This fixture is an INFLOW leg (+500 into checking from a brokerage),
        so what it must not do is read as income: nobody earned it, it was
        drawn out of savings. It gets its own inflow trunk, which is how the
        diagram stays flow-conserving without overstating earnings."""
        budget, checking, brokerage = await _budget_with_accounts(db_session)
        group = await create_category_group(db_session, budget, "Savings")
        category = await create_category(db_session, budget, group, "Investments")
        payee = await PayeeRepository(db_session).find_or_create_transfer(
            budget.id, brokerage.id, brokerage.name
        )
        await create_transaction(
            db_session, budget, checking, "500.00", TODAY, payee=payee, category=category
        )

        result = await ReportService(db_session).cash_flow_sankey(budget.id, START, TODAY)

        assert result["total_income"] == Decimal("0"), "a savings draw is not income"
        drawn = [
            link
            for link in result["links"]
            if link["target"] == "__budget__" and str(link["source"]).startswith("drawn_")
        ]
        assert drawn, "and it must not vanish either"
        assert sum(link["value"] for link in drawn) == Decimal("500.00")


class TestTransferPayeeResolution:
    async def test_sets_transfer_account_id(self, db_session):
        budget, _, brokerage = await _budget_with_accounts(db_session)
        payee = await PayeeRepository(db_session).find_or_create_transfer(
            budget.id, brokerage.id, brokerage.name
        )
        assert payee.name == "Transfer : Brokerage"
        assert payee.transfer_account_id == brokerage.id

    async def test_adopts_and_backfills_an_existing_plain_payee(self, db_session):
        """uq_payee_budget_name allows one payee per name, so an unlinked payee
        left by an older import must be adopted, not duplicated."""
        budget, _, brokerage = await _budget_with_accounts(db_session)
        existing = await create_payee(db_session, budget, "Transfer : Brokerage")
        assert existing.transfer_account_id is None

        payee = await PayeeRepository(db_session).find_or_create_transfer(
            budget.id, brokerage.id, brokerage.name
        )
        assert payee.id == existing.id
        assert payee.transfer_account_id == brokerage.id

    async def test_is_idempotent(self, db_session):
        budget, _, brokerage = await _budget_with_accounts(db_session)
        repo = PayeeRepository(db_session)
        first = await repo.find_or_create_transfer(budget.id, brokerage.id, brokerage.name)
        second = await repo.find_or_create_transfer(budget.id, brokerage.id, brokerage.name)
        assert first.id == second.id


class TestTransferPayeeBinding:
    """`find_or_create_transfer` promises that `transfer_account_id` points at
    the account the payee names. It looked the payee up case-insensitively
    while the unique constraint is case-sensitive, so two accounts differing
    only in case shared one payee — and the second silently kept the first's
    binding. Every unlinked leg then resolved its counterpart to the wrong
    account, which can classify a debt payment as savings."""

    async def test_accounts_differing_only_in_case_get_their_own_payees(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        upper = await create_account(db_session, budget, "Savings", on_budget=True)
        lower = await create_account(db_session, budget, "savings", on_budget=True)
        repo = PayeeRepository(db_session)

        a = await repo.find_or_create_transfer(budget.id, upper.id, upper.name)
        b = await repo.find_or_create_transfer(budget.id, lower.id, lower.name)

        assert a.id != b.id
        assert a.transfer_account_id == upper.id
        assert b.transfer_account_id == lower.id

    async def test_reusing_a_renamed_accounts_name_is_refused(self, db_session):
        """Rename "Savings" to "Vacation Fund", then create a new "Savings".
        Re-pointing rewrites what existing transfers mean and returning it
        as-is misfiles every future one, so neither is silently chosen."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        original = await create_account(db_session, budget, "Savings", on_budget=True)
        repo = PayeeRepository(db_session)
        await repo.find_or_create_transfer(budget.id, original.id, "Savings")

        original.name = "Vacation Fund"
        replacement = await create_account(db_session, budget, "Savings2", on_budget=True)
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="different account"):
            await repo.find_or_create_transfer(budget.id, replacement.id, "Savings")
