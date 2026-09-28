"""Money filed INTO an envelope, and when a category counts as over its plan.

The plan reports — Budget vs Actual, Cumulative Variance, Plan vs Reality —
counted outflows only. A transfer from savings into a Medical envelope that
paid a medical bill read as the whole bill overspent, on all three at once,
while the budget page showed the envelope on plan; about half of one real
budget's cumulative "overspending" was that. And "over" had no tolerance, so a
mortgage paid a few cents past its assignment three months running was named
a chronic overspender, which the Guide then repeated.

Each test is one of those divergences, named for what used to go wrong. The
rule is `domain.plan` (`plan_effect`, `envelope_outcome`, `is_chronic`); the
rows are `services/plan_ledger.py`. Since 2026-09-28 carryover counts: a month
carries in what the one before left, `left` is the budget page's Available,
and a month is over only when that went negative. Amounts are invented and
round.
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
    """2,000 moved in from savings, 2,000 medical bill paid: funded 2,000,
    spent 2,000, nothing left and nothing overspent — as the budget page
    shows it."""

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
        assert (row["assigned"], row["moved_in"], row["funded"]) == (D("0"), D("2000"), D("2000"))
        # It read 2,000 over a plan of nothing.
        assert (row["spent"], row["left"], row["overspent"], row["over"]) == (
            D("2000"),
            D("0"),
            D("0"),
            False,
        )
        assert bva["total_overspent"] == D("0")

    async def test_the_month_total_reads_it_on_plan(self, db_session, api_client):
        budget, _ = await self._medical(db_session, api_client.test_user)
        (point,) = (await ReportService(db_session).plan_vs_spent(budget.id, months=1))[
            "month_totals"
        ][-1:]

        assert (point["moved_in"], point["funded"], point["spent"]) == (
            D("2000"),
            D("2000"),
            D("2000"),
        )
        assert (point["left"], point["overspent"]) == (D("0"), D("0"))
        assert point["assigned"] == D("0")

    async def test_plan_vs_reality_reads_it_on_plan(self, db_session, api_client):
        budget, medical = await self._medical(db_session, api_client.test_user)
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=3)

        cell = _row(pvr, medical)["monthly"][-1]
        assert (cell["funded"], cell["spent"], cell["left"], cell["over"]) == (
            D("2000"),
            D("2000"),
            D("0"),
            False,
        )
        assert _row(pvr, medical)["months_over"] == 0

    async def test_spending_past_what_moved_in_is_still_over(self, db_session, api_client):
        """100 assigned and 2,000 moved in fund 2,100; 2,150 spent leaves the
        page at -50, which Ready to Assign covers."""
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        medical = await create_category(db_session, budget, group, "Medical")
        await create_budget_assignment(db_session, budget, medical, THIS_MONTH, "100.00")
        await _moved_in(db_session, budget, hysa, checking, "2000.00", EARLY, medical)
        await create_transaction(db_session, budget, checking, "-2150.00", EARLY, category=medical)

        bva = await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY)

        row = _row(bva, medical)
        assert (row["funded"], row["overspent"], row["over"]) == (D("2100"), D("50"), True)
        # The span leaves what the next month would carry: nothing.
        assert row["left"] == D("0")

    async def test_a_deposit_into_a_savings_envelope_funds_it(self, db_session, api_client):
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
        assert (row["moved_in"], row["funded"], row["spent"], row["left"]) == (
            D("1000"),
            D("1000"),
            D("1000"),
            D("0"),
        )
        assert (row["other"], row["over"]) == (D("0"), False)

    async def test_a_starting_balance_filed_to_an_envelope_moves_nothing(
        self, db_session, api_client
    ):
        """An opening is where counting begins, not money moved in: funded
        stays 0. Were it funding, a hand-filed opening would pad an envelope's
        plan by the account's whole balance.

        The budget page's Available does hold it — 5,000 less the 40 spent —
        and `left` is that figure, so the gap is served as `other` (the
        deliberate divergence `EnvelopeOutcome.other` names), not hidden."""
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
        assert (row["moved_in"], row["funded"], row["spent"]) == (D("0"), D("0"), D("40"))
        assert (row["other"], row["left"], row["overspent"]) == (D("5000"), D("4960"), D("0"))


class TestMoneyMovedOutLowersThePlan:
    """The mirror (owner's call, 2026-09-26): money moved out of an envelope
    and not spent unfunds it. Read as nothing, a Mortgage envelope paid by a
    principal transfer read underspent by the whole payment every month, and a
    brokerage transfer read as money left unspent."""

    async def _mortgage(self, db_session, user):
        """1,500 assigned to an envelope nobody tagged Debt principal, paid by
        a 1,500 principal transfer to the tracked loan."""
        budget, checking, _, group = await _world(db_session, user)
        loan = await create_account(
            db_session, budget, "Harborstone Mortgage", account_type="loan", on_budget=False
        )
        mortgage = await create_category(db_session, budget, group, "Mortgage")
        await create_budget_assignment(db_session, budget, mortgage, THIS_MONTH, "1500.00")
        await create_transfer(
            db_session, budget, checking, loan, "1500.00", EARLY, category=mortgage
        )
        return budget, checking, mortgage

    async def _brokerage(self, db_session, user):
        """600 assigned, 400 of it sent to a brokerage, 180 spent."""
        budget, checking, _, group = await _world(db_session, user)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        fun = await create_category(db_session, budget, group, "Fun Money")
        await create_budget_assignment(db_session, budget, fun, THIS_MONTH, "600.00")
        await create_transfer(
            db_session, budget, checking, brokerage, "400.00", EARLY, category=fun
        )
        await create_transaction(db_session, budget, checking, "-180.00", EARLY, category=fun)
        return budget, fun

    async def test_a_mortgage_paid_by_principal_is_a_row_on_plan_on_both_reports(
        self, db_session, api_client
    ):
        budget, _, mortgage = await self._mortgage(db_session, api_client.test_user)
        reports = ReportService(db_session)
        bva = await reports.budget_vs_actual(budget.id, THIS_MONTH, TODAY)
        (point,) = (await reports.plan_vs_spent(budget.id, months=1))["month_totals"][-1:]
        pvr = await reports.plan_vs_spent(budget.id, months=3)

        # Still a row — the owner would read a missing row as the mortgage
        # missing — and on plan: assigned 1,500, moved out 1,500, nothing
        # left. It was a 1,500 underspend.
        row = _row(bva, mortgage)
        assert (row["assigned"], row["moved_out"], row["funded"], row["spent"]) == (
            D("1500"),
            D("1500"),
            D("0"),
            D("0"),
        )
        assert (row["left"], row["overspent"], row["over"]) == (D("0"), D("0"), False)
        assert (bva["total_left"], bva["total_overspent"]) == (D("0"), D("0"))
        assert (point["moved_out"], point["funded"], point["left"]) == (
            D("1500"),
            D("0"),
            D("0"),
        )
        # A Plan vs Reality row too, its month active and on plan.
        cell = _row(pvr, mortgage)["monthly"][-1]
        assert (cell["assigned"], cell["moved_out"], cell["funded"], cell["left"]) == (
            D("1500"),
            D("1500"),
            D("0"),
            D("0"),
        )
        assert (cell["active"], cell["over"]) == (True, False)

    async def test_a_quiet_envelope_is_still_no_row(self, db_session, api_client):
        """Only nothing at all — assigned, moved in, moved out, spent — drops a
        row (`PlanMonth.quiet`). An envelope that exists and saw no activity
        is not a finding on either report."""
        budget, checking, _, group = await _world(db_session, api_client.test_user)
        idle = await create_category(db_session, budget, group, "Idle")
        await create_transaction(db_session, budget, checking, "-10.00", EARLY)
        reports = ReportService(db_session)
        bva = await reports.budget_vs_actual(budget.id, THIS_MONTH, TODAY)
        pvr = await reports.plan_vs_spent(budget.id, months=3)
        for body in (bva, pvr):
            assert str(idle.id) not in {c["category_id"] for c in body["categories"]}

    async def test_a_debt_payment_short_of_its_plan_leaves_the_rest(self, db_session, api_client):
        """Plan vs Reality's cell, where the envelope carries a finding: 1,500
        assigned, 1,500 moved out, 60 spent on a late fee — the envelope ends
        60 short. The month is running, so it is not a verdict yet."""
        budget, checking, mortgage = await self._mortgage(db_session, api_client.test_user)
        await create_transaction(db_session, budget, checking, "-60.00", EARLY, category=mortgage)
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=3)

        cell = _row(pvr, mortgage)["monthly"][-1]
        assert (cell["assigned"], cell["moved_out"], cell["funded"], cell["spent"]) == (
            D("1500"),
            D("1500"),
            D("0"),
            D("60"),
        )
        assert (cell["left"], cell["overspent"], cell["over"]) == (D("-60"), D("60"), False)

    async def test_a_brokerage_transfer_leaves_the_rest_of_the_plan(self, db_session, api_client):
        budget, fun = await self._brokerage(db_session, api_client.test_user)
        reports = ReportService(db_session)
        bva = await reports.budget_vs_actual(budget.id, THIS_MONTH, TODAY)
        (point,) = (await reports.plan_vs_spent(budget.id, months=1))["month_totals"][-1:]
        pvr = await reports.plan_vs_spent(budget.id, months=3)

        row = _row(bva, fun)
        assert (row["assigned"], row["moved_out"], row["funded"]) == (D("600"), D("400"), D("200"))
        # Not spent: saving is not spending. 20 left, where it read 420.
        assert (row["spent"], row["left"], row["over"]) == (D("180"), D("20"), False)
        assert bva["total_moved_out"] == D("400")
        assert (point["moved_out"], point["funded"], point["spent"], point["left"]) == (
            D("400"),
            D("200"),
            D("180"),
            D("20"),
        )
        cat = _row(pvr, fun)
        assert cat["monthly"][-1]["moved_out"] == D("400")
        # The running month is in no total.
        assert (cat["total"]["moved_out"], pvr["total_moved_out"]) == (D("0"), D("0"))

    async def test_plan_vs_reality_totals_carry_it_over_complete_months(
        self, db_session, api_client
    ):
        budget, checking, _, group = await _world(db_session, api_client.test_user)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        fun = await create_category(db_session, budget, group, "Fun Money")
        await create_budget_assignment(db_session, budget, fun, back(1), "600.00")
        await create_transfer(
            db_session, budget, checking, brokerage, "400.00", back(1), category=fun
        )
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=3)
        assert (_row(pvr, fun)["total"]["moved_out"], pvr["total_moved_out"]) == (
            D("400"),
            D("400"),
        )

    async def test_moving_out_a_carried_balance_leaves_nothing_to_spend(
        self, db_session, api_client
    ):
        """2,000 carried in from last month and all of it drained into a
        brokerage, then 30 spent: funded 0, and the 30 is overspent — never the
        2,030 an unfloored plan of -2,000 would read it overrun by."""
        budget, checking, _, group = await _world(db_session, api_client.test_user)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        rainy = await create_category(db_session, budget, group, "Rainy Day")
        await create_budget_assignment(db_session, budget, rainy, back(1), "2000.00")
        await create_transfer(
            db_session, budget, checking, brokerage, "2000.00", EARLY, category=rainy
        )
        await create_transaction(db_session, budget, checking, "-30.00", EARLY, category=rainy)

        bva = await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY)

        row = _row(bva, rainy)
        assert (row["carried_in"], row["moved_out"], row["funded"], row["spent"]) == (
            D("2000"),
            D("2000"),
            D("0"),
            D("30"),
        )
        assert (row["left"], row["overspent"], row["over"]) == (D("0"), D("30"), True)

    async def test_a_savings_envelope_outflow_is_still_spent_not_moved_out(
        self, db_session, api_client
    ):
        """The exception stands, stated once in `plan_effect`: the plan meant
        a savings envelope's money to leave, so its outflow is spent."""
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        savings = await create_category(db_session, budget, group, "Vacation Savings")
        await tag_with_system_tags(db_session, savings, "savings")
        await create_budget_assignment(db_session, budget, savings, THIS_MONTH, "500.00")
        await create_transfer(db_session, budget, checking, hysa, "200.00", EARLY, category=savings)

        row = _row(
            await ReportService(db_session).budget_vs_actual(budget.id, THIS_MONTH, TODAY), savings
        )
        assert (row["moved_out"], row["funded"], row["spent"], row["left"]) == (
            D("0"),
            D("500"),
            D("200"),
            D("300"),
        )

    async def test_category_history_serves_it(self, db_session, api_client):
        budget, fun = await self._brokerage(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(fun.id), "months": 3},
        )
        assert r.status_code == 200, r.text
        latest = r.json()["months"][-1]
        assert (money(latest["moved_out"]), money(latest["spent"])) == (D("400"), D("180"))

    async def test_the_endpoints_serve_it(self, db_session, api_client):
        budget, _ = await self._brokerage(db_session, api_client.test_user)
        await db_session.commit()
        base = f"/api/v1/{budget.id}/reports"
        r = await api_client.get(f"{base}/plan-vs-spent", params={"months": 3})
        assert r.status_code == 200, r.text
        body = r.json()
        # In the running month, so in its cell and its month total, and in no
        # window total (those are the complete months').
        assert money(body["categories"][0]["monthly"][-1]["moved_out"]) == D("400")
        assert money(body["month_totals"][-1]["moved_out"]) == D("400")
        assert money(body["categories"][0]["total"]["moved_out"]) == D("0")
        assert money(body["total_moved_out"]) == D("0")

    async def test_the_assistant_is_told_it(self, db_session, api_client):
        from igab.ai.tools import handlers
        from igab.ai.tools.context import build_tool_context

        budget, _ = await self._brokerage(db_session, api_client.test_user)
        ctx = await build_tool_context(db_session, budget.id, TODAY)
        result = await handlers.budget_vs_actual(
            ctx, {"start_date": THIS_MONTH.isoformat(), "end_date": TODAY.isoformat()}
        )
        (row,) = result["rows"]
        assert (row["moved_out"], row["funded"], row["spent"]) == (400.0, 200.0, 180.0)
        assert (row["left"], row["overspent"]) == (20.0, 0.0)
        assert result["total_moved_out"] == 400.0


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
        (point,) = (await reports.plan_vs_spent(budget.id, months=1))["month_totals"][-1:]
        pvr = await reports.plan_vs_spent(budget.id, months=3)

        assert bva["categories"] == []
        assert (point["funded"], point["left"]) == (D("0"), D("0"))
        assert pvr["categories"] == []


