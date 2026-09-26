"""Money filed INTO an envelope, and when a category counts as over its plan.

The plan reports — Budget vs Actual, Cumulative Variance, Plan vs Reality —
counted outflows only. A transfer from savings into a Medical envelope that
paid a medical bill read as the whole bill overspent, on all three at once,
while the budget page showed the envelope on plan; about half of one real
budget's cumulative "overspending" was that. And "over" had no tolerance, so a
mortgage paid a few cents past its assignment three months running was named
a chronic overspender, which the Guide then repeated.

Each test is one of those divergences, named for what used to go wrong. The
rule is `domain.plan` (`plan_effect`, `plan_outcome`, `is_chronic`); the rows
are `services/plan_ledger.py`. Amounts are invented and round.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import update

from igab.db.models import Transaction
from igab.domain.dates import add_months
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    money,
    tag_with_system_tags,
)

D = Decimal
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)
# The 1st of the month, or the day it is: never a future date.
EARLY = THIS_MONTH


def back(n: int) -> date:
    return add_months(THIS_MONTH, -n)


async def _world(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Everyday")
    return budget, checking, hysa, group


async def _moved_in(db_session, budget, source, checking, amount: str, day: date, category):
    """A transfer from `source` into checking, the on-budget leg filed to
    `category` — how a household files savings it moved to pay a bill."""
    _, to_leg = await create_transfer(db_session, budget, source, checking, amount, day)
    await db_session.execute(
        update(Transaction).where(Transaction.id == to_leg.id).values(category_id=category.id)
    )
    await db_session.flush()


def _row(body: dict, category) -> dict:
    return next(c for c in body["categories"] if c["category_id"] == str(category.id))


class TestMoneyMovedInRaisesThePlan:
    """2,000 moved in from savings, 2,000 medical bill paid: on plan."""

    async def _medical(self, db_session, user):
        budget, checking, hysa, group = await _world(db_session, user)
        medical = await create_category(db_session, budget, group, "Medical")
        await _moved_in(db_session, budget, hysa, checking, "2000.00", EARLY, medical)
        await create_transaction(db_session, budget, checking, "-2000.00", EARLY, category=medical)
        return budget, medical

    async def test_budget_vs_actual_reads_it_on_plan(self, db_session, api_client):
        budget, medical = await self._medical(db_session, api_client.test_user)
        bva = await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY)

        row = _row(bva, medical)
        assert (row["assigned"], row["moved_in"], row["plan"]) == (D("0"), D("2000"), D("2000"))
        assert (row["spent"], row["variance"], row["overspent"]) == (D("2000"), D("0"), False)
        # It read -2,000 and "no plan" — the percentage of nothing.
        assert row["variance_pct"] == 0.0
        assert bva["total_variance"] == D("0")

    async def test_cumulative_variance_reads_it_on_plan(self, db_session, api_client):
        budget, _ = await self._medical(db_session, api_client.test_user)
        (point,) = await ReportService(db_session).cumulative_variance(budget.id, months=1)

        assert (point["moved_in"], point["planned"], point["actual_spent"]) == (
            D("2000"),
            D("2000"),
            D("2000"),
        )
        assert point["monthly_variance"] == D("0")
        assert point["budget_assigned"] == D("0")

    async def test_plan_vs_reality_reads_it_on_plan(self, db_session, api_client):
        budget, medical = await self._medical(db_session, api_client.test_user)
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=3)

        cell = _row(pvr, medical)["monthly"][-1]
        assert (cell["plan"], cell["spent"], cell["over"]) == (D("2000"), D("2000"), False)
        assert _row(pvr, medical)["months_over"] == 0

    async def test_spending_past_what_moved_in_is_still_over(self, db_session, api_client):
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        medical = await create_category(db_session, budget, group, "Medical")
        await create_budget_assignment(db_session, budget, medical, THIS_MONTH, "100.00")
        await _moved_in(db_session, budget, hysa, checking, "2000.00", EARLY, medical)
        await create_transaction(db_session, budget, checking, "-2150.00", EARLY, category=medical)

        bva = await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY)

        row = _row(bva, medical)
        assert (row["plan"], row["variance"], row["overspent"]) == (D("2100"), D("-50"), True)

    async def test_a_deposit_into_a_savings_envelope_raises_its_plan(self, db_session, api_client):
        """A bonus filed to a sent-out Savings envelope and then sent on to
        savings: the deposit funds the envelope, the send-out is spent against
        it, and the two meet at zero. Read as nothing, the send-out was a 1,000
        overrun on a plan of nothing."""
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        savings = await create_category(db_session, budget, group, "Savings")
        await tag_with_system_tags(db_session, savings, "savings")
        await create_transaction(db_session, budget, checking, "1000.00", EARLY, category=savings)
        await create_transfer(
            db_session, budget, checking, hysa, "1000.00", EARLY, category=savings
        )

        bva = await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY)

        row = _row(bva, savings)
        assert (row["moved_in"], row["spent"], row["variance"]) == (D("1000"), D("1000"), D("0"))
        assert row["overspent"] is False

    async def test_a_starting_balance_filed_to_an_envelope_moves_nothing(
        self, db_session, api_client
    ):
        """An opening is where counting begins, not money moved in. Were it
        plan, a hand-filed opening would pad an envelope's plan by the
        account's whole balance."""
        from .factories import create_payee

        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        misc = await create_category(db_session, budget, group, "Misc")
        opening = await create_payee(db_session, budget, "Starting Balance")
        await create_transaction(
            db_session, budget, checking, "5000.00", EARLY, category=misc, payee=opening
        )
        await create_transaction(db_session, budget, checking, "-40.00", EARLY, category=misc)

        bva = await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY)

        row = _row(bva, misc)
        assert (row["moved_in"], row["plan"], row["spent"]) == (D("0"), D("0"), D("40"))


