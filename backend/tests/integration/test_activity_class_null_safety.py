"""The inputs the classifier's first cut did not imagine.

Every case here passed the whole 1,540-test suite while being wrong. They are
grouped by the mechanism rather than the symptom, because three of the four
share one: a SQL expression that evaluates to NULL instead of FALSE, which in
a first-match CASE silently declines to fire.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from igab.db.models import Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ACTIVITY_REASON, ActivityClass
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
MONTH_START = TODAY.replace(day=1)


async def _classify(db_session, txn):
    row = (
        await db_session.execute(
            select(ACTIVITY_CLASS, ACTIVITY_REASON).where(Transaction.id == txn.id)
        )
    ).first()
    return row[0], row[1]


async def _budget(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    return budget, checking


class TestNullPayeeDoesNotVanish:
    """`payee_id IN (subquery)` is UNKNOWN for a NULL payee, and NOT UNKNOWN is
    UNKNOWN — so `~TRANSFER_LEG` dropped every payee-less row, but only once
    the budget contained a transfer payee to make the subquery non-empty. That
    conditionality is why no existing test caught it."""

    async def _sankey_totals(self, db_session, budget):
        r = await ReportService(db_session).cash_flow_sankey(budget.id, MONTH_START, TODAY)
        return r["total_income"], r["total_expense"]

    @pytest.mark.parametrize("with_transfer_payee", [False, True])
    async def test_payee_less_rows_count_either_way(self, db_session, with_transfer_payee):
        budget, checking = await _budget(db_session)
        if with_transfer_payee:
            brokerage = await create_account(
                db_session, budget, "Brokerage", account_type="investment", on_budget=False
            )
            await create_payee(
                db_session, budget, "Transfer : Brokerage", transfer_account_id=brokerage.id
            )
        await create_transaction(db_session, budget, checking, "500.00", TODAY)
        await create_transaction(db_session, budget, checking, "-40.00", TODAY)
        await db_session.flush()

        income, expense = await self._sankey_totals(db_session, budget)

        assert income == Decimal("500.00")
        assert expense == Decimal("40.00")

    async def test_a_payee_less_row_is_not_a_transfer(self, db_session):
        budget, checking = await _budget(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        await create_payee(
            db_session, budget, "Transfer : Brokerage", transfer_account_id=brokerage.id
        )
        txn = await create_transaction(db_session, budget, checking, "-40.00", TODAY)
        await db_session.flush()

        cls, _ = await _classify(db_session, txn)

        assert cls == ActivityClass.SPENDING


class TestNullClassificationIsUnreachable:
    """This suite used to prove the classifier survived a NULL classification.
    b8c3e5a71f42 made the column NOT NULL instead, which is the stronger claim:
    the state that disabled four rules cannot be written in the first place.
    What is left to pin is that the door is actually shut."""

    async def test_the_column_refuses_null(self, db_session):
        budget, _ = await _budget(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        brokerage.classification = None  # type: ignore[assignment]

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_tracked_asset_still_classifies_from_its_type_row(self, db_session):
        """The replacement guarantee: classification is derived from the type
        registry for every account, so the rules always have a value to read."""
        budget, _ = await _budget(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        txn = await create_transaction(db_session, budget, brokerage, "800.00", TODAY)
        await db_session.flush()

        assert brokerage.classification == "asset"
        cls, _ = await _classify(db_session, txn)
        assert cls == ActivityClass.INVESTMENT_RETURN


class TestUncategorizedTransfersOutOfTheBudget:
    """Where the money went decides the class, not whether it was categorized.
    YNAB exports are full of uncategorized tracking-account transfers."""

    async def _linked_transfer(self, db_session, budget, src, dst, amount):
        out = await create_transaction(db_session, budget, src, amount, TODAY)
        into = await create_transaction(db_session, budget, dst, str(-Decimal(amount)), TODAY)
        out.transfer_id, into.transfer_id = into.id, out.id
        await db_session.flush()
        return out, into

    async def test_uncategorized_transfer_to_a_brokerage_is_savings(self, db_session):
        budget, checking = await _budget(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        out, _ = await self._linked_transfer(db_session, budget, checking, brokerage, "-1000.00")

        cls, _ = await _classify(db_session, out)

        assert cls == ActivityClass.SAVINGS

    async def test_uncategorized_transfer_to_a_loan_is_debt_principal(self, db_session):
        budget, checking = await _budget(db_session)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        out, _ = await self._linked_transfer(db_session, budget, checking, loan, "-275.00")

        cls, _ = await _classify(db_session, out)

        assert cls == ActivityClass.DEBT_PRINCIPAL

    async def test_the_tracked_side_stays_neutral(self, db_session):
        """Only the on-budget leg represents money leaving the budget; counting
        the far side too would double it."""
        budget, checking = await _budget(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        _, into = await self._linked_transfer(db_session, budget, checking, brokerage, "-1000.00")

        cls, _ = await _classify(db_session, into)

        assert cls == ActivityClass.TRANSFER_INTERNAL

    async def test_between_two_on_budget_accounts_is_still_neutral(self, db_session):
        budget, checking = await _budget(db_session)
        savings = await create_account(db_session, budget, "Savings", on_budget=True)
        out, into = await self._linked_transfer(db_session, budget, checking, savings, "-300.00")

        assert (await _classify(db_session, out))[0] == ActivityClass.TRANSFER_INTERNAL
        assert (await _classify(db_session, into))[0] == ActivityClass.TRANSFER_INTERNAL

    async def test_the_savings_rate_sees_it(self, db_session):
        budget, checking = await _budget(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
        rta = await create_category(db_session, budget, inflow, "Ready to Assign")
        await create_transaction(db_session, budget, checking, "3000.00", TODAY, category=rta)
        await self._linked_transfer(db_session, budget, checking, brokerage, "-1000.00")

        summary = (await ReportService(db_session).savings_rate(budget.id, months=1))["summary"]

        assert summary["income"] == Decimal("3000.00")
        assert summary["savings"] == Decimal("1000.00")
        assert summary["savings_rate"] == pytest.approx(1 / 3, abs=1e-6)


class TestNegativeInflowIsNegativeIncome:
    """A reversed paycheck reduces income; it is not spending. Sign-gating the
    income rule sent it to the spending default, inflating both the savings-rate
    denominator and every spending average by its full value."""

    async def _reversal_world(self, db_session):
        budget, checking = await _budget(db_session)
        inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
        rta = await create_category(db_session, budget, inflow, "Ready to Assign")
        await create_transaction(db_session, budget, checking, "3000.00", TODAY, category=rta)
        reversal = await create_transaction(
            db_session, budget, checking, "-2000.00", TODAY, category=rta
        )
        await db_session.flush()
        return budget, reversal

    async def test_it_classifies_as_income(self, db_session):
        _, reversal = await self._reversal_world(db_session)
        cls, _ = await _classify(db_session, reversal)
        assert cls == ActivityClass.INCOME

    async def test_it_nets_against_income_rather_than_adding_spending(self, db_session):
        budget, _ = await self._reversal_world(db_session)
        summary = (await ReportService(db_session).savings_rate(budget.id, months=1))["summary"]
        assert summary["income"] == Decimal("1000.00")
        assert summary["spending"] == Decimal("0")

    async def test_a_refund_to_an_ordinary_category_is_still_not_income(self, db_session):
        """The inflow-group carve-out must not swallow refunds, which net
        against their own category's spending."""
        budget, checking = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        refund = await create_transaction(
            db_session, budget, checking, "25.00", TODAY, category=groceries
        )
        await db_session.flush()
        cls, _ = await _classify(db_session, refund)
        assert cls == ActivityClass.SPENDING
