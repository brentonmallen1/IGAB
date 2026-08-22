"""Savings rate: how much of what came in was kept.

The number derkus asked for. Its honesty rests on two things the class
partition provides:

- growth inside a tracked account is `investment_return`, not saving, so the
  rate does not rise in a bull market without the household doing anything;
- a refund is not income, so it cannot quietly inflate the denominator.

Rates are None when there was no income. "No income recorded" and "saved
nothing out of real income" are different facts and must not share a value.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.tag_repo import TagRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
    create_transaction,
    create_user,
)

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


async def _world(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return {
        "budget": budget,
        "checking": await create_account(db_session, budget, "Checking", on_budget=True),
        "brokerage": await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        ),
        "loan": await create_account(
            db_session, budget, "Auto Loan", account_type="loan", on_budget=False
        ),
        "group": await create_category_group(db_session, budget, "Everyday"),
    }


async def _rate(db_session, budget, months: int = 1) -> dict:
    return await ReportService(db_session).savings_rate(budget.id, months=months)


async def _transfer_payee(db_session, budget, account):
    return await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, account.id, account.name
    )


class TestTheRate:
    async def test_income_savings_and_spending_split_out(self, db_session):
        w = await _world(db_session)
        cat_inv = await create_category(db_session, w["budget"], w["group"], "Investments")
        cat_food = await create_category(db_session, w["budget"], w["group"], "Groceries")
        payee = await _transfer_payee(db_session, w["budget"], w["brokerage"])

        await create_transaction(db_session, w["budget"], w["checking"], "4000.00", THIS_MONTH)
        await create_transaction(
            db_session, w["budget"], w["checking"], "-1000.00", THIS_MONTH,
            category=cat_inv, payee=payee,
        )
        await create_transaction(
            db_session, w["budget"], w["checking"], "-500.00", THIS_MONTH, category=cat_food
        )

        result = await _rate(db_session, w["budget"])
        month = result["months"][-1]
        assert month["income"] == Decimal("4000.00")
        assert month["savings"] == Decimal("1000.00")
        assert month["spending"] == Decimal("500.00")
        assert month["savings_rate"] == 0.25

    async def test_debt_principal_is_separate_from_savings(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w["budget"], w["group"], "Car Payment")
        payee = await _transfer_payee(db_session, w["budget"], w["loan"])

        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        await create_transaction(
            db_session, w["budget"], w["checking"], "-250.00", THIS_MONTH,
            category=cat, payee=payee,
        )

        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["savings"] == Decimal("0")
        assert month["debt_principal"] == Decimal("250.00")
        assert month["savings_rate"] == 0.0
        assert month["savings_rate_with_debt"] == 0.25

    async def test_market_growth_does_not_count_as_saving(self, db_session):
        """The distinction that keeps the number meaningful."""
        w = await _world(db_session)
        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        await create_transaction(db_session, w["budget"], w["brokerage"], "5000.00", THIS_MONTH)

        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["savings"] == Decimal("0")
        assert month["income"] == Decimal("1000.00")
        assert month["savings_rate"] == 0.0

    async def test_a_savings_tag_counts_without_any_transfer(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w["budget"], w["group"], "Emergency Fund")
        tag = await create_tag(db_session, w["budget"], "Savings", system_key="savings")
        await TagRepository(db_session).set_category_tags(cat.id, [tag.id])

        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        await create_transaction(
            db_session, w["budget"], w["checking"], "-300.00", THIS_MONTH, category=cat
        )

        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["savings"] == Decimal("300.00")
        assert month["savings_rate"] == 0.3


class TestEdgeCases:
    async def test_no_income_gives_no_rate(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w["budget"], w["group"], "Groceries")
        await create_transaction(
            db_session, w["budget"], w["checking"], "-50.00", THIS_MONTH, category=cat
        )
        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["income"] == Decimal("0")
        assert month["savings_rate"] is None, "no income is not the same as saving nothing"

    async def test_empty_budget_returns_a_full_series_of_none(self, db_session):
        w = await _world(db_session)
        result = await _rate(db_session, w["budget"], months=6)
        assert len(result["months"]) == 6
        assert all(m["savings_rate"] is None for m in result["months"])
        assert result["summary"]["savings_rate"] is None

    async def test_saving_more_than_income_exceeds_one(self, db_session):
        """Drawing down a balance is real and must not be clamped — a rate
        over 100% is information, not an error."""
        w = await _world(db_session)
        cat = await create_category(db_session, w["budget"], w["group"], "Investments")
        payee = await _transfer_payee(db_session, w["budget"], w["brokerage"])
        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        await create_transaction(
            db_session, w["budget"], w["checking"], "-1500.00", THIS_MONTH,
            category=cat, payee=payee,
        )
        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["savings_rate"] == 1.5

    async def test_a_refund_does_not_inflate_income(self, db_session):
        w = await _world(db_session)
        cat = await create_category(db_session, w["budget"], w["group"], "Groceries")
        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        await create_transaction(
            db_session, w["budget"], w["checking"], "40.00", THIS_MONTH, category=cat
        )
        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["income"] == Decimal("1000.00")
        assert month["spending"] == Decimal("-40.00"), "a refund nets against spending"

    async def test_internal_transfer_touches_nothing(self, db_session):
        w = await _world(db_session)
        savings_acct = await create_account(
            db_session, w["budget"], "Savings", on_budget=True
        )
        payee = await _transfer_payee(db_session, w["budget"], savings_acct)
        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        await create_transaction(
            db_session, w["budget"], w["checking"], "-400.00", THIS_MONTH, payee=payee
        )
        month = (await _rate(db_session, w["budget"]))["months"][-1]
        assert month["income"] == Decimal("1000.00")
        assert month["savings"] == Decimal("0")
        assert month["spending"] == Decimal("0")

    async def test_summary_totals_across_months(self, db_session):
        w = await _world(db_session)
        await create_transaction(db_session, w["budget"], w["checking"], "1000.00", THIS_MONTH)
        result = await _rate(db_session, w["budget"], months=3)
        assert result["summary"]["income"] == Decimal("1000.00")
        assert len(result["months"]) == 3


class TestEndpoint:
    async def test_returns_a_series(self, api_client, db_session):
        user = api_client.test_user
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        await create_transaction(db_session, budget, checking, "2000.00", THIS_MONTH)
        payee = await create_payee(db_session, budget, "Employer")
        assert payee is not None

        resp = await api_client.get(
            f"/api/v1/{budget.id}/reports/savings-rate", params={"months": 3}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["months"]) == 3
        assert Decimal(body["summary"]["income"]) == Decimal("2000.00")