class TestACardEnvelopeIsNotAPlan:
    """A card's envelope plans paydown, never spending: counted as a plan it
    was assigned and never spent, a phantom underspend on Budget vs Actual and
    a Variance line that climbed with every paydown."""

    async def test_it_is_on_no_plan_report(self, db_session, api_client):
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
        payments = await create_category_group(db_session, budget, "Credit Card Payments")
        envelope = await create_category(db_session, budget, payments, "Sapphire Visa")
        envelope.linked_account_id = card.id
        await db_session.flush()
        await create_budget_assignment(db_session, budget, envelope, THIS_MONTH, "600.00")
        # An older import filed a savings transfer into it.
        await _moved_in(db_session, budget, hysa, checking, "300.00", EARLY, envelope)

        reports = ReportService(db_session)
        bva = await reports.budget_vs_actual(budget.id, THIS_MONTH, TODAY)
        (point,) = await reports.cumulative_variance(budget.id, months=1)
        pvr = await reports.plan_vs_reality(budget.id, months=3)

        assert bva["categories"] == []
        assert (point["planned"], point["monthly_variance"]) == (D("0"), D("0"))
        assert pvr["categories"] == []


class TestOverHasATolerance:
    """Over by at least $1 AND 1% of the plan."""

    async def _mortgage(self, db_session, user, over_by: str):
        budget, checking, _, group = await _world(db_session, user)
        mortgage = await create_category(db_session, budget, group, "Mortgage")
        # Three complete months and the running one: only complete months
        # are held to the tolerance (`ReportWindow`).
        for n in (0, 1, 2, 3):
            await create_budget_assignment(db_session, budget, mortgage, back(n), "1500.00")
            paid = D("1500.00") + D(over_by)
            await create_transaction(
                db_session,
                budget,
                checking,
                -paid,
                min(back(n) + timedelta(days=4), TODAY),
                category=mortgage,
            )
        return budget, mortgage

    async def test_cents_over_three_months_are_not_chronic(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "0.27")
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=6)

        row = _row(pvr, mortgage)
        assert (row["months_over"], row["chronic"], pvr["chronic_count"]) == (0, False, 0)
        # The arithmetic is still there; only the verdict is tolerant.
        assert row["monthly"][-1]["variance"] == D("-0.27")
        assert row["monthly"][-1]["over"] is False

    async def test_past_a_dollar_but_under_one_percent_is_not_over(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "14.00")
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=6)

        assert _row(pvr, mortgage)["months_over"] == 0

    async def test_one_percent_and_a_dollar_three_times_is_chronic(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "15.00")
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=6)

        row = _row(pvr, mortgage)
        assert (row["months_over"], row["chronic"]) == (3, True)
        assert row["avg_overspend"] == D("15.00")

    async def test_budget_vs_actual_uses_the_same_verdict(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "0.27")
        bva = await ReportService(db_session).budget_vs_actual(budget.id, back(2), TODAY)

        assert _row(bva, mortgage)["overspent"] is False


