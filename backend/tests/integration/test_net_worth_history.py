"""Net worth at a date has one rule, and these pin its parts.

`AccountRepository.balances_through` is every account's balance at a list of
days in one statement; `net_worth_history` and the Overview card both read it
through `ReportService._balance_sheets`. It replaced a polars pass that
fetched every parent row in the budget, beside a second hand-spelled SQL sum
for the card — two implementations whose date bounds had already drifted.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.repositories.account_repo import AccountRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_liability_snapshot,
    create_transaction,
    create_user,
)

TODAY = date.today()
MONTH_START = TODAY.replace(day=1)
JAN, FEB, MAR = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)


async def _budget(db_session):
    return await create_budget(db_session, await create_user(db_session))


class TestBalancesThrough:
    async def test_a_balance_is_cumulative_across_the_cutoffs(self, db_session):
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, "Checking")
        for day, amount in (
            (date(2026, 1, 10), "1000.00"),
            (date(2026, 2, 10), "-400.00"),
            (date(2026, 3, 10), "250.00"),
        ):
            await create_transaction(db_session, budget, checking, amount, day)

        got = await AccountRepository(db_session).balances_through(budget.id, [JAN, FEB, MAR])

        assert got == {checking.id: (0, [Decimal("1000"), Decimal("600"), Decimal("850")])}

    async def test_rows_older_than_the_first_cutoff_open_it(self, db_session):
        """The opening point is everything that happened up to then, not
        that month's activity — a five-year-old savings account does not
        start the chart at zero."""
        budget = await _budget(db_session)
        savings = await create_account(db_session, budget, "Savings", account_type="savings")
        await create_transaction(db_session, budget, savings, "5000.00", date(2021, 6, 1))
        await create_transaction(db_session, budget, savings, "100.00", date(2026, 3, 2))

        got = await AccountRepository(db_session).balances_through(budget.id, [FEB, MAR])

        assert got[savings.id] == (0, [Decimal("5000"), Decimal("5100")])

    async def test_a_cutoff_counts_its_own_day_and_nothing_after_the_last(self, db_session):
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, "Checking")
        await create_transaction(db_session, budget, checking, "300.00", JAN)
        await create_transaction(db_session, budget, checking, "20.00", FEB)
        await create_transaction(db_session, budget, checking, "900.00", FEB + timedelta(days=1))
        # Only after the last cutoff: not on the sheet at all.
        later = await create_account(db_session, budget, "Later")
        await create_transaction(db_session, budget, later, "50.00", MAR)

        got = await AccountRepository(db_session).balances_through(budget.id, [JAN, FEB])

        assert got == {checking.id: (0, [Decimal("300"), Decimal("320")])}

    async def test_an_account_with_no_rows_yet_starts_later_not_at_zero(self, db_session):
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, "Checking")
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        await create_transaction(db_session, budget, checking, "300.00", date(2026, 1, 5))
        await create_transaction(db_session, budget, brokerage, "900.00", date(2026, 2, 5))

        got = await AccountRepository(db_session).balances_through(budget.id, [JAN, FEB])

        assert got[checking.id][0] == 0
        # February's index — January's stack must not carry a brokerage tile.
        assert got[brokerage.id][0] == 1

    async def test_only_balance_rows_count(self, db_session):
        """BALANCE_ROW, composed rather than respelled: a pending hold, a
        deleted row and a split's children are not the account's money
        (the parent already carries the children)."""
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, "Checking")
        parent = await create_transaction(
            db_session, budget, checking, "-100.00", JAN, is_split=True
        )
        for leg in ("-60.00", "-40.00"):
            await create_transaction(
                db_session, budget, checking, leg, JAN, parent_transaction_id=parent.id
            )
        await create_transaction(db_session, budget, checking, "-25.00", JAN, cleared="pending")
        await create_transaction(db_session, budget, checking, "-7.00", JAN, is_deleted=True)

        got = await AccountRepository(db_session).balances_through(budget.id, [JAN])

        assert got == {checking.id: (0, [Decimal("-100")])}

    async def test_cutoffs_must_ascend(self, db_session):
        repo = AccountRepository(db_session)
        budget = await _budget(db_session)
        assert await repo.balances_through(budget.id, []) == {}
        with pytest.raises(ValueError):
            await repo.balances_through(budget.id, [FEB, JAN])


class TestNetWorthHistory:
    async def test_an_account_is_absent_before_its_first_row(self, db_session):
        """The skip that keeps an unopened account off earlier points had
        no test on the report itself: dropping it drew a zero tile for an
        account in the months before it opened, and no test failed."""
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, "Checking")
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        await create_transaction(
            db_session, budget, checking, "1000.00", MONTH_START - timedelta(days=70)
        )
        await create_transaction(db_session, budget, brokerage, "900.00", MONTH_START)

        points = await ReportService(db_session).net_worth_history(budget.id, months=3)

        oldest = {a["account_id"] for a in points[0]["accounts"]}
        newest = {a["account_id"] for a in points[-1]["accounts"]}
        assert oldest == {str(checking.id)}
        assert newest == {str(checking.id), str(brokerage.id)}
        assert points[-1]["net_worth"] == Decimal("1900.00")

    async def test_an_empty_register_still_owes_from_the_day_it_was_recorded(self, db_session):
        """An empty register had a loop of its own, marking the newest point
        with the old countdown's `i == 0` after the main loop had turned the
        right way round. It goes through the one path now; a debt recorded
        this month stands on the newest point only."""
        budget = await _budget(db_session)
        loan = await create_liability(
            db_session, budget, "Harborstone Loan", manual_balance=Decimal("8000.00")
        )
        await create_liability_snapshot(db_session, loan, TODAY, Decimal("8000.00"))

        points = await ReportService(db_session).net_worth_history(budget.id, months=3)

        assert [p["date"] for p in points][-1] == MONTH_START
        assert [p["net_worth"] for p in points] == [
            Decimal("0"),
            Decimal("0"),
            Decimal("-8000.00"),
        ]
        assert all(p["accounts"] == [] for p in points)