class TestOverHasATolerance:
    """Over by at least $1 AND 1% of what the envelope was funded with. Each
    month is 1,500 assigned and paid past it, so each ends a little negative
    and the next starts from zero."""

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
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=6)

        row = _row(pvr, mortgage)
        assert (row["months_over"], row["chronic"], pvr["chronic_count"]) == (0, False, 0)
        # The arithmetic is still there; only the verdict is tolerant.
        last = row["monthly"][-2]
        assert (last["left"], last["overspent"], last["over"]) == (D("-0.27"), D("0.27"), False)

    async def test_past_a_dollar_but_under_one_percent_is_not_over(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "14.00")
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=6)

        assert _row(pvr, mortgage)["months_over"] == 0

    async def test_one_percent_and_a_dollar_three_times_is_chronic(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "15.00")
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=6)

        row = _row(pvr, mortgage)
        assert (row["months_over"], row["chronic"]) == (3, True)
        assert row["avg_overspend"] == D("15.00")

    async def test_budget_vs_actual_uses_the_same_verdict(self, db_session, api_client):
        budget, mortgage = await self._mortgage(db_session, api_client.test_user, "0.27")
        bva = await ReportService(db_session).budget_vs_actual(budget.id, back(2), TODAY)

        assert _row(bva, mortgage)["over"] is False


