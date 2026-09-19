"""Debt, net worth and what is due — the three domains a tool could not reach.

Each is a thin adapter over a service that already computes the answer, so
what is tested here is the adapter's judgement rather than the arithmetic:
that a loan with no terms is reported as having no payoff date instead of an
invented one, that the horizon on "what is due" means what it says, and that
the shapes are the ones a model can read.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.ai.tools import handlers
from igab.ai.tools.context import build_tool_context

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_scheduled_transaction,
    create_user,
)


async def _ctx(db_session, budget, today: date | None = None):
    return await build_tool_context(db_session, budget.id, today or date(2026, 9, 19))


class TestDebt:
    async def test_a_loan_without_terms_has_no_payoff_date_and_says_so(self, db_session):
        """An imported loan arrives with no rate at all. A payoff date
        guessed for it would be a claim about someone's debt that nobody
        made — the note names the row instead."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        account = await create_account(
            db_session, budget, "Mortgage", account_type="mortgage", on_budget=False
        )
        await db_session.flush()
        await create_liability(
            db_session,
            budget,
            "Mortgage",
            liability_type="mortgage",
            linked_account_id=account.id,
            interest_rate=None,
            minimum_payment=None,
        )
        await db_session.flush()

        result = await handlers.get_debt_status(await _ctx(db_session, budget), {})

        assert len(result["debts"]) == 1
        row = result["debts"][0]
        assert row["name"] == "Mortgage"
        assert row["payoff_date"] is None
        assert row["terms_complete"] is False
        assert "Mortgage" in result["note"]

    async def test_it_reports_every_debt_and_the_total(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        card_account = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card"
        )
        await db_session.flush()
        await create_liability(
            db_session,
            budget,
            "Sapphire Visa",
            liability_type="credit_card",
            linked_account_id=card_account.id,
            interest_rate=Decimal("18.9"),
        )
        await db_session.flush()

        result = await handlers.get_debt_status(await _ctx(db_session, budget), {})
        names = {row["name"] for row in result["debts"]}
        assert "Sapphire Visa" in names
        assert "total_balance" in result


class TestNetWorth:
    async def test_it_returns_a_point_per_month_with_the_latest_called_out(self, db_session):
        """`latest` is kept by name through the size cap: a model asked "what
        is my net worth" must not get a trimmed series with the answer
        summarized away."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await create_account(db_session, budget, "Harborstone")
        await db_session.flush()

        result = await handlers.get_net_worth(await _ctx(db_session, budget), {"months": 3})

        assert len(result["months"]) == 3
        assert result["latest"] is not None
        assert {"month", "assets", "liabilities", "net_worth"} <= set(result["months"][0])

    async def test_the_months_argument_is_clamped_not_trusted(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await db_session.flush()
        result = await handlers.get_net_worth(await _ctx(db_session, budget), {"months": "lots"})
        # Falls back rather than raising: a wrong range is visible on the
        # call, an error is not readable by the person who asked.
        assert len(result["months"]) == 12


class TestScheduled:
    async def test_only_what_falls_inside_the_horizon(self, db_session):
        today = date(2026, 9, 19)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        account = await create_account(db_session, budget, "Harborstone")
        group = await create_category_group(db_session, budget, "Everyday")
        rent = await create_category(db_session, budget, group, "Rent")
        await db_session.flush()

        await create_scheduled_transaction(
            db_session,
            budget,
            account,
            amount="-1200",
            frequency="monthly",
            next_occurrence_date=today + timedelta(days=5),
            category=rent,
        )
        await create_scheduled_transaction(
            db_session,
            budget,
            account,
            amount="-90",
            frequency="yearly",
            next_occurrence_date=today + timedelta(days=200),
            category=rent,
        )
        await db_session.flush()

        ctx = await _ctx(db_session, budget, today)
        soon = await handlers.list_scheduled(ctx, {"days_ahead": 30})
        assert len(soon["rows"]) == 1
        assert soon["rows"][0]["amount"] == -1200

        far = await handlers.list_scheduled(ctx, {"days_ahead": 365})
        assert len(far["rows"]) == 2

    async def test_soonest_first(self, db_session):
        today = date(2026, 9, 19)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        account = await create_account(db_session, budget, "Harborstone")
        await db_session.flush()
        for days, amount in ((10, "-50"), (2, "-20"), (6, "-30")):
            await create_scheduled_transaction(
                db_session,
                budget,
                account,
                amount=amount,
                frequency="monthly",
                next_occurrence_date=today + timedelta(days=days),
            )
        await db_session.flush()

        result = await handlers.list_scheduled(await _ctx(db_session, budget, today), {})
        assert [row["amount"] for row in result["rows"]] == [-20, -30, -50]