class TestASinkingFundIsNeverChronic:
    """A quarterly premium paid from a Long-term expense envelope is "over"
    its monthly assignment every time it lands: the plan working."""

    async def _premium(self, db_session, user):
        budget, checking, _, group = await _world(db_session, user)
        premium = await create_category(db_session, budget, group, "Home Insurance")
        await tag_with_system_tags(db_session, premium, "long_term_expense")
        for n in (0, 1, 2, 3, 4, 5):
            await create_budget_assignment(db_session, budget, premium, back(n), "100.00")
        for n in (1, 3, 5):
            await create_transaction(
                db_session, budget, checking, "-300.00", back(n), category=premium
            )
        return budget, premium

    async def test_plan_vs_reality_does_not_flag_it(self, db_session, api_client):
        budget, premium = await self._premium(db_session, api_client.test_user)
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=6)

        row = _row(pvr, premium)
        # Over in the months the premium landed — that is still true — but
        # never chronic, and the row says why.
        assert row["months_over"] == 3
        assert (row["chronic"], row["sinking_fund"], pvr["chronic_count"]) == (False, True, 0)

    async def test_the_guide_reads_the_same_flag(self, db_session, api_client):
        """One rule: the checkup's chronic count is the report's."""
        budget, premium = await self._premium(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Second Checking")
        group = await create_category_group(db_session, budget, "Fun")
        dining = await create_category(db_session, budget, group, "Dining Out")
        for n in (1, 2, 3):
            await create_transaction(
                db_session, budget, checking, "-40.00", back(n), category=dining
            )
        await db_session.commit()

        body = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        pvr = (await api_client.get(f"/api/v1/{budget.id}/reports/plan-vs-reality")).json()

        metric = next(m for m in body["metrics"] if m["key"] == "chronic_overspend")
        assert money(metric["value"]) == D(pvr["chronic_count"]) == D("1")
        assert metric["names"] == ["Dining Out"]


class TestOneSpentAcrossTheFamily:
    """Category History, Volatility and Anomalies read the plan ledger's
    spent, so a month reads the same on every tab."""

    async def test_category_history_spent_is_the_plan_reports_spent(self, db_session, api_client):
        """History drew `max(-activity, 0)`: the budget page's Activity nets
        the 2,000 moved in, so the medical bill read as no spending there and
        as the whole bill on Plan vs Reality."""
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        medical = await create_category(db_session, budget, group, "Medical")
        await _moved_in(db_session, budget, hysa, checking, "2000.00", EARLY, medical)
        await create_transaction(db_session, budget, checking, "-2000.00", EARLY, category=medical)
        await create_transaction(db_session, budget, checking, "-100.00", back(1), category=medical)
        await create_transaction(db_session, budget, checking, "30.00", back(1), category=medical)
        await db_session.commit()

        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(medical.id), "months": 3},
        )
        assert r.status_code == 200, r.text
        months = r.json()["months"]
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=3)
        cells = _row(pvr, medical)["monthly"]

        assert [money(m["spent"]) for m in months] == [c["spent"] for c in cells]
        assert money(months[-1]["spent"]) == D("2000")
        assert money(months[-1]["moved_in"]) == D("2000")
        # The activity column is still the budget page's: net of everything.
        assert money(months[-1]["activity"]) == D("0")
        # Last month: 100 spent, 30 refunded.
        assert money(months[-2]["spent"]) == D("70")

    async def test_its_average_is_over_complete_months(self, db_session, api_client):
        """The running month is month-to-date; averaged in, it read a steady
        category as falling for most of every month."""
        budget, checking, _, group = await _world(db_session, api_client.test_user)
        groceries = await create_category(db_session, budget, group, "Groceries")
        for n in (1, 2):
            await create_transaction(
                db_session, budget, checking, "-400.00", back(n), category=groceries
            )
        await create_transaction(db_session, budget, checking, "-10.00", EARLY, category=groceries)
        await db_session.commit()

        body = (
            await api_client.get(
                f"/api/v1/{budget.id}/reports/category-history",
                params={"category_id": str(groceries.id), "months": 3},
            )
        ).json()

        assert (money(body["average_spent"]), body["months_averaged"]) == (D("400.00"), 2)

    async def test_volatility_nets_refunds_and_leaves_saving_out(self, db_session, api_client):
        """It read `abs(amount)` of every outflow of every class: a refund made
        a month bigger, and a transfer to a brokerage filed to an envelope
        swung the category as if it were spending."""
        budget, checking, _, group = await _world(db_session, api_client.test_user)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        home = await create_category(db_session, budget, group, "Home")
        await create_transaction(db_session, budget, checking, "-100.00", back(1), category=home)
        await create_transaction(db_session, budget, checking, "40.00", back(1), category=home)
        await create_transaction(db_session, budget, checking, "-60.00", back(2), category=home)
        await create_transfer(
            db_session, budget, checking, brokerage, "5000.00", back(2), category=home
        )

        result = await ReportService(db_session).category_volatility(budget.id, months=2)

        (row,) = result["categories"]
        assert (row["min_val"], row["max_val"]) == (D("60"), D("60"))
        assert row["std_dev"] == D("0")