class TestASinkingFundIsJudgedByWhatItHeld:
    """A quarterly-ish premium paid from a Long-term expense envelope.

    Judged by its monthly assignment, the month the bill landed was "over"
    every time — the plan working — so a sinking fund was exempt from chronic.
    Judged by what it held (carryover counts), paying the bill it saved for
    leaves it at zero, not below, and there is nothing to exempt: the tag no
    longer matters. One that is saving too little does go negative when the
    bill lands, and that is overspending, tagged or not."""

    async def _premium(self, db_session, user, monthly: str, paid_in: tuple[int, ...]):
        """`monthly` assigned in each of the last six months and the running
        one; a 300 premium paid in each month of `paid_in`."""
        budget, checking, _, group = await _world(db_session, user)
        premium = await create_category(db_session, budget, group, "Home Insurance")
        await tag_with_system_tags(db_session, premium, "long_term_expense")
        await create_transaction(db_session, budget, checking, "-1.00", back(6))
        for n in range(7):
            await create_budget_assignment(db_session, budget, premium, back(n), monthly)
        for n in paid_in:
            await create_transaction(
                db_session, budget, checking, "-300.00", back(n), category=premium
            )
        return budget, premium

    async def test_paying_the_bill_it_saved_for_is_never_over(self, db_session, api_client):
        """150 a month, 300 every other month: 150, 0, 150, 0, 150, 0."""
        budget, premium = await self._premium(db_session, api_client.test_user, "150.00", (5, 3, 1))
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=6)

        row = _row(pvr, premium)
        lefts = [c["left"] for c in row["monthly"]]
        assert lefts == [D(x) for x in ("150", "0", "150", "0", "150", "0", "150")]
        assert (row["months_over"], row["chronic"], pvr["chronic_count"]) == (0, False, 0)

    async def test_an_underfunded_one_is_chronic_like_any_other(self, db_session, api_client):
        """100 a month against a 300 bill every other month: each bill lands
        on the 200 saved since the last one and leaves the envelope 100 short,
        which Ready to Assign covers. The tag no longer exempts it: over in
        three of the last six months is chronic."""
        budget, premium = await self._premium(db_session, api_client.test_user, "100.00", (5, 3, 1))
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=6)

        row = _row(pvr, premium)
        # back(6) 100; back(5) 200-300 = -100; back(4) 100; back(3) 200-300 =
        # -100; back(2) 100; back(1) -100; running 100.
        lefts = [c["left"] for c in row["monthly"]]
        assert lefts == [D(x) for x in ("100", "-100", "100", "-100", "100", "-100", "100")]
        assert (row["months_over"], row["chronic"], pvr["chronic_count"]) == (3, True, 1)
        assert row["avg_overspend"] == D("100.00")

    async def test_the_guide_reads_the_same_flag(self, db_session, api_client):
        """One rule: the checkup's chronic count is the report's."""
        budget, _ = await self._premium(db_session, api_client.test_user, "150.00", (5, 3, 1))
        checking = await create_account(db_session, budget, "Second Checking")
        group = await create_category_group(db_session, budget, "Fun")
        dining = await create_category(db_session, budget, group, "Dining Out")
        for n in (1, 2, 3):
            await create_transaction(
                db_session, budget, checking, "-40.00", back(n), category=dining
            )
        await db_session.commit()

        body = (await api_client.get(f"/api/v1/{budget.id}/guide/checkup")).json()
        pvr = (await api_client.get(f"/api/v1/{budget.id}/reports/plan-vs-spent")).json()

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
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=3)
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
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=3)
        assert pvr["running_month"] == THIS_MONTH
        assert pvr["months"][-1] == THIS_MONTH


class TestAMonthTotalIsItsColumnSummed:
    """A month total is its column of cells summed — what Cumulative Variance
    served beside Plan vs Reality's matrix, and now its totals row."""

    async def test_every_month_agrees(self, db_session, api_client):
        """Car Repairs: 300 funded two months ago, all of it drained last
        month, then 80 moved in and 100 spent this month. Dining Out: 300
        assigned and 350 spent last month."""
        budget, checking, hysa, group = await _world(db_session, api_client.test_user)
        a = await create_category(db_session, budget, group, "Car Repairs")
        b = await create_category(db_session, budget, group, "Dining Out")
        await create_transaction(db_session, budget, checking, "-1.00", back(2))
        await create_budget_assignment(db_session, budget, a, back(2), "300.00")
        await create_budget_assignment(db_session, budget, a, back(1), "-300.00")
        await create_budget_assignment(db_session, budget, b, back(1), "300.00")
        await create_transaction(db_session, budget, checking, "-350.00", back(1), category=b)
        await _moved_in(db_session, budget, hysa, checking, "80.00", EARLY, a)
        await create_transaction(db_session, budget, checking, "-100.00", EARLY, category=a)

        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=3)
        totals = pvr["month_totals"]

        summed = ("carried_in", "assigned", "moved_in", "moved_out", "funded", "spent")
        summed += ("other", "left", "overspent")
        for i, point in enumerate(totals):
            column = [c["monthly"][i] for c in pvr["categories"]]
            for key in summed:
                cells = sum((c[key] or D("0") for c in column), D("0"))
                assert point[key] == cells, (point["month"], key)
            assert point["funded"] - point["spent"] + point["other"] == point["left"]

        by_month = {p["month"]: p for p in totals}
        # Two months ago: Car Repairs funded 300 and kept it.
        two = by_month[back(2)]
        assert (two["funded"], two["left"], two["categories_over"]) == (D("300"), D("300"), 0)
        # Last month: the drain empties Car Repairs (300 in, 300 out — on
        # plan), and Dining ends 50 short.
        one = by_month[back(1)]
        assert (one["carried_in"], one["funded"], one["spent"]) == (D("300"), D("300"), D("350"))
        assert (one["left"], one["overspent"], one["categories_over"]) == (D("-50"), D("50"), 1)
        # This month, drawn but in no total: 80 moved in, 100 spent.
        now = by_month[THIS_MONTH]
        assert (now["funded"], now["spent"], now["left"]) == (D("80"), D("100"), D("-20"))
        assert now["categories_over"] == 0
        # The headline reads the complete months: Dining's 50.
        assert pvr["total_overspent"] == D("50")