class TestPlanVsRealityServesItsRunningMonth:
    async def test_the_newest_column_is_marked(self, db_session, api_client):
        budget, *_ = await _world(db_session, api_client.test_user)
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=3)
        assert pvr["running_month"] == THIS_MONTH
        assert pvr["months"][-1] == THIS_MONTH


class TestVarianceIsThePlanMatrixSummed:
    """Cumulative Variance's month is Plan vs Reality's column, summed — the
    identity the "Plan vs Spent" merge will draw as a totals row."""

    async def test_every_month_agrees(self, db_session, api_client):
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        a = await create_category(db_session, budget, group, "Car Repairs")
        b = await create_category(db_session, budget, group, "Dining Out")
        await create_budget_assignment(db_session, budget, a, back(1), "-300.00")
        await create_budget_assignment(db_session, budget, b, back(1), "300.00")
        await create_transaction(db_session, budget, checking, "-350.00", back(1), category=b)
        await _moved_in(db_session, budget, hysa, checking, "80.00", EARLY, a)
        await create_transaction(db_session, budget, checking, "-100.00", EARLY, category=a)

        reports = ReportService(db_session)
        variance = await reports.cumulative_variance(budget.id, months=3)
        pvr = await reports.plan_vs_reality(budget.id, months=3)

        for i, point in enumerate(variance):
            column = [c["monthly"][i] for c in pvr["categories"]]
            assert point["monthly_variance"] == sum((c["variance"] for c in column), D("0"))
            assert point["planned"] == sum((c["plan"] for c in column), D("0"))
            assert point["planned"] - point["actual_spent"] == point["monthly_variance"]
        # Last month: the drain is no plan (not -300) and Dining is 50 over.
        assert variance[-2]["monthly_variance"] == D("-50")
        # This month, drawn but not in the drift: 80 moved in, 100 spent.
        assert variance[-1]["monthly_variance"] == D("-20")
        assert variance[-1]["cumulative_variance"] is None
